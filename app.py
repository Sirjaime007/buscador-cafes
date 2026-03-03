import streamlit as st
import pandas as pd
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk
import requests
from streamlit_js_eval import get_geolocation

# =====================================
# CONFIG
# =====================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés en Argentina")

SPREADSHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

GID_CAFES = {
    "Mar del Plata": "0",
    "Buenos Aires": "1296176686",
    "La Plata": "208452991",
    "Córdoba": "1250014567",
    "Rosario": "1691979590",
}

GID_TOSTADORES = "1590442133"

def sheet_url(gid):
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"

# =====================================
# DATA
# =====================================
@st.cache_data(ttl=600)
def cargar_cafes(gid):
    df = pd.read_csv(sheet_url(gid), dtype=str)
    df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", "."), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["LAT", "LONG"])
    return df

@st.cache_data(ttl=600)
def cargar_tostadores():
    return pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str)

# =====================================
# PESTAÑAS
# =====================================
tab1, tab2, tab3 = st.tabs(["🔍 Buscar Cercanos", "🏷️ Buscar por Nombre", "☕ Tostadores"])

# =====================================
# TAB 1 - BUSCAR CERCANOS
# =====================================
with tab1:

    ciudad = st.selectbox("Ciudad", list(GID_CAFES.keys()))
    cafes = cargar_cafes(GID_CAFES[ciudad])

    tostadores_unicos = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
    filtro_tostador = st.selectbox("Filtrar por tostador", tostadores_unicos)

    col1, col2 = st.columns([3,1])

    with col1:
        direccion = st.text_input("Dirección")

    with col2:
        geo_btn = st.button("📡 Usar mi ubicación")

    coords = None

    if geo_btn:
        loc = get_geolocation()
        if loc and "coords" in loc:
            coords = (loc["coords"]["latitude"], loc["coords"]["longitude"])
            st.success("Ubicación detectada")

    if direccion and not coords:
        geo = ArcGIS(timeout=10)
        loc = geo.geocode(f"{direccion}, {ciudad}, Argentina")
        if loc:
            coords = (loc.latitude, loc.longitude)

    radio = st.slider("Radio km", 0.5, 5.0, 2.0)

    if coords:
        cafes["DIST"] = cafes.apply(
            lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
            axis=1
        )

        resultado = cafes[cafes["DIST"] <= radio]

        if filtro_tostador != "Todos":
            resultado = resultado[resultado["TOSTADOR"] == filtro_tostador]

        resultado = resultado.sort_values("DIST")

        st.subheader(f"{len(resultado)} cafés encontrados")

        if not resultado.empty:

            resultado["MAPS"] = resultado.apply(
                lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
                axis=1
            )

            st.dataframe(
                resultado[["CAFE","UBICACION","TOSTADOR","MAPS"]].reset_index(drop=True),
                column_config={
                    "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Abrir")
                },
                use_container_width=True
            )

            mapa_resultado = resultado.copy()
            user_coords = coords
        else:
            mapa_resultado = None
            user_coords = None
    else:
        mapa_resultado = None
        user_coords = None

# =====================================
# TAB 2 - BUSCAR POR NOMBRE
# =====================================
with tab2:

    ciudad2 = st.selectbox("Ciudad ", list(GID_CAFES.keys()), key="ciudad_nombre")
    cafes2 = cargar_cafes(GID_CAFES[ciudad2])

    nombre_busqueda = st.text_input("Nombre del café")

    if nombre_busqueda:
        resultado_nombre = cafes2[cafes2["CAFE"].str.contains(nombre_busqueda, case=False, na=False)]

        if not resultado_nombre.empty:
            st.dataframe(
                resultado_nombre[["CAFE","UBICACION","TOSTADOR"]].reset_index(drop=True),
                use_container_width=True
            )
        else:
            st.info("No se encontraron resultados.")

# =====================================
# TAB 3 - TOSTADORES
# =====================================
with tab3:
    tostadores = cargar_tostadores()
    st.dataframe(tostadores.reset_index(drop=True), use_container_width=True)

# =====================================
# REPORTE (SIDEBAR)
# =====================================
with st.sidebar:
    st.header("💡 Reportar Café")

    with st.form("reporte"):
        tipo = st.selectbox("Tipo de reporte", ["Nueva cafetería", "Modificación", "Cierre"])
        nombre = st.text_input("Nombre")
        direccion = st.text_input("Dirección")
        ciudad = st.selectbox("Ciudad", list(GID_CAFES.keys()), key="ciudad_reporte")
        comentarios = st.text_area("Comentarios")
        enviar = st.form_submit_button("Enviar")

        if enviar:
            try:
                TOKEN = st.secrets["TELEGRAM_TOKEN"]
                CHAT = st.secrets["CHAT_ID"]

                mensaje = f"""
📌 REPORTE CAFÉ

Tipo: {tipo}
Nombre: {nombre}
Dirección: {direccion}
Ciudad: {ciudad}

Comentarios:
{comentarios}
"""
                url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": CHAT, "text": mensaje})
                st.success("Reporte enviado")
            except:
                st.error("Error enviando reporte")

# =====================================
# MAPA ABAJO DEL TODO (PUNTOS PEQUEÑOS)
# =====================================
st.markdown("---")
st.header("🗺️ Mapa")

if "mapa_resultado" in locals() and mapa_resultado is not None:

    df_map = mapa_resultado.rename(columns={"LAT":"lat","LONG":"lon"})

    layer_cafes = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["lon","lat"],
        get_radius=1,
        radius_min_pixels=2,
        get_fill_color=[200,30,0,180],
        pickable=True,
    )

    layer_user = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": user_coords[0], "lon": user_coords[1]}]),
        get_position=["lon","lat"],
        get_radius=1,
        radius_min_pixels=4,
        get_fill_color=[0,120,255,220],
    )

    view_state = pdk.ViewState(
        latitude=user_coords[0],
        longitude=user_coords[1],
        zoom=14
    )

    deck = pdk.Deck(
        layers=[layer_cafes, layer_user],
        initial_view_state=view_state,
        tooltip={"text": "{CAFE}\n{UBICACION}"}
    )

    st.pydeck_chart(deck, use_container_width=True)
