import streamlit as st
import pandas as pd
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk
import requests
from streamlit_js_eval import get_geolocation

# =========================
# CONFIG APP Y ESTILOS
# =========================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif; color: #4B3832; }
    .stApp { background-color: #FDF8F5; }
    
    /* Contador Minimalista */
    .main-counter {
        background-color: #4B3832;
        color: #FDF8F5;
        padding: 35px 20px;
        border-radius: 16px;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 4px 15px rgba(75, 56, 50, 0.1);
    }
    .main-counter h1 { font-weight: 600; font-size: 3.2rem; margin: 0; color: #BE8C63; }
    .main-counter p { font-weight: 300; font-size: 1.1rem; opacity: 0.9; margin: 0; }

    /* Tarjetas de Tostadores */
    .tostador-card {
        background: #FFFFFF;
        border: 1px solid #EADBC8;
        border-radius: 12px;
        padding: 20px;
        min-height: 250px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }
    .tostador-title { color: #4B3832; font-weight: 600; font-size: 1.15rem; margin-bottom: 5px; }
    .tostador-desc { font-size: 0.9rem; color: #85746D; margin-top: 8px; line-height: 1.4; }
    
    /* Botones minimalistas */
    .ig-btn {
        background: #4B3832;
        color: #FDF8F5 !important;
        text-align: center;
        padding: 8px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        font-size: 0.85rem;
        margin-top: 15px;
        display: block;
        transition: background 0.3s;
    }
    .ig-btn:hover { background: #BE8C63; }
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
    except: 
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_tostadores():
    try: 
        return pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str).fillna("-")
    except: 
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_todos_los_cafes():
    dfs = []
    for ciudad, gid in GID_CAFES.items():
        df = cargar_cafes(gid).copy()
        df["CIUDAD_REF"] = ciudad
        dfs.append(df)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()

# =========================
# FUNCIONES
# =========================
@st.cache_resource
def get_geocoder(): 
    return ArcGIS(timeout=10)

def obtener_calle(lat, lon):
    try: 
        return get_geocoder().reverse((lat, lon)).address
    except: 
        return "Ubicación detectada"

# =========================
# SIDEBAR - TELEGRAM
# =========================
with st.sidebar:
    st.header("💡 Ayudanos a mejorar")
    with st.form("form_sugerencia", clear_on_submit=True):
        tipo = st.radio("Reportar", ["✨ Nuevo local", "✏️ Editar", "❌ Cerrado"])
        sug_nombre = st.text_input("Nombre del local *")
        sug_ubicacion = st.text_input("Dirección *")
        sug_ciudad = st.selectbox("Ciudad *", list(GID_CAFES.keys()) + ["Otra"])
        sug_comentario = st.text_area("Comentarios / Detalles")
        btn_enviar = st.form_submit_button("Enviar sugerencia")
        
        if btn_enviar and sug_nombre and sug_ubicacion:
            try:
                msg = (f"☕ NUEVO REPORTE\nTipo: {tipo}\nCafé: {sug_nombre}\n"
                       f"Dir: {sug_ubicacion}\nCiudad: {sug_ciudad}\nComentario: {sug_comentario}")
                requests.post(f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendMessage", 
                              data={"chat_id": st.secrets['CHAT_ID'], "text": msg})
                st.success("¡Enviado a @Lisandro0_18! 🚀")
            except: 
                st.error("Error al enviar")

# =========================
# UI PRINCIPAL - CONTADOR
# =========================
df_total = cargar_todos_los_cafes()
st.markdown(f"""
    <div class="main-counter">
        <p>EXPLORANDO EL CAFÉ DE ESPECIALIDAD</p>
        <h1>{len(df_total)} Cafeterías</h1>
        <p>en Argentina</p>
    </div>
""", unsafe_allow_html=True)

tabs = st.tabs(["☕ Cafés", "🔥 Tostadores", "🔍 Buscar por Nombre", "🇦🇷 Mapa Federal"])

# --- TAB 1: CAFÉS ---
with tabs[0]:
    ciudad_sel = st.selectbox("🏙️ Ciudad de búsqueda", list(GID_CAFES.keys()))
    df_ciudad = cargar_cafes(GID_CAFES[ciudad_sel])
    
    col_input, col_gps = st.columns([3, 1])
    with col_gps:
        st.write("###")
        posicion_gps = get_geolocation()
        usar_gps = st.button("📍 Usar mi ubicación")

    with col_input:
        dir_placeholder = "Ej: Av. Colón 1500"
        if usar_gps and posicion_gps:
            lat_gps = posicion_gps['coords']['latitude']
            lon_gps = posicion_gps['coords']['longitude']
            dir_placeholder = obtener_calle(lat_gps, lon_gps)
        
        direccion = st.text_input("📍 Ingresá tu dirección", value=dir_placeholder if usar_gps else "")

    radio_km = st.slider("📏 Radio de búsqueda (km)", 0.5, 5.0, 1.5)
    
    if st.button("🔍 Buscar locales cercanos", use_container_width=True):
        lat_f, lon_f = None, None
        if usar_gps and posicion_gps:
            lat_f, lon_f = posicion_gps['coords']['latitude'], posicion_gps['coords']['longitude']
        elif direccion:
            try:
                res = get_geocoder().geocode(f"{direccion}, {ciudad_sel}, Argentina")
                if res: 
                    lat_f, lon_f = res.latitude, res.longitude
            except: 
                pass

        if lat_f:
            df_ciudad["DIST_KM"] = df_ciudad.apply(lambda r: geodesic((lat_f, lon_f), (r["LAT"], r["LONG"])).km, axis=1)
            res = df_ciudad[df_ciudad["DIST_KM"] <= radio_km].sort_values("DIST_KM")
            
            if not res.empty:
                st.dataframe(res[["CAFE", "UBICACION", "TOSTADOR"]], use_container_width=True)
                
                # Mapa con color café oscuro
                view = pdk.ViewState(latitude=lat_f, longitude=lon_f, zoom=14)
                layer = pdk.Layer(
                    "ScatterplotLayer", 
                    res, 
                    get_position=["LONG", "LAT"],
                    get_color=[75, 56, 50, 200], 
                    get_radius=40, 
                    radius_min_pixels=4, 
                    pickable=True
                )
                st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip={"text": "{CAFE}"}))
            else: 
                st.warning("Nada en este radio.")
        else: 
            st.error("No se pudo detectar ubicación.")

# --- TAB 2: TOSTADORES ---
with tabs[1]:
    ciudad_tost = st.selectbox("🏙️ Filtrar tostadores por ciudad", ["Todas"] + list(GID_CAFES.keys()))
    tostadores = cargar_tostadores()
    
    if ciudad_tost != "Todas":
        tostadores = tostadores[tostadores["CIUDAD"].str.contains(ciudad_tost, case=False)]
    
    for i in range(0, len(tostadores), 3):
        cols = st.columns(3)
        for j, (_, t) in enumerate(tostadores.iloc[i:i+3].iterrows()):
            with cols[j]:
                st.markdown(f"""
                    <div class="tostador-card">
                        <div>
                            <div class="tostador-title">☕ {t['TOSTADOR']}</div>
                            <p style='font-size: 0.8rem; color: #BE8C63; font-weight: 600;'>🌱 {t['VARIEDADES']}</p>
                            <p class="tostador-desc">{t['DESCRIPCION']}</p>
                        </div>
                        <a class="ig-btn" href="{t['INSTAGRAM']}" target="_blank">VER INSTAGRAM</a>
                    </div>
                """, unsafe_allow_html=True)

# --- TAB 3: BUSCAR POR NOMBRE ---
with tabs[2]:
    st.subheader("🔍 Buscador inteligente")
    lista_nombres = sorted(df_total["CAFE"].unique())
    nombre_sel = st.selectbox("Seleccioná o escribí el nombre del café", [""] + lista_nombres)
    
    if nombre_sel:
        resultado = df_total[df_total["CAFE"] == nombre_sel]
        st.success(f"Encontrado en {resultado['CIUDAD_REF'].iloc[0]}")
        st.dataframe(resultado[["CAFE", "UBICACION", "TOSTADOR", "CIUDAD_REF"]], use_container_width=True)

# --- TAB 4: MAPA FEDERAL ---
with tabs[3]:
    st.subheader("🇦🇷 Mapa Federal")
    view_arg = pdk.ViewState(latitude=-38.41, longitude=-63.61, zoom=4)
    layer_fed = pdk.Layer(
        "ScatterplotLayer", 
        df_total, 
        get_position=["LONG", "LAT"],
        get_color=[190, 140, 99, 180], 
        get_radius=30, 
        radius_min_pixels=3, 
        pickable=True
    )
    st.pydeck_chart(pdk.Deck(layers=[layer_fed], initial_view_state=view_arg, tooltip={"text": "{CAFE}"}))
