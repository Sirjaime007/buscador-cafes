import streamlit as st
import pandas as pd
import pydeck as pdk

# ======================
# CONFIG
# ======================
st.set_page_config(page_title="Buscador de Cafés", layout="wide")

SPREADSHEET_ID = "TU_SPREADSHEET_ID_AQUI"

GID_CAFES = {
    "Buenos Aires": "0",
    "La Plata": "123456789"
}

GID_TOSTADORES = "1590442133"

# ======================
# HELPERS
# ======================
def sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"

@st.cache_data(ttl=600)
def cargar_cafes(gid):
    df = pd.read_csv(sheet_url(gid), dtype=str)

    df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", "."), errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"].str.replace(",", "."), errors="coerce")

    df = df.dropna(subset=["LAT", "LON"])
    return df

@st.cache_data(ttl=600)
def cargar_tostadores():
    df = pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str)

    df["LAT"] = pd.to_numeric(df["LAT"].str.replace(",", "."), errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"].str.replace(",", "."), errors="coerce")

    df = df.dropna(subset=["LAT", "LON", "CIUDAD"])
    return df

# ======================
# UI
# ======================
st.title("☕ Buscador de Cafés y Tostadores")

ciudad = st.selectbox("Elegí una ciudad", list(GID_CAFES.keys()))

cafes = cargar_cafes(GID_CAFES[ciudad])
tostadores = cargar_tostadores()
tostadores = tostadores[tostadores["CIUDAD"].str.contains(ciudad, case=False, na=False)]

# ======================
# MAP DATA
# ======================
map_df = pd.concat([
    cafes.assign(tipo="Café"),
    tostadores.assign(tipo="Tostador")
])

map_df["r"] = map_df["tipo"].map({"Café": 200, "Tostador": 255})
map_df["g"] = map_df["tipo"].map({"Café": 100, "Tostador": 50})
map_df["b"] = map_df["tipo"].map({"Café": 0, "Tostador": 50})
map_df["a"] = 160

# ======================
# HEATMAP LIGHT
# ======================
heatmap = pdk.Layer(
    "HeatmapLayer",
    data=map_df,
    get_position='[LON, LAT]',
    aggregation=pdk.types.String("MEAN"),
    intensity=0.6,
    radiusPixels=60,
    threshold=0.03
)

points = pdk.Layer(
    "ScatterplotLayer",
    data=map_df,
    get_position='[LON, LAT]',
    get_fill_color='[r, g, b, a]',
    get_radius=70,
    pickable=True
)

view = pdk.ViewState(
    latitude=map_df["LAT"].mean(),
    longitude=map_df["LON"].mean(),
    zoom=12,
)

st.pydeck_chart(
    pdk.Deck(
        layers=[heatmap, points],
        initial_view_state=view,
        tooltip={"text": "{NOMBRE}\n{tipo}"}
    )
)

# ======================
# TABLES
# ======================
st.subheader("📍 Cafés")
st.dataframe(cafes)

st.subheader("🔥 Tostadores")
st.dataframe(tostadores)
