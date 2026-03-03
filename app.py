import streamlit as st
import pandas as pd
import random
import re
import unicodedata
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk
import requests
from streamlit_js_eval import get_geolocation

# =========================
# CONFIG APP
# =========================
st.set_page_config(page_title="Mapa de Cafeterías", page_icon="☕", layout="wide")

# Estilo para el Contador y Badges
st.markdown("""
    <style>
    .main-counter {
        background: linear-gradient(135deg, #5f3512 0%, #a67c52 100%);
        color: white;
        padding: 30px;
        border-radius: 15px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        margin-bottom: 25px;
    }
    .main-counter h1 { font-size: 3rem; margin: 0; }
    .main-counter p { font-size: 1.2rem; opacity: 0.9; }
    </style>
""", unsafe_allow_html=True)

# =========================
# CARGA DE DATOS
# =========================
SPREADSHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"
GID_CAFES = {
    "Mar del Plata": "0", "Buenos Aires": "1296176686", 
    "La Plata": "208452991", "Córdoba": "1250014567", "Rosario": "1691979590"
}

def sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"

@st.cache_data(ttl=300)
def cargar_cafes(gid):
    try:
        df = pd.read_csv(sheet_url(gid), dtype=str)
        df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", "."), errors="coerce")
        df["LONG"] = pd.to_numeric(df["LONG"].str.replace(",", "."), errors="coerce")
        return df.dropna(subset=["LAT", "LONG"])
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_todo_argentina():
    lista_dfs = []
    for ciudad, gid in GID_CAFES.items():
        df = cargar_cafes(gid)
        df["CIUDAD_ORIGEN"] = ciudad
        lista_dfs.append(df)
    return pd.concat(lista_dfs, ignore_index=True)

# =========================
# GEOCODER PARA CALLE GPS
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def obtener_calle(lat, lon):
    geo = get_geocoder()
    try:
        location = geo.reverse((lat, lon))
        return location.address
    except:
        return "Dirección desconocida"

# =========================
# LÓGICA DE TELEGRAM (CON SECRETS)
# =========================
with st.sidebar:
    st.header("💡 Sugerencias")
    with st.form("form_sugerencia", clear_on_submit=True):
        tipo = st.radio("Tipo", ["✨ Nuevo", "✏️ Editar", "❌ Cerrado"])
        nombre = st.text_input("Nombre *")
        dire = st.text_input("Dirección *")
        enviar = st.form_submit_button("Enviar a Lisandro")
        if enviar and nombre and dire:
            try:
                msg = f"☕ NUEVO REPORTE: {tipo}\nNombre: {nombre}\nDir: {dire}"
                requests.post(f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendMessage", 
                              data={"chat_id": st.secrets['CHAT_ID'], "text": msg})
                st.success("¡Enviado!")
            except:
                st.error("Error al enviar")

# =========================
# INTERFAZ PRINCIPAL
# =========================
df_total = cargar_todo_argentina()

st.markdown(f"""
    <div class="main-counter">
        <p>Explorando el café de especialidad</p>
        <h1>{len(df_total)} Cafeterías</h1>
        <p>en todo el país</p>
    </div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📍 Cerca de mí", "🇦🇷 Mapa Federal", "🏙️ Por Ciudad"])

# --- TAB 1: GPS ---
with tabs[0]:
    loc = get_geolocation()
    if loc:
        lat, lon = loc['coords']['latitude'], loc['coords']['longitude']
        calle_actual = obtener_calle(lat, lon)
        st.success(f"📍 Detectado en: **{calle_actual}**")
        
        radio = st.slider("¿A cuántos km buscamos?", 0.5, 5.0, 1.5)
        
        df_total["DIST"] = df_total.apply(lambda r: geodesic((lat, lon), (r["LAT"], r["LONG"])).km, axis=1)
        cercanos = df_total[df_total["DIST"] <= radio].sort_values("DIST")
        
        if not cercanos.empty:
            view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=14)
            layer = pdk.Layer(
                "ScatterplotLayer",
                cercanos,
                get_position=["LONG", "LAT"],
                get_color=[255, 90, 0, 160],
                get_radius=40,
                radius_min_pixels=4, # Mantiene el punto visible al alejar
                pickable=True
            )
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{CAFE}\n{UBICACION}"}))
            st.dataframe(cercanos[["CAFE", "UBICACION", "CIUDAD_ORIGEN"]], use_container_width=True)
        else:
            st.warning("No hay cafés cerca en este radio.")
    else:
        st.info("Esperando señal GPS... Por favor, aceptá los permisos en el navegador.")

# --- TAB 2: MAPA FEDERAL (Punto 4) ---
with tabs[1]:
    st.subheader("Mapa de Cafeterías en Argentina")
    
    view_state_arg = pdk.ViewState(latitude=-38.4161, longitude=-63.6167, zoom=4)
    
    layer_federal = pdk.Layer(
        "ScatterplotLayer",
        df_total,
        get_position=["LONG", "LAT"],
        get_color=[100, 50, 0, 200],
        get_radius=30,
        radius_min_pixels=3, # Puntos pequeños y definidos
        pickable=True
    )
    
    st.pydeck_chart(pdk.Deck(
        layers=[layer_federal], 
        initial_view_state=view_state_arg,
        tooltip={"text": "{CAFE} ({CIUDAD_ORIGEN})"}
    ))

# --- TAB 3: POR CIUDAD ---
with tabs[2]:
    ciudad_sel = st.selectbox("Elegí una ciudad para ver el listado", list(GID_CAFES.keys()))
    df_c = cargar_cafes(GID_CAFES[ciudad_sel])
    st.dataframe(df_c, use_container_width=True)
