import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS

# ================================
# Configuración general
# ================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# ================================
# Cargar dataset de cafés (sin truncar decimales, con puntajes correctos)
# ================================
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    # Leer como texto para NO truncar nada
    df = pd.read_csv(path, encoding="latin-1", dtype=str)

    required_cols = {"CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG"}
    if not required_cols.issubset(df.columns):
        st.error(f"El CSV no contiene estas columnas obligatorias: {required_cols}")
        st.stop()

    # Normalizador de números (conserva todos los decimales)
    def fix_number(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "":
            return None
        # -38,0056 -> -38.0056  (formato AR)
        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")
        # 1.234,567 -> 1234.567  (miles + decimales)
        if x.count(".") == 1 and x.count(",") == 1:
            return x.replace(".", "").replace(",", ".")
        return x  # ya está OK

    # Aplicar normalización
    df["LAT"] = df["LAT"].apply(fix_number)
    df["LONG"] = df["LONG"].apply(fix_number)
    df["PUNTAJE"] = df["PUNTAJE"].apply(fix_number)

    # Convertir a número
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"], errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"], errors="coerce")

    return df

cafes = load_cafes("Cafes.csv")

# ================================
# Geocoder ArcGIS (sin API Key)
# ================================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address_arcgis(address: str):
    if not address:
        return None
    query = f"{address}, Mar del Plata, Buenos Aires, Argentina"
    loc = get_geocoder().geocode(query)
    if loc is None:
        return None
    return (loc.latitude, loc.longitude)

# ================================
# Inputs
# ================================
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

# ================================
# Lógica principal
# ================================
if buscar:
    with st.spinner("Buscando dirección…"):
        coord_user = geocode_address_arcgis(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá agregar altura o revisar la calle.")
        st.stop()

    st.success(f"Dirección encontrada: lat={coord_user[0]:.8f}, lon={coord_user[1]:.8f}")

    # Filtrar cafés con coordenadas válidas
    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    # Distancia en km
    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda row: geodesic(coord_user, (row["LAT"], row["LONG"])).km,
        axis=1
    )
    # Distancia en cuadras (1 cuadra = 87 m)
    cafes_validos["CUADRAS"] = cafes_validos["DIST_KM"] * 1000.0 / 87.0

    # Filtrar por radio
    resultado = (
        cafes_validos[cafes_validos["DIST_KM"] <= radio_km]
        .sort_values("DIST_KM")
        .reset_index(drop=True)
    )

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio seleccionado.")
        st.stop()

    # ---- Formato de salida para mostrar (no altera cálculos) ----
    res_show = resultado.copy()
    # Mostrar LAT/LONG con todos los decimales
    res_show["LAT"] = res_show["LAT"].map(lambda x: f"{x:.12f}")
    res_show["LONG"] = res_show["LONG"].map(lambda x: f"{x:.12f}")
    # Distancias: km (3 decimales) y cuadras (1 decimal)
    res_show["DIST_KM"] = res_show["DIST_KM"].round(3)
    res_show["CUADRAS"] = res_show["CUADRAS"].round(1)

    st.dataframe(
        res_show[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG", "DIST_KM", "CUADRAS"]],
        use_container_width=True,
        hide_index=True
    )

    # Mapa
    st.subheader("Mapa")
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})
    st.map(map_df[["lat", "lon"]], zoom=14)
