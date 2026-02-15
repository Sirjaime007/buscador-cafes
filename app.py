import streamlit as st
import pandas as pd
from datetime import datetime
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk
import uuid

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Buscador de Cafés",
    page_icon="☕",
    layout="wide"
)

CUADRA_METROS = 87
CAFES_CSV = "Cafes.csv"
VOTES_SHEET = "Votos Cafes"

# =========================
# GOOGLE SHEETS
# =========================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client.open(VOTES_SHEET).sheet1

def guardar_voto(cafe, puntaje):
    sheet = get_sheet()
    sheet.append_row([
        datetime.utcnow().isoformat(),
        cafe,
        float(puntaje)
    ])

def cargar_votos():
    try:
        rows = get_sheet().get_all_records()
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["timestamp", "cafe", "puntaje"])

# =========================
# CARGA CAFÉS
# =========================
@st.cache_data
def load_cafes():
    df = pd.read_csv(CAFES_CSV)
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"], errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"], errors="coerce")
    return df.dropna(subset=["LAT", "LONG"])

cafes = load_cafes()

# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode(address):
    loc = get_geocoder().geocode(
        f"{address}, Mar del Plata, Buenos Aires, Argentina"
    )
    if loc:
        return loc.latitude, loc.longitude
    return None

# =========================
# SESSION
# =========================
if "voter_id" not in st.session_state:
    st.session_state.voter_id = str(uuid.uuid4())

# =========================
# UI
# =========================
st.title("☕ Buscador de Cafés")
st.caption("Buscá cafés cercanos, miralos en el mapa y votá tu favorito")

col1, col2 = st.columns([3, 1])
with col1:
    direccion = st.text_input("Dirección", "Av. Colón 1500")
with col2:
    radio_km = st.number_input("Radio (km)", 0.1, 10.0, 2.0, 0.1)

buscar = st.button("🔎 Buscar cafés", use_container_width=True)

# =========================
# BUSCAR
# =========================
if buscar:
    coord = geocode(direccion)
    if not coord:
        st.error("No se pudo encontrar la dirección")
        st.stop()

   cafes_calc["DIST_KM"] = [
    geodesic(coord, (lat, lon)).km
    for lat, lon in zip(cafes_calc["LAT"], cafes_calc["LONG"])
]
    )
    cafes_calc["CUADRAS"] = cafes_calc["DIST_KM"] * 1000 / CUADRA_METROS

    resultado = cafes_calc[cafes_calc["DIST_KM"] <= radio_km].sort_values("DIST_KM")

    st.subheader("📍 Cafés cercanos")

    if resultado.empty:
        st.info("No hay cafés en ese radio")
        st.stop()

    st.dataframe(
        resultado[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS"]],
        use_container_width=True,
        hide_index=True
    )

    # =========================
    # MAPA
    # =========================
    st.subheader("🗺️ Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})

    layer_cafes = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=60,
        radius_units="meters",
        get_fill_color=[200, 30, 0, 180],
        pickable=True
    )

    layer_user = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord[0], "lon": coord[1]}]),
        get_position=["lon", "lat"],
        get_radius=90,
        radius_units="meters",
        get_fill_color=[0, 120, 255, 220]
    )

    deck = pdk.Deck(
        layers=[layer_cafes, layer_user],
        initial_view_state=pdk.ViewState(
            latitude=coord[0],
            longitude=coord[1],
            zoom=14
        ),
        getTooltip="""
<b>{CAFE}</b><br/>
{UBICACION}<br/>
Puntaje: {PUNTAJE}
"""
    )

    st.pydeck_chart(deck, use_container_width=True)

# =========================
# VOTACIÓN
# =========================
st.subheader("⭐ Votá tu café favorito")

with st.form("votar"):
    cafe_sel = st.selectbox("Café", cafes["CAFE"].unique())
    puntaje = st.slider("Puntaje", 1.0, 10.0, 8.0, 0.5)
    enviar = st.form_submit_button("Votar")

    if enviar:
        guardar_voto(cafe_sel, puntaje)
        st.success("¡Voto guardado! ☕")

# =========================
# RANKING
# =========================
st.subheader("🏆 Ranking")

votes = cargar_votos()
if votes.empty:
    st.info("Todavía no hay votos")
else:
    ranking = (
        votes.groupby("cafe")["puntaje"]
        .agg(["count", "mean"])
        .reset_index()
        .rename(columns={
            "cafe": "CAFE",
            "count": "Votos",
            "mean": "Promedio"
        })
        .sort_values(["Promedio", "Votos"], ascending=False)
    )
    ranking["Promedio"] = ranking["Promedio"].round(2)

    st.dataframe(ranking, use_container_width=True, hide_index=True)
