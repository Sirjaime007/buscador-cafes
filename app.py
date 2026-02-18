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

BASE_URL = "https://docs.google.com/spreadsheets/d/10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

CIUDADES = {
    "Mar del Plata": "0",
    "La Plata": "2035362762",
    "Buenos Aires": "1484696705"
}

# =========================
# CARGA CAFÉS
# =========================
@st.cache_data(ttl=300)
def cargar_cafes(gid):
    url = f"{BASE_URL}/export?format=csv&gid={gid}"
    df = pd.read_csv(url, dtype=str).fillna("")

    df.columns = df.columns.str.strip().str.upper()

    for col in ["LAT", "LONG"]:
        df[col] = (
            df[col]
            .str.replace(",", ".", regex=False)
            .astype(float)
        )

    df = df[
        df["LAT"].between(-90, 90) &
        df["LONG"].between(-180, 180)
    ]

    return df


# =========================
# CARGA TOSTADORES (GLOBAL)
# =========================
@st.cache_data(ttl=300)
def cargar_tostadores():
    url = f"{BASE_URL}/export?format=csv&gid=1590442133"
    df = pd.read_csv(url, dtype=str).fillna("")
    df.columns = df.columns.str.strip().str.upper()
    return df


# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)


def geocodificar(direccion, ciudad):
    geo = get_geocoder()
    loc = geo.geocode(f"{direccion}, {ciudad}, Argentina")
    if loc:
        return loc.latitude, loc.longitude
    return None


# =========================
# UI SUPERIOR
# =========================
ciudad = st.selectbox("🌎 Ciudad", list(CIUDADES.keys()))
cafes = cargar_cafes(CIUDADES[ciudad])
tostadores = cargar_tostadores()

tabs = st.tabs(["☕ Cafés", "🏷️ Tostadores"])

# =========================
# TAB CAFÉS
# =========================
with tabs[0]:
    direccion = st.text_input("📍 Dirección", value="Av. Colón 1500")
    radio_km = st.slider("📏 Radio de búsqueda (km)", 0.5, 5.0, 2.0, 0.5)

    tostadores_filtro = ["Todos"] + sorted(cafes["TOSTADOR"].unique())
    filtro_tostador = st.selectbox("🏷️ Filtrar por tostador", tostadores_filtro)

    buscar = st.button("🔍 Buscar cafés")

    if buscar:
        coords = geocodificar(direccion, ciudad)

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
            st.warning("No se encontraron cafés con esos filtros")
            st.stop()

        # ---- distancia texto ----
        resultado["DISTANCIA"] = resultado["DIST_KM"].apply(
            lambda d: f"{int(d*1000)} m" if d < 1 else f"{d:.2f} km"
        )

        resultado["MAPS"] = resultado.apply(
            lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
            axis=1
        )

        st.subheader(f"☕ Cafés encontrados ({len(resultado)})")

        st.dataframe(
            resultado[["CAFE", "UBICACION", "TOSTADOR", "DISTANCIA", "MAPS"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "MAPS": st.column_config.LinkColumn(
                    "Abrir en Maps",
                    display_text="📍 Google Maps"
                )
            }
        )

        # =========================
        # MAPA – HEATMAP LIGHT
        # =========================
        st.subheader("🗺️ Mapa")

        map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()

        min_d = map_df["DIST_KM"].min()
        max_d = map_df["DIST_KM"].max()

        def heat_color(d):
            if max_d == min_d:
                return [0, 200, 0, 220]
            ratio = (d - min_d) / (max_d - min_d)
            r = int(255 * ratio)
            g = int(200 * (1 - ratio))
            return [r, g, 0, 200]

        map_df["color"] = map_df["DIST_KM"].apply(heat_color)

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
            data=pd.DataFrame([{"lat": coords[0], "lon": coords[1]}]),
            get_position=["lon", "lat"],
            get_radius=130,
            get_fill_color=[0, 120, 255, 220]
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
                "text": "{CAFE}\n{UBICACION}\nDistancia: {DISTANCIA}"
            }
        )

        st.pydeck_chart(deck, use_container_width=True)


# =========================
# TAB TOSTADORES
# =========================
with tabs[1]:
    st.subheader("🏷️ Tostadores")

    tostadores_ciudad = tostadores[
        (tostadores["CIUDAD"] == "") |
        (tostadores["CIUDAD"].str.contains(ciudad, case=False, na=False))
    ]

    for _, r in tostadores_ciudad.iterrows():
        st.markdown(f"### ☕ {r['TOSTADOR']}")
        if r.get("INSTAGRAM"):
            st.markdown(f"📸 [Instagram]({r['INSTAGRAM']})")
        if r.get("VARIEDADES"):
            st.write(f"🌱 Variedades: {r['VARIEDADES']}")
        st.divider()
