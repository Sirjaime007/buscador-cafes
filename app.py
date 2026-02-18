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

st.title("☕ Buscador de Cafés en Mar del Plata")

# =========================
# CARGA DESDE GOOGLE SHEETS
# =========================
@st.cache_data(ttl=300)
def cargar_cafes():
    url = (
        "https://docs.google.com/spreadsheets/d/"
        "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"
        "/export?format=csv"
    )

    df = pd.read_csv(url, dtype=str)

    for col in ["LAT", "LONG"]:
        df[col] = (
            df[col]
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[
        df["LAT"].between(-90, 90) &
        df["LONG"].between(-180, 180)
    ]

    return df


cafes = cargar_cafes()

if cafes is None or cafes.empty:
    st.error("No hay datos de cafés 😕")
    st.stop()

# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocodificar(direccion):
    geo = get_geocoder()
    loc = geo.geocode(f"{direccion}, Mar del Plata, Buenos Aires, Argentina")
    if loc:
        return loc.latitude, loc.longitude
    return None

# =========================
# UI
# =========================
direccion = st.text_input(
    "📍 Dirección",
    value="Av. Colón 1500",
    placeholder="Ej: Alberti 2500"
)

radio_km = st.slider(
    "📏 Radio de búsqueda (km)",
    0.5, 5.0, 2.0, 0.5
)

tostadores = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
filtro_tostador = st.selectbox("🏷️ Filtrar por tostador", tostadores)

buscar = st.button("🔍 Buscar cafés")

# =========================
# BUSQUEDA
# =========================
if buscar:
    coords = geocodificar(direccion)

    if coords is None:
        st.error("No se pudo encontrar la dirección 😕")
        st.stop()

    cafes_calc = cafes.copy()

    cafes_calc["Distancia"] = cafes_calc.apply(
        lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
        axis=1
    )

    resultado = cafes_calc[cafes_calc["Distancia"] <= radio_km]

    if filtro_tostador != "Todos":
        resultado = resultado[resultado["TOSTADOR"] == filtro_tostador]

    resultado = resultado.sort_values("Distancia")

    if resultado.empty:
        st.warning("No se encontraron cafés con esos filtros ☹️")
        st.stop()

    # =========================
    # TABLA
    # =========================
    resultado["Distancia"] = resultado["Distancia"].apply(
        lambda km: f"{int(km*1000)} m" if km < 1 else f"{km:.2f} km"
    )

    resultado["MAPS"] = resultado.apply(
        lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
        axis=1
    )

    st.subheader(f"☕ Cafés encontrados ({len(resultado)})")

    st.dataframe(
        resultado[["CAFE", "UBICACION", "TOSTADOR", "Distancia", "MAPS"]],
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
    # MAPA
    # =========================
    st.subheader("🗺️ Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()

    # colores: rojo = normal, verde = más cercano
    map_df["color"] = [[200, 50, 50, 160]] * len(map_df)
    idx_mas_cercano = map_df.index[0]
    map_df.at[idx_mas_cercano, "color"] = [0, 200, 0, 220]

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
