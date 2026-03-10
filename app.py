import streamlit as st
import pandas as pd
from geopy.geocoders import ArcGIS, Nominatim
from geopy.distance import geodesic
import pydeck as pdk
import requests
from streamlit_js_eval import get_geolocation
import random
import urllib.parse

# =========================
# CONFIG APP Y ESTILOS
# =========================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    html, body, h1, h2, h3, h4, h5, h6, p, label, span, div { 
        font-family: 'Inter', sans-serif; 
    }
    .material-symbols-rounded, .material-icons {
        font-family: 'Material Symbols Rounded' !important;
    }
    
    .stApp { background-color: #FDF8F5; }
    
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
    
    .wpp-btn {
        background: #25D366;
        color: #FFFFFF !important;
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
    .wpp-btn:hover { background: #128C7E; }
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
        
        # Escudo protector
        if "INSTAGRAM" not in df.columns:
            df["INSTAGRAM"] = ""
            
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
        df["CIUDAD"] = ciudad
        dfs.append(df)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()

# =========================
# FUNCIONES SATELITALES Y MATEMÁTICAS
# =========================
@st.cache_resource
def get_geocoder(): 
    return ArcGIS(timeout=10)

@st.cache_resource
def get_osm_geocoder(): 
    return Nominatim(user_agent="cafes_app_arg_v4", timeout=10)

def obtener_calle(lat, lon):
    try: 
        return get_geocoder().reverse((lat, lon)).address
    except: 
        return "Ubicación detectada"

def calcular_cuadras(km, ciudad):
    metros = km * 1000
    divisor = 87 if ciudad == "Mar del Plata" else 100
    cuadras = int(metros / divisor)
    if cuadras == 0:
        return "A pasos"
    elif cuadras == 1:
        return "1 cuadra"
    else:
        return f"{cuadras} cuadras"

def buscar_coordenadas_inteligente(direccion, ciudad_sel, df_ciudad):
    if not direccion or direccion.strip() == "":
        return None, None, None
        
    dir_limpia = direccion.strip().lower()
    
    match_local = df_ciudad[df_ciudad["UBICACION"].str.lower().str.contains(dir_limpia, na=False)]
    if not match_local.empty:
        lat = match_local.iloc[0]["LAT"]
        lon = match_local.iloc[0]["LONG"]
        nom = match_local.iloc[0]["CAFE"]
        ubi = match_local.iloc[0]["UBICACION"]
        return lat, lon, f"{ubi} (Local: {nom})"
        
    variantes_busqueda = [
        f"{direccion}, {ciudad_sel}, Argentina",
        f"{direccion}, Buenos Aires, Argentina",
        f"{direccion}, Argentina"
    ]
    
    geo = get_geocoder()
    for query in variantes_busqueda:
        try:
            res = geo.geocode(query)
            if res: return res.latitude, res.longitude, res.address
        except: pass
        
    geo_osm = get_osm_geocoder()
    for query in variantes_busqueda:
        try:
            res = geo_osm.geocode(query)
            if res: return res.latitude, res.longitude, res.address
        except: pass
        
    return None, None, None

def generar_link_whatsapp(nombre, ubicacion, lat, lon):
    map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    texto = f"Vamos a tomar un cafe a {nombre}, queda en {ubicacion}: {map_url}"
    texto_codificado = urllib.parse.quote(texto)
    return f"https://api.whatsapp.com/send?text={texto_codificado}"

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
    
    placeholders = {
        "Mar del Plata": "Ej: Av. Colón 1500",
        "Buenos Aires": "Ej: Av. Santa Fe 3000, Palermo",
        "La Plata": "Ej: Av 7 800, Tolosa",
        "Córdoba": "Ej: Av. General Paz 150",
        "Rosario": "Ej: Bulevar Oroño 500"
    }
    texto_ejemplo = placeholders.get(ciudad_sel, "Ej: San Martín 100")
    
    if "dir_memoria" not in st.session_state:
        st.session_state.dir_memoria = ""
    if "coords_memoria" not in st.session_state:
        st.session_state.coords_memoria = None

    posicion_gps = get_geolocation()
    col_input, col_gps = st.columns([3, 1])
    
    with col_input:
        direccion = st.text_input("📍 Ingresá tu dirección (Escribí y tocá Enter)", value=st.session_state.dir_memoria, placeholder=texto_ejemplo)
        if direccion != st.session_state.dir_memoria:
            st.session_state.dir_memoria = direccion
            st.session_state.coords_memoria = None

    with col_gps:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("📍 Usar mi ubicación", use_container_width=True):
            if posicion_gps and 'coords' in posicion_gps:
                lat_gps = posicion_gps['coords']['latitude']
                lon_gps = posicion_gps['coords']['longitude']
                st.session_state.coords_memoria = (lat_gps, lon_gps)
                calle_gps = obtener_calle(lat_gps, lon_gps)
                st.session_state.dir_memoria = calle_gps
                st.rerun()
            else:
                st.warning("Esperando señal GPS o no diste permiso.")

    radio_km = st.slider("📏 Radio de búsqueda (km)", 0.5, 5.0, 1.5)
    
    col_btn_buscar, col_btn_rec = st.columns(2)
    btn_buscar = col_btn_buscar.button("🔍 Buscar locales cercanos", use_container_width=True)
    btn_recomendar = col_btn_rec.button("🎯 Recomendar café", use_container_width=True)
    
    if btn_buscar or btn_recomendar:
        lat_f, lon_f = None, None
        
        if st.session_state.coords_memoria and direccion == st.session_state.dir_memoria:
            lat_f, lon_f = st.session_state.coords_memoria
        elif direccion:
            lat_f, lon_f, _ = buscar_coordenadas_inteligente(direccion, ciudad_sel, df_ciudad)

        if lat_f:
            df_ciudad["DIST_KM"] = df_ciudad.apply(lambda r: geodesic((lat_f, lon_f), (r["LAT"], r["LONG"])).km, axis=1)
            
            if btn_buscar:
                res_busqueda = df_ciudad[df_ciudad["DIST_KM"] <= radio_km].sort_values("DIST_KM")
                if not res_busqueda.empty:
                    res_busqueda["CUADRAS"] = res_busqueda["DIST_KM"].apply(lambda km: calcular_cuadras(km, ciudad_sel))
                    res_busqueda["MAPS"] = res_busqueda.apply(lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}", axis=1)
                    
                    res_busqueda["WHATSAPP"] = res_busqueda.apply(lambda r: generar_link_whatsapp(r['CAFE'], r['UBICACION'], r['LAT'], r['LONG']), axis=1)
                    
                    res_busqueda = res_busqueda.reset_index(drop=True)
                    
                    st.dataframe(
                        res_busqueda[["CAFE", "UBICACION", "INSTAGRAM", "CUADRAS", "MAPS", "WHATSAPP"]], 
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "INSTAGRAM": st.column_config.LinkColumn("Instagram", display_text="📱 Ver Perfil"),
                            "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Abrir en mapa"),
                            "WHATSAPP": st.column_config.LinkColumn("WhatsApp", display_text="💬 Invitar")
                        }
                    )
                    
                    view = pdk.ViewState(latitude=lat_f, longitude=lon_f, zoom=14)
                    layer_cafes = pdk.Layer(
                        "ScatterplotLayer", 
                        res_busqueda, 
                        get_position=["LONG", "LAT"],
                        get_color=[190, 130, 90, 220], 
                        get_radius=25, 
                        radius_min_pixels=3, 
                        pickable=True
                    )
                    layer_usuario = pdk.Layer(
                        "ScatterplotLayer",
                        pd.DataFrame([{"LAT": lat_f, "LONG": lon_f}]),
                        get_position=["LONG", "LAT"],
                        get_color=[30, 136, 229, 255],
                        get_radius=40,
                        radius_min_pixels=6,
                        pickable=False
                    )
                    st.pydeck_chart(pdk.Deck(layers=[layer_cafes, layer_usuario], initial_view_state=view, tooltip={"text": "{CAFE}"}))
                else: 
                    st.warning("No encontramos locales en este radio. ¡Probá ampliando el rango o verificá el punto detectado!")
            
            elif btn_recomendar:
                res_rec = df_ciudad[df_ciudad["DIST_KM"] <= 0.5]
                if not res_rec.empty:
                    elegido = res_rec.sample(1).iloc[0]
                    dist_txt = calcular_cuadras(elegido['DIST_KM'], ciudad_sel)
                    map_link = f"https://www.google.com/maps/search/?api=1&query={elegido['LAT']},{elegido['LONG']}"
                    wpp_link = generar_link_whatsapp(elegido['CAFE'], elegido['UBICACION'], elegido['LAT'], elegido['LONG'])
                    ig_link = elegido.get('INSTAGRAM', '#')
                    
                    # AQUÍ SE CORRIGIÓ LA SANGRÍA DEL HTML
                    st.markdown(f"""
<div class="tostador-card" style="border: 2px solid #BE8C63; text-align: center; max-width: 500px; margin: 0 auto;">
    <h3 style="color: #BE8C63; margin-bottom: 15px;">🎯 Recomendación del momento</h3>
    <h2 style="color: #4B3832; margin-bottom: 5px;">{elegido['CAFE']}</h2>
    <p style="font-size: 1.1rem; margin-bottom: 15px;">📍 {elegido['UBICACION']} <strong>({dist_txt})</strong></p>
    
    <div style="display: flex; gap: 10px; justify-content: center; margin-top: 10px; flex-wrap: wrap;">
        <a class="ig-btn" href="{ig_link}" target="_blank" style="flex: 1; margin-top: 0; min-width: 120px;">📱 Instagram</a>
        <a class="ig-btn" href="{map_link}" target="_blank" style="flex: 1; margin-top: 0; min-width: 120px;">📍 Llevame ahí</a>
        <a class="wpp-btn" href="{wpp_link}" target="_blank" style="flex: 1; margin-top: 0; min-width: 120px;">💬 Invitar</a>
    </div>
</div>
""", unsafe_allow_html=True)
                else:
                    st.warning("No tenés cafeterías a menos de 5 cuadras para recomendarte. ☹️ ¡Probá buscando locales en general!")

        else: 
            st.error("❌ El satélite no pudo encontrar esa dirección. Asegurate de incluir el barrio o usar una calle principal.")

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
                # AQUÍ TAMBIÉN SE CORRIGIÓ LA SANGRÍA
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
    
    total_cafeterias = len(df_total)
    texto_todas = f"Todas ({total_cafeterias})"
    
    opciones_filtro_ciudad = [texto_todas]
    mapa_filtro_ciudad = {texto_todas: "Todas"}
    
    for c in sorted(df_total["CIUDAD"].dropna().unique()):
        cantidad = len(df_total[df_total["CIUDAD"] == c])
        texto_opcion = f"{c} ({cantidad})"
        opciones_filtro_ciudad.append(texto_opcion)
        mapa_filtro_ciudad[texto_opcion] = c
        
    ciudad_filtro_sel = st.selectbox("🏙️ Filtrar lista por ciudad", opciones_filtro_ciudad)
    ciudad_real_elegida = mapa_filtro_ciudad[ciudad_filtro_sel]
    
    if ciudad_real_elegida == "Todas":
        df_nombres_filtrado = df_total
    else:
        df_nombres_filtrado = df_total[df_total["CIUDAD"] == ciudad_real_elegida]
        
    lista_nombres_filtrada = sorted(df_nombres_filtrado["CAFE"].dropna().unique())
    nombre_sel = st.selectbox("☕ Seleccioná o escribí el nombre del café", [""] + lista_nombres_filtrada)
    
    if nombre_sel:
        resultado = df_nombres_filtrado[df_nombres_filtrado["CAFE"] == nombre_sel].copy()
        resultado = resultado.reset_index(drop=True)
        resultado["MAPS"] = resultado.apply(lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}", axis=1)
        resultado["WHATSAPP"] = resultado.apply(lambda r: generar_link_whatsapp(r['CAFE'], r['UBICACION'], r['LAT'], r['LONG']), axis=1)
        
        if len(resultado) > 1:
            st.success(f"Encontramos {len(resultado)} sucursales de **{nombre_sel}**")
        else:
            st.success(f"Encontrado en {resultado['CIUDAD'].iloc[0]}")
            
        st.dataframe(
            resultado[["CAFE", "UBICACION", "INSTAGRAM", "CIUDAD", "MAPS", "WHATSAPP"]], 
            use_container_width=True,
            hide_index=True,
            column_config={
                "INSTAGRAM": st.column_config.LinkColumn("Instagram", display_text="📱 Ver Perfil"),
                "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Abrir en mapa"),
                "WHATSAPP": st.column_config.LinkColumn("WhatsApp", display_text="💬 Invitar")
            }
        )

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
