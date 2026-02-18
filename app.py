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
# SHEET CONFIG
# =========================
SHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"
GID_TOSTADORES = "1590442133"

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
# CARGA DATA
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

    return df.dropna(subset=["LAT", "LONG"])

@st.cache_data(ttl=300)
def cargar_tostadores():
    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{SHEET_ID}/export?format=csv&gid={GID_TOSTADORES}"
    )
    return pd.read_csv(url, dtype=str)

cafes = cargar_cafes(CIUDADES[ciudad]["gid"])
tostadores_df = cargar_tostadores()

if cafes.empty:
    st.warning("No hay datos de cafés para esta ciudad")
    st.stop()

# =========================
# TABS
# =========================
tab_busqueda, tab_tostadores = st.tabs(
    ["☕ Buscar cafés", "🔥 Tostadores"]
)

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
# TAB 1 - BUSQUEDA
# =========================
with tab_busqueda:
    direccion = st.text_input("📍 Dirección")
    radio_km = st.slider("📏 Radio (km)", 0.5, 5.0, 2.0, 0.5)

    tostadores = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
    filtro_tostador = st.selectbox("🏷️ Tostador", tostadores)

    buscar = st.button("🔍 Buscar cafés")

    if buscar:
        coords = geocodificar(direccion, CIUDADES[ciudad]["geo"])
        if coords is None:
            st.error("No se pudo geocodificar la dirección")
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
            st.warning("No se encontraron cafés")
            st.stop()

        resultado["DISTANCIA"] = resultado["DIST_KM"].apply(
            lambda km: f"{int(km*1000)} m" if km < 1 else f"{km:.2f} km"
        )

        resultado["MAPS"] = resultado.apply(
            lambda r: (
                "https://www.google.com/maps/search/?api=1"
                f"&query={r['LAT']},{r['LONG']}"
            ),
            axis=1
        )

        st.dataframe(
            resultado[["CAFE", "UBICACION", "TOSTADOR", "DISTANCIA", "MAPS"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "MAPS": st.column_config.LinkColumn(
                    "Maps", display_text="📍 Abrir"
                )
            }
        )

        st.subheader("🗺️ Mapa")

        map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()
        map_df["color"] = [[200, 50, 50, 160]] * len(map_df)
        map_df.at[map_df.index[0], "color"] = [0, 200, 0, 220]

        deck = pdk.Deck(
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=map_df,
                    get_position=["lon", "lat"],
                    get_radius=90,
                    get_fill_color="color",
                    pickable=True
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([{
                        "lat": coords[0],
                        "lon": coords[1]
                    }]),
                    get_position=["lon", "lat"],
                    get_radius=130,
                    get_fill_color=[0, 120, 255, 200]
                )
            ],
            initial_view_state=pdk.ViewState(
                latitude=coords[0],
                longitude=coords[1],
                zoom=14
            ),
            tooltip={
                "text": "{CAFE}\n{UBICACION}\nDistancia: {DISTANCIA}"
            }
        )

        st.pydeck_chart(deck, use_container_width=True)

# =========================
# TAB 2 - TOSTADORES
# =========================
with tab_tostadores:
    st.subheader("🔥 Tostadores")

    for _, tost in tostadores_df.iterrows():
        st.markdown(f"### ☕ {tost['TOSTADOR']}")

        col1, col2 = st.columns([1, 3])

        with col1:
            if pd.notna(tost.get("INSTAGRAM")):
                st.link_button("📸 Instagram", tost["INSTAGRAM"])

        with col2:
            if pd.notna(tost.get("DESCRIPCION")):
                st.write(tost["DESCRIPCION"])

            if pd.notna(tost.get("VARIEDADES")):
                st.markdown(f"**Variedades:** {tost['VARIEDADES']}")

        cafes_usan = cafes[
            cafes["TOSTADOR"] == tost["TOSTADOR"]
        ]["CAFE"].unique()

        if len(cafes_usan) > 0:
            st.markdown(
                "**Cafeterías que lo usan:** " +
                ", ".join(cafes_usan)
            )
        else:
            st.caption("No hay cafeterías registradas en esta ciudad")

        st.divider()
