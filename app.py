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
st.set_page_config(
    page_title="Buscador de Cafés",
    page_icon="☕",
    layout="wide"
)

st.title("☕ Buscador de Cafés en Argentina")

# =========================
# GOOGLE SHEETS CONFIG
# =========================
SPREADSHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

GID_CAFES = {
    "Mar del Plata": "0",
    "Buenos Aires": "1296176686",
    "La Plata": "208452991",
    "Córdoba": "1250014567",
    "Rosario": "1691979590",
}

GID_TOSTADORES = "1590442133"

def sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"

# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=600)
def cargar_cafes(gid):
    try:
        df = pd.read_csv(sheet_url(gid), dtype=str)
    except:
        df = pd.read_csv("Cafes.csv", dtype=str)

    df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", ".", regex=False), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].str.replace(",", ".", regex=False), errors="coerce")

    df = df.dropna(subset=["LAT", "LONG"])
    df = df[(df["LAT"].between(-90, 90)) & (df["LONG"].between(-180, 180))]
    return df

@st.cache_data(ttl=600)
def cargar_todos_los_cafes():
    dfs = []
    for ciudad, gid in GID_CAFES.items():
        try:
            df = cargar_cafes(gid)
            df["CIUDAD"] = ciudad
            dfs.append(df)
        except:
            pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocodificar(direccion, ciudad):
    geo = get_geocoder()
    try:
        loc = geo.geocode(f"{direccion}, {ciudad}, Argentina")
        return (loc.latitude, loc.longitude) if loc else None
    except:
        return None

def cafes_en_radio(df, coords, radio_km):
    df = df.copy()
    df["DIST_KM"] = df.apply(
        lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
        axis=1
    )
    return df[df["DIST_KM"] <= radio_km]

# =========================
# CONTADOR GLOBAL GRANDE
# =========================
todos = cargar_todos_los_cafes()
total = len(todos)

st.markdown(f"""
<div style="display:flex;justify-content:center;margin:40px 0;">
    <div style="text-align:center;padding:30px 60px;
        background:linear-gradient(135deg,#f0e1cf,#fdf8f2);
        border-radius:20px;border:2px solid #5f3512;
        box-shadow:0 6px 18px rgba(0,0,0,0.08);">
        <div style="font-size:3.5rem;font-weight:800;color:#5f3512;">
            {total}
        </div>
        <div style="font-size:1.1rem;color:#7a4b22;">
            CAFETERÍAS REGISTRADAS
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================
# MAPA NACIONAL
# =========================
st.markdown("## 🗺️ Mapa Nacional de Cafeterías")

if not todos.empty:
    df_map = todos.rename(columns={"LAT": "lat", "LONG": "lon"})
    
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["lon", "lat"],
        get_radius=6000,
        get_fill_color=[120, 60, 20, 140],
        pickable=True,
    )

    view_state = pdk.ViewState(latitude=-38.4161, longitude=-63.6167, zoom=4)

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "{CAFE}\n{CIUDAD}"}
    )

    st.pydeck_chart(deck, use_container_width=True)

# =========================
# SIDEBAR TELEGRAM
# =========================
with st.sidebar:
    st.header("💡 Reportar café")

    with st.form("form_sugerencia"):
        nombre = st.text_input("Nombre")
        direccion = st.text_input("Dirección")
        ciudad = st.selectbox("Ciudad", list(GID_CAFES.keys()))
        enviar = st.form_submit_button("Enviar")

        if enviar:
            try:
                TOKEN = st.secrets["TELEGRAM_TOKEN"]
                CHAT = st.secrets["CHAT_ID"]

                msg = f"Nuevo café:\n{nombre}\n{direccion}\n{ciudad}"
                url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                requests.post(url, data={"chat_id": CHAT, "text": msg})
                st.success("Enviado!")
            except:
                st.error("Error enviando a Telegram")

# =========================
# BUSCADOR
# =========================
st.markdown("---")
st.header("🔍 Buscar cafés cercanos")

ciudad = st.selectbox("Ciudad", list(GID_CAFES.keys()))
cafes = cargar_cafes(GID_CAFES[ciudad])

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
    else:
        st.error("No se pudo detectar ubicación")

if direccion and not coords:
    coords = geocodificar(direccion, ciudad)

radio = st.slider("Radio km", 0.5, 5.0, 2.0)

if coords:
    resultado = cafes_en_radio(cafes, coords, radio)
    resultado = resultado.sort_values("DIST_KM")

    st.subheader(f"{len(resultado)} cafés encontrados")

    if not resultado.empty:

        resultado["MAPS"] = resultado.apply(
            lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
            axis=1
        )

        st.dataframe(
            resultado[["CAFE","UBICACION","TOSTADOR","MAPS"]],
            column_config={
                "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Abrir")
            },
            use_container_width=True
        )

        df_map = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})

        layer_cafes = pdk.Layer(
            "ScatterplotLayer",
            data=df_map,
            get_position=["lon", "lat"],
            get_radius=100,
            get_fill_color=[200, 30, 0, 180],
            pickable=True,
        )

        layer_user = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"lat": coords[0], "lon": coords[1]}]),
            get_position=["lon", "lat"],
            get_radius=150,
            get_fill_color=[0,120,255,220]
        )

        view_state = pdk.ViewState(latitude=coords[0], longitude=coords[1], zoom=14)

        deck = pdk.Deck(
            layers=[layer_cafes, layer_user],
            initial_view_state=view_state,
            tooltip={"text": "{CAFE}\n{UBICACION}"}
        )

        st.pydeck_chart(deck, use_container_width=True)
