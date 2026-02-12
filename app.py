import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk

# ======================================
# Configuración
# ======================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")


# ======================================
# Cargar CSV (tildes + decimales correctos)
# ======================================
@st.cache_data
def load_cafes(path):
    df = pd.read_csv(path, encoding="latin-1", dtype=str)

    # Fix caracteres especiales: á é í ó ú ñ ¿ ¡
    df = df.apply(lambda col: col.str.encode("latin-1", "ignore").str.decode("utf-8", "ignore"))

    def fix_number(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "":
            return None

        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")
        if x.count(",") == 1 and x.count(".") == 1:
            return x.replace(".", "").replace(",", ".")
        return x

    df["LAT"] = pd.to_numeric(df["LAT"].apply(fix_number), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].apply(fix_number), errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"].apply(fix_number), errors="coerce")

    return df


cafes = load_cafes("Cafes.csv")


# ======================================
# Geocoder ArcGIS (sin API Key)
# ======================================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)


def geocode_address(address):
    geo = get_geocoder().geocode(f"{address}, Mar del Plata, Buenos Aires, Argentina")
    if not geo:
        return None
    return float(geo.latitude), float(geo.longitude)


# ======================================
# Inputs
# ======================================
col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input("Dirección", "Av. Colón 1500")

with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)


# ======================================
# Búsqueda
# ======================================
if st.button("🔎 Buscar cafés cercanos"):
    with st.spinner("Buscando dirección..."):
        coord_user = geocode_address(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá con calle + altura.")
        st.stop()

    st.success("Dirección encontrada ✔️")

    # Filtrar cafés válidos
    cafes_ok = cafes.dropna(subset=["LAT", "LONG"]).copy()

    cafes_ok["DIST_KM"] = cafes_ok.apply(
        lambda r: geodesic(coord_user, (float(r["LAT"]), float(r["LONG"]))).km,
        axis=1
    )

    cafes_ok["CUADRAS"] = cafes_ok["DIST_KM"] * 1000 / 87

    resultado = (
        cafes_ok[cafes_ok["DIST_KM"] <= radio_km]
        .sort_values("DIST_KM")
        .reset_index(drop=True)
    )

    st.subheader("Resultados")

    if resultado.empty:
        st.info("No hay cafés dentro del radio indicado.")
        st.stop()

    # ============================
    # Tabla sin LAT/LONG
    # ============================
    tabla = resultado.copy()
    tabla["DIST_KM"] = tabla["DIST_KM"].round(3)
    tabla["CUADRAS"] = tabla["CUADRAS"].round(1)

    st.dataframe(
        tabla[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS"]],
        use_container_width=True,
        hide_index=True
    )

    # ============================
    # Mapa PyDeck (puntos pequeños)
    # ============================
    st.subheader("Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})[["lat", "lon", "CAFE", "UBICACION"]].dropna()

    # Asegurar tipo numérico
    map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")

    if map_df.empty:
        st.info("No hay puntos válidos para mostrar en el mapa.")
        st.stop()

    cafes_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=12,
        radius_units="meters",
        get_fill_color=[0, 0, 0, 220],
        pickable=True
    )

    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord_user[0], "lon": coord_user[1]}]),
        get_position=["lon", "lat"],
        get_radius=18,
        radius_units="meters",
        get_fill_color=[0, 100, 255, 220],
        pickable=False
    )

    view = pdk.ViewState(
        latitude=coord_user[0], longitude=coord_user[1], zoom=14
    )

    tooltip = {"html": "<b>{CAFE}</b><br/>{UBICACION}"}

    deck = pdk.Deck(
        layers=[cafes_layer, user_layer],
        initial_view_state=view,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9"
    )

    st.pydeck_chart(deck, use_container_width=True, height=500)
