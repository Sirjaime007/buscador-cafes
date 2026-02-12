import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS

# ---------------------------------------
# Configuración general
# ---------------------------------------
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# ---------------------------------------
# Cargar dataset de cafés
# ---------------------------------------
# --- BLOQUE DE FORMATEO PARA MOSTRAR EN TABLA (NO ALTERA LOS CÁLCULOS) ---
cols_show = ["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG", "DIST_KM"]

res_to_show = resultado[cols_show].copy()

# Mostrar LAT/LONG con TODOS los decimales (12 es suficiente y legible)
res_to_show["LAT"] = res_to_show["LAT"].map(lambda x: f"{x:.12f}" if pd.notna(x) else "")
res_to_show["LONG"] = res_to_show["LONG"].map(lambda x: f"{x:.12f}" if pd.notna(x) else "")

# Mostrar distancia con 3 decimales; los cálculos se hicieron con float de precisión completa
res_to_show["DIST_KM"] = res_to_show["DIST_KM"].round(3)

st.dataframe(
    res_to_show,
    use_container_width=True,
    hide_index=True
)
st.dataframe(
    resultado.assign(DIST_KM=lambda d: d["DIST_KM"]),
    use_container_width=True,
    hide_index=True
)

cafes = load_cafes("Cafes.csv")

# ---------------------------------------
# Geocoder ArcGIS (no requiere API KEY)
# ---------------------------------------
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address_arcgis(address: str):
    if not address:
        return None

    # Sesgo automático a Mar del Plata
    query = f"{address}, Mar del Plata, Buenos Aires, Argentina"

    geolocator = get_geocoder()
    loc = geolocator.geocode(query)

    if loc is None:
        return None

    return (loc.latitude, loc.longitude)

# ---------------------------------------
# Inputs
# ---------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input(
        "Dirección",
        value="Av. Colón 1500",
        placeholder="Ej.: Gascon 2525, Córdoba 1800, etc."
    )

with col2:
    radio_km = st.number_input(
        "Radio (km)",
        min_value=0.1,
        value=2.0,
        step=0.5
    )

buscar = st.button("🔎 Buscar cafés cercanos")

# ---------------------------------------
# Lógica principal
# ---------------------------------------
if buscar:
    with st.spinner("Buscando dirección…"):
        coord_user = geocode_address_arcgis(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá agregar altura o revisar la calle.")
        st.stop()

    st.success(f"Dirección encontrada: lat={coord_user[0]:.5f}, lon={coord_user[1]:.5f}")

    # Filtrar cafés con coordenadas válidas
    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda row: geodesic(coord_user, (row["LAT"], row["LONG"])).km,
        axis=1
    )

    resultado = cafes_validos[cafes_validos["DIST_KM"] <= radio_km] \
                .sort_values("DIST_KM") \
                .reset_index(drop=True)

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio seleccionado.")
        st.stop()

    st.dataframe(
        resultado.assign(DIST_KM=lambda d: d["DIST_KM"].round(3)),
        use_container_width=True,
        hide_index=True
    )

    # Mapa de cafés cerca de la dirección
    st.subheader("Mapa")
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})
    st.map(map_df[["lat", "lon"]], zoom=14)
