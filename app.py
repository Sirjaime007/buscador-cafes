import streamlit as st
import pandas as pd
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Buscador de Cafés",
    page_icon="☕",
    layout="wide"
)

st.title("☕ Buscador de Cafés en Mar del Plata")

# =========================
# CARGA CSV
# =========================
@st.cache_data
def cargar_cafes():
    df = pd.read_csv("Cafes.csv", dtype=str)

    # Normalizar números con coma
    for col in ["LAT", "LONG", "PUNTAJE"]:
        df[col] = (
            df[col]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["LAT", "LONG"])
    return df

cafes = cargar_cafes()

# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocodificar(direccion):
    geo = get_geocoder()
    loc = geo.geocode(f"{direccion}, Mar del Plata, Argentina")
    if loc:
        return (loc.latitude, loc.longitude)
    return None

# =========================
# UI
# =========================
direccion = st.text_input(
    "Dirección",
    value="Av. Colón 1500",
    placeholder="Ej: Alberti 2500"
)

radio_km = st.slider(
    "Radio de búsqueda (km)",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5
)

buscar = st.button("🔍 Buscar cafés")

# =========================
# BUSQUEDA
# =========================
if buscar:
    coords = geocodificar(direccion)

    if coords is None:
        st.error("No se pudo encontrar la dirección")
        st.stop()

    cafes_calc = cafes.copy()

    cafes_calc["DIST_KM"] = cafes_calc.apply(
        lambda r: geodesic(
            coords,
            (r["LAT"], r["LONG"])
        ).km,
        axis=1
    )

    resultado = cafes_calc[cafes_calc["DIST_KM"] <= radio_km]
    resultado = resultado.sort_values("DIST_KM")

    if resultado.empty:
        st.warning("No hay cafés en ese radio")
        st.stop()

    st.subheader("☕ Cafés encontrados")

    st.dataframe(
        resultado[
            ["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM"]
        ].assign(DIST_KM=lambda x: x["DIST_KM"].round(2)),
        use_container_width=True,
        hide_index=True
    )

    # =========================
    # MAPA
    # =========================
    st.subheader("🗺️ Mapa")

    map_df = resultado.rename(
        columns={"LAT": "lat", "LONG": "lon"}
    )

    layer_cafes = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=80,
        get_fill_color=[200, 30, 0, 160],
        pickable=True
    )

    layer_user = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{
            "lat": coords[0],
            "lon": coords[1]
        }]),
        get_position=["lon", "lat"],
        get_radius=120,
        get_fill_color=[0, 120, 255, 200]
    )

    view_state = pdk.ViewState(
        latitude=coords[0],
        longitude=coords[1],
        zoom=14
    )

    deck = pdk.Deck(
        layers=[layer_cafes, layer_user],
        initial_view_state=view_state,
        tooltip={
            "text": "{CAFE}\n{UBICACION}\nPuntaje: {PUNTAJE}"
        }
    )

    st.pydeck_chart(deck, use_container_width=True)
