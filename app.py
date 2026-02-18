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
CIUDADES = {
    "Mar del Plata": "0",
    "La Plata": "XXXXXXXX",       # <-- reemplazá
    "Buenos Aires": "YYYYYYYY"    # <-- reemplazá
}

BASE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"
)

# =========================
# CARGA CAFÉS (ROBUSTA)
# =========================
@st.cache_data(ttl=300)
def cargar_cafes(gid):
    url = f"{BASE_URL}/export?format=csv&gid={gid}"
    df = pd.read_csv(url, dtype=str).fillna("")

    for col in ["LAT", "LONG"]:
        df[col] = (
            df[col]
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # eliminar filas inválidas
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
    return pd.read_csv(url, dtype=str).fillna("")

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

tabs = st.tabs(["☕ Cafés", "🔥 Tostadores"])

# =====================================================
# ☕ TAB CAFÉS
# =====================================================
with tabs[0]:
    direccion = st.text_input(
        "📍 Dirección",
        value="Av. Colón 1500"
    )

    radio_km = st.slider(
        "📏 Radio de búsqueda (km)",
        0.5, 5.0, 2.0, 0.5
    )

    tostadores_lista = ["Todos"] + sorted(
        cafes["TOSTADOR"].dropna().unique()
    )

    filtro_tostador = st.selectbox(
        "🏷️ Filtrar por tostador",
        tostadores_lista
    )

    if st.button("🔍 Buscar cafés"):
        coords = geocodificar(direccion, ciudad)

        if not coords:
            st.error("No se pudo encontrar la dirección 😕")
            st.stop()

        df = cafes.copy()

        df["DIST_KM"] = df.apply(
            lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
            axis=1
        )

        df = df[df["DIST_KM"] <= radio_km]

        if filtro_tostador != "Todos":
            df = df[df["TOSTADOR"] == filtro_tostador]

        df = df.sort_values("DIST_KM")

        if df.empty:
            st.warning("No se encontraron cafés con esos filtros ☹️")
            st.stop()

        df["Distancia"] = df["DIST_KM"].apply(
            lambda km: f"{int(km * 1000)} m" if km < 1 else f"{km:.2f} km"
        )

        df["MAPS"] = df.apply(
            lambda r: (
                "https://www.google.com/maps/search/?api=1"
                f"&query={r['LAT']},{r['LONG']}"
            ),
            axis=1
        )

        st.dataframe(
            df[["CAFE", "UBICACION", "TOSTADOR", "Distancia", "MAPS"]],
            hide_index=True,
            use_container_width=True,
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
        map_df = df.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()
        map_df["color"] = [[200, 50, 50, 160]] * len(map_df)

        # más cercano
        map_df.iloc[0, map_df.columns.get_loc("color")] = [0, 200, 0, 220]

        st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=map_df,
                        get_position=["lon", "lat"],
                        get_fill_color="color",
                        get_radius=90,
                        pickable=True
                    ),
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=pd.DataFrame([{
                            "lat": coords[0],
                            "lon": coords[1]
                        }]),
                        get_position=["lon", "lat"],
                        get_fill_color=[0, 120, 255, 200],
                        get_radius=130
                    )
                ],
                initial_view_state=pdk.ViewState(
                    latitude=coords[0],
                    longitude=coords[1],
                    zoom=14
                ),
                tooltip={
                    "text": "{CAFE}\n{UBICACION}\n{Distancia}"
                }
            ),
            use_container_width=True
        )

# =====================================================
# 🔥 TAB TOSTADORES
# =====================================================
with tabs[1]:
    st.subheader("🔥 Tostadores")

    tostadores_ciudad = tostadores[
        tostadores["CIUDAD"].str.contains(ciudad, case=False, na=False)
    ]

    if tostadores_ciudad.empty:
        st.info("No hay tostadores cargados para esta ciudad")
    else:
        for _, t in tostadores_ciudad.iterrows():
            st.markdown(f"### ☕ {t['TOSTADOR']}")

            if t.get("INSTAGRAM"):
                st.markdown(f"[📸 Instagram]({t['INSTAGRAM']})")

            if t.get("VARIEDADES"):
                st.markdown(f"**🌱 Variedades:** {t['VARIEDADES']}")

            if t.get("CAFETERIAS"):
                st.markdown(f"**🏪 Cafeterías:** {t['CAFETERIAS']}")

            st.divider()
