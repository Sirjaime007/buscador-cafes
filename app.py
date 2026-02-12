import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk

# ================================
# Configuración general
# ================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# ================================
# Cargar dataset de cafés (sin truncar decimales)
# ================================
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="latin-1", dtype=str)  # leer como texto

    required_cols = {"CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG"}
    if not required_cols.issubset(df.columns):
        st.error(f"Faltan columnas: {required_cols}")
        st.stop()

    def fix_number(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "":
            return None
        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")
        if x.count(".") == 1 and x.count(",") == 1:
            return x.replace(".", "").replace(",", ".")
        return x

    df["LAT"] = pd.to_numeric(df["LAT"].apply(fix_number), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].apply(fix_number), errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"].apply(fix_number), errors="coerce")

    return df

cafes = load_cafes("Cafes.csv")

# ================================
# Geocoder ArcGIS
# ================================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address_arcgis(address: str):
    if not address:
        return None
    loc = get_geocoder().geocode(f"{address}, Mar del Plata, Buenos Aires, Argentina")
    if loc is None:
        return None
    return (loc.latitude, loc.longitude)

# ================================
# Inputs
# ================================
col1, col2 = st.columns([3, 1])
with col1:
    direccion = st.text_input("Dirección", value="Av. Colón 1500")
with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.5)

buscar = st.button("🔎 Buscar cafés cercanos")

# ================================
# Lógica principal
# ================================
if buscar:
    with st.spinner("Buscando dirección…"):
        coord_user = geocode_address_arcgis(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección.")
        st.stop()

    st.success(f"Dirección encontrada: lat={coord_user[0]:.8f}, lon={coord_user[1]:.8f}")

    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda r: geodesic(coord_user, (r["LAT"], r["LONG"])).km,
        axis=1
    )

    cafes_validos["CUADRAS"] = cafes_validos["DIST_KM"] * 1000 / 87

    resultado = cafes_validos[cafes_validos["DIST_KM"] <= radio_km] \
        .sort_values("DIST_KM") \
        .reset_index(drop=True)

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio seleccionado.")
        st.stop()

    # Tabla sin LAT y LONG
    tabla = resultado.copy()
    tabla["DIST_KM"] = tabla["DIST_KM"].round(3)
    tabla["CUADRAS"] = tabla["CUADRAS"].round(1)

    st.dataframe(
        tabla[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS"]],
        use_container_width=True,
        hide_index=True
    )

    # ================================
    # Mapa con puntos pequeños (pydeck)
    # ================================
    st.subheader("Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position='[lon, lat]',
        get_radius=8,         # tamaño MUY pequeño
        get_color=[0, 0, 0],  # negro
        pickable=False
    )

    view_state = pdk.ViewState(
        latitude=coord_user[0],
        longitude=coord_user[1],
        zoom=14
    )

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
