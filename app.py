import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pydeck as pdk

# ---------------------------------
# CONFIG
# ---------------------------------
st.set_page_config(page_title="Buscador de Cafés", layout="wide")

# ---------------------------------
# CARGA CSV
# ---------------------------------
@st.cache_data
def cargar_cafes():
    df = pd.read_csv("cafes.csv")

    # Normalizar columnas
    df.columns = [c.strip() for c in df.columns]

    # Corregir decimales con coma
    df["LAT"] = (
        df["LAT"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    df["LONG"] = (
        df["LONG"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    # Puntaje con coma decimal
    df["PUNTAJE"] = (
        df["PUNTAJE"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    return df.dropna(subset=["LAT", "LONG"])

cafes = cargar_cafes()

# ---------------------------------
# SESSION STATE (para que NO se recargue)
# ---------------------------------
if "direccion" not in st.session_state:
    st.session_state.direccion = ""

if "radio" not in st.session_state:
    st.session_state.radio = 2

# ---------------------------------
# UI
# ---------------------------------
st.title("☕ Buscador de Cafés")

st.markdown("Buscá cafés cerca de una dirección. **No necesitás latitud ni longitud.**")

col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input(
        "Dirección",
        placeholder="Ej: Alberti 2900, Mar del Plata",
        value=st.session_state.direccion
    )

with col2:
    radio_km = st.slider(
        "Radio (km)",
        0.5, 5.0,
        value=st.session_state.radio,
        step=0.5
    )

buscar = st.button("Buscar cafés")

# ---------------------------------
# GEOCODING
# ---------------------------------
def geocodificar(direccion):
    geolocator = Nominatim(user_agent="buscador_cafes")
    location = geolocator.geocode(direccion + ", Mar del Plata, Argentina")
    if location:
        return location.latitude, location.longitude
    return None, None

# ---------------------------------
# BUSQUEDA
# ---------------------------------
if buscar and direccion.strip():
    st.session_state.direccion = direccion
    st.session_state.radio = radio_km

    lat_user, lon_user = geocodificar(direccion)

    if lat_user is None:
        st.error("No se pudo encontrar esa dirección 😕")
    else:
        cafes_calc = cafes.copy()

        cafes_calc["DIST_KM"] = cafes_calc.apply(
            lambda row: geodesic(
                (lat_user, lon_user),
                (row["LAT"], row["LONG"])
            ).km,
            axis=1
        )

        resultado = cafes_calc[cafes_calc["DIST_KM"] <= radio_km]

        if resultado.empty:
            st.warning("No se encontraron cafés en ese radio ☹️")
        else:
            resultado = resultado.sort_values("DIST_KM")

            # ---------------------------------
            # MAPA
            # ---------------------------------
            st.subheader("📍 Cafés cercanos")

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=resultado,
                get_position='[LONG, LAT]',
                get_radius=60,
                pickable=True,
                get_fill_color=[200, 30, 0, 180],
            )

            view_state = pdk.ViewState(
                latitude=lat_user,
                longitude=lon_user,
                zoom=14,
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    tooltip={
                        "html": "<b>{CAFE}</b><br/>{UBICACION}<br/>⭐ {PUNTAJE}<br/>{DIST_KM:.2f} km"
                    }
                )
            )

            # ---------------------------------
            # LISTA
            # ---------------------------------
            st.subheader("☕ Resultados")

            for _, row in resultado.iterrows():
                st.markdown(
                    f"""
                    **{row['CAFE']}**  
                    📍 {row['UBICACION']}  
                    🔥 Tostador: {row['TOSTADOR']}  
                    ⭐ Puntaje: {row['PUNTAJE']}  
                    📏 Distancia: {row['DIST_KM']:.2f} km  
                    🕒 Abre domingos: {row['¿ Abre los domingos ?']}  
                    ---
                    """
                )

# ---------------------------------
# FOOTER
# ---------------------------------
st.caption("Datos cargados desde Google Sheets · Proyecto Buscador de Cafés ☕")
