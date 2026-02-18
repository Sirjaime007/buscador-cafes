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

st.title("☕ Buscador de Cafés")

# =========================
# CIUDADES / GID
# =========================
SHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

CIUDADES = {
    "Mar del Plata": {
        "gid": "0",
        "geo": "Mar del Plata, Buenos Aires, Argentina"
    },
    "La Plata": {
        "gid": "208452991",
        "geo": "La Plata, Buenos Aires, Argentina"
    },
    "Buenos Aires": {
        "gid": "1296176686",
        "geo": "Buenos Aires, Argentina"
    }
}

# =========================
# UI - CIUDAD
# =========================
ciudad = st.selectbox("🏙️ Ciudad", list(CIUDADES.keys()))

# =========================
# CARGA GOOGLE SHEETS
# =========================
@st.cache_data(ttl=300)
def cargar_cafes(gid):
    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{SHEET_ID}/export?format=csv&gid={gid}"
    )

    df = pd.read_csv(url, dtype=str)

    for col in ["LAT", "LONG"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["LAT", "LONG"])
    return df

cafes = cargar_cafes(CIUDADES[ciudad]["gid"])

if cafes.empty:
    st.warning("No hay datos para esta ciudad")
    st.stop()

# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocodificar(direccion, ciudad_geo):
    geo = get_geocoder()
    loc = geo.geocode(f"{direccion}, {ciudad_geo}")
    if loc:
        return loc.latitude, loc.longitude
    return None

# =========================
# UI - FILTROS
# =========================
direccion = st.text_input(
    "📍 Dirección",
    placeholder="Ej: Av. Colón 1500"
)

radio_km = st.slider(
    "📏 Radio de búsqueda (km)",
    0.5, 5.0, 2.0, 0.5
)

tostadores = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
filtro_tostador = st.selectbox("🏷️ Tostador", tostadores)

buscar = st.button("🔍 Buscar cafés")

# =========================
# BUSQUEDA
# =========================
if buscar:
    coords = geocodificar(direccion, CIUDADES[ciudad]["geo"])

    if coords is None:
        st.error("No se pudo geocodificar la dirección 😕")
        st.stop()

    cafes_calc = cafes.copy()

    cafes_calc["DIST_KM"] = cafes_calc.apply(
        lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
        axis=1
    )

    resultado = cafes_calc[cafes_calc["DIST_KM"] <= radio_km]

    if filtro_tostador != "Todos":
        resultado = resultado[resultado["TOSTADOR"] == filtro_tostador]

    resultado = resultado.sort_values("DIST_KM")

    if resultado.empty:
        st.warning("No se encontraron cafés con esos filtros ☹️")
        st.stop()

    # =========================
    # TABLA
    # =========================
    resultado["DIST_TXT"] = resultado["DIST_KM"].apply(
        lambda km: f"{int(km*1000)} m" if km < 1 else f"{km:.2f} km"
    )

    resultado["MAPS"] = resultado.apply(
        lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
        axis=1
    )

    st.subheader(f"☕ Cafés encontrados en {ciudad} ({len(resultado)})")

    st.dataframe(
        resultado[["CAFE", "UBICACION", "TOSTADOR", "DIST_TXT", "MAPS"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "MAPS": st.column_config.LinkColumn(
                "Google Maps",
                display_text="📍 Abrir"
            )
        }
    )

    # =========================
    # MAPA
    # =========================
    st.subheader("🗺️ Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()

    map_df["color"] = [[200, 50, 50, 160]] * len(map_df)
    map_df.at[map_df.index[0], "color"] = [0, 200, 0, 220]

    layer_cafes = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=90,
        get_fill_color="color",
        pickable=True
    )

    layer_user = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{
            "lat": coords[0],
            "lon": coords[1]
        }]),
        get_position=["lon", "lat"],
        get_radius=130,
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
            "text": "{CAFE}\n{UBICACION}\nDistancia: {DIST_TXT}"
        }
    )

    st.pydeck_chart(deck, use_container_width=True)

