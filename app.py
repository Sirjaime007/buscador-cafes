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
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")

# Estilo para el Contador Estético
st.markdown("""
    <style>
    .main-counter {
        background: linear-gradient(135deg, #5f3512 0%, #a67c52 100%);
        color: white; padding: 25px; border-radius: 15px;
        text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        margin-bottom: 25px;
    }
    .main-counter h1 { font-size: 2.8rem; margin: 0; }
    .main-counter p { font-size: 1.1rem; opacity: 0.9; }
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
GID_TOSTADORES = "1590442133"

def sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"

@st.cache_data(ttl=300)
def cargar_cafes(gid):
    try:
        df = pd.read_csv(sheet_url(gid), dtype=str)
        df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", "."), errors="coerce")
        df["LONG"] = pd.to_numeric(df["LONG"].str.replace(",", "."), errors="coerce")
        return df.dropna(subset=["LAT", "LONG"])
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_tostadores():
    try: return pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str)
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_todos_los_cafes():
    dfs = []
    for ciudad, gid in GID_CAFES.items():
        df = cargar_cafes(gid).copy()
        df["CIUDAD"] = ciudad
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# =========================
# FUNCIONES DE APOYO
# =========================
@st.cache_resource
def get_geocoder(): return ArcGIS(timeout=10)

def obtener_calle(lat, lon):
    try: return get_geocoder().reverse((lat, lon)).address
    except: return "Ubicación GPS"

def normalizar_texto(valor, fallback="Sin dato"):
    if pd.isna(valor): return fallback
    return str(valor).strip()

# =========================
# SIDEBAR - TELEGRAM (SEGURIDAD OK)
# =========================
with st.sidebar:
    st.header("💡 Ayudanos a mejorar")
    with st.form("form_sugerencia", clear_on_submit=True):
        tipo = st.radio("Reportar", ["✨ Nuevo local", "✏️ Editar", "❌ Cerrado"])
        sug_nombre = st.text_input("Nombre del local *")
        sug_ubicacion = st.text_input("Dirección *")
        btn_enviar = st.form_submit_button("Enviar sugerencia")
        if btn_enviar and sug_nombre and sug_ubicacion:
            try:
                msg = f"☕ NUEVO REPORTE: {tipo}\nNombre: {sug_nombre}\nDir: {sug_ubicacion}"
                requests.post(f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendMessage", 
                              data={"chat_id": st.secrets['CHAT_ID'], "text": msg})
                st.success("¡Gracias, Lisandro! Recibido.")
            except: st.error("Error al enviar")

# =========================
# UI PRINCIPAL - CONTADOR
# =========================
df_total = cargar_todos_los_cafes()
st.markdown(f"""<div class="main-counter"><p>Explorando el café de especialidad</p><h1>{len(df_total)} Cafeterías</h1><p>en Argentina</p></div>""", unsafe_allow_html=True)

tabs = st.tabs(["☕ Cafés", "🔥 Tostadores", "🔍 Buscar por Nombre", "🇦🇷 Mapa Federal"])

# --- TAB 1: CAFÉS (CON BOTÓN GPS) ---
with tabs[0]:
    ciudad_sel = st.selectbox("🏙️ Ciudad", list(GID_CAFES.keys()))
    df_ciudad = cargar_cafes(GID_CAFES[ciudad_sel])
    
    col_input, col_gps = st.columns([3, 1])
    with col_input:
        direccion = st.text_input("📍 Ingresá tu dirección", placeholder="Ej: Av. Colón 1500")
    with col_gps:
        st.write("") # Espaciador
        usar_gps = st.button("📍 Usar GPS")

    # Lógica de ubicación
    lat_user, lon_user = None, None
    if usar_gps:
        loc = get_geolocation()
        if loc:
            lat_user, lon_user = loc['coords']['latitude'], loc['coords']['longitude']
            direccion = obtener_calle(lat_user, lon_user)
            st.info(f"Ubicación detectada: {direccion}")
        else:
            st.warning("Por favor, habilitá el GPS en tu navegador.")

    radio_km = st.slider("📏 Radio de búsqueda (km)", 0.5, 5.0, 1.5)
    
    if st.button("🔍 Buscar Cafés Cercanos", use_container_width=True):
        if not lat_user and direccion:
            try:
                res = get_geocoder().geocode(f"{direccion}, {ciudad_sel}, Argentina")
                if res: lat_user, lon_user = res.latitude, res.longitude
            except: pass

        if lat_user:
            df_ciudad["DIST_KM"] = df_ciudad.apply(lambda r: geodesic((lat_user, lon_user), (r["LAT"], r["LONG"])).km, axis=1)
            resultado = df_ciudad[df_ciudad["DIST_KM"] <= radio_km].sort_values("DIST_KM")
            
            if not resultado.empty:
                st.subheader(f"Encontramos {len(resultado)} locales")
                st.dataframe(resultado[["CAFE", "UBICACION", "TOSTADOR"]], use_container_width=True)
                
                # MAPA CON PUNTOS CHICOS PERO VISIBLES
                view = pdk.ViewState(latitude=lat_user, longitude=lon_user, zoom=14)
                layer = pdk.Layer("ScatterplotLayer", resultado, get_position=["LONG", "LAT"],
                                  get_color=[150, 75, 0, 160], get_radius=40, radius_min_pixels=4, pickable=True)
                st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip={"text": "{CAFE}\n{UBICACION}"}))
            else:
                st.warning("No hay cafés en ese radio.")
        else:
            st.error("No pudimos obtener una ubicación. Ingresá una calle o activá el GPS.")

# --- TAB 2: TOSTADORES (COMO ANTES) ---
with tabs[1]:
    tostadores = cargar_tostadores()
    st.subheader("🔥 Tostadores Disponibles")
    st.dataframe(tostadores, use_container_width=True)

# --- TAB 3: BUSCAR POR NOMBRE (COMO ANTES) ---
with tabs[2]:
    nombre_buscado = st.text_input("Escribí el nombre del café")
    if nombre_buscado:
        match = df_total[df_total["CAFE"].str.contains(nombre_buscado, case=False, na=False)]
        st.dataframe(match[["CAFE", "UBICACION", "CIUDAD"]], use_container_width=True)

# --- TAB 4: MAPA FEDERAL (NUEVO) ---
with tabs[3]:
    st.subheader("🇦🇷 Todas las cafeterías del país")
    view_arg = pdk.ViewState(latitude=-38.41, longitude=-63.61, zoom=4)
    layer_fed = pdk.Layer("ScatterplotLayer", df_total, get_position=["LONG", "LAT"],
                          get_color=[100, 50, 0, 200], get_radius=30, radius_min_pixels=3, pickable=True)
    st.pydeck_chart(pdk.Deck(layers=[layer_fed], initial_view_state=view_arg, tooltip={"text": "{CAFE} ({CIUDAD})"}))
