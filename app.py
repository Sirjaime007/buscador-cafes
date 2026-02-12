import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk

# ================================
# Configuración general
# ================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# ================================
# Cargar CSV (tildes + decimales OK)
# ================================
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    # Intentamos leer con codificaciones comunes
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except Exception:
            continue

    # Intento final sin especificar encoding
    if "df" not in locals():
        df = pd.read_csv(path, dtype=str)

    # Fix de mojibake (hipÃ³lito → hipólito)
    def fix_text(x):
        try:
            return x.encode("latin1").decode("utf-8")
        except:
            return x

    for col in df.select_dtypes(include="object"):
        df[col] = df[col].apply(lambda x: fix_text(str(x)) if x is not None else x)

    # Normalizador de números (mantiene decimales)
    def fix_number(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "":
            return None
        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")
        if x.count(".") == 1 and x.count(",") == 1:
            return x.replace(".", "").replace(",", ".")
        return x

    df["LAT"] = pd.to_numeric(df["LAT"].apply(fix_number), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].apply(fix_number), errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"].apply(fix_number), errors="coerce")

    return df


cafes = load_cafes("Cafes.csv")

# ================================
# Geocoder ArcGIS
# ================================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address(address: str):
    loc = get_geocoder().geocode(f"{address}, Mar del Plata, Buenos Aires, Argentina")
    if loc:
        return float(loc.latitude), float(loc.longitude)
    return None

# ================================
# Inputs
# ================================
col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input("Dirección", "Av. Colón 1500")

with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)

# ================================
# Acción
# ================================
if st.button("🔎 Buscar cafés cercanos"):

    with st.spinner("Buscando..."):
        coord_user = geocode_address(direccion)

    if coord_user is None:
        st.error("No se encontró la dirección. Probá agregar la altura o revisar la calle.")
        st.stop()

    st.success("Dirección encontrada ✔️")

    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    # Distancias
    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda r: geodesic(coord_user, (float(r["LAT"]), float(r["LONG"]))).km,
        axis=1
    )
    cafes_validos["CUADRAS"] = cafes_validos["DIST_KM"] * 1000 / 87

    # Filtrar
    resultado = cafes_validos[cafes_validos["DIST_KM"] <= radio_km] \
        .sort_values("DIST_KM") \
        .reset_index(drop=True)

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio indicado.")
        st.stop()

    # Agregar botón "Cómo llegar"
    def link_maps(lat, lon):
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    resultado["COMO_LLEGAR"] = resultado.apply(
        lambda r: f"[Cómo llegar]({link_maps(r['LAT'], r['LONG'])})",
        axis=1
    )

    # Tabla limpia (sin LAT/LONG)
    tabla = resultado[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS", "COMO_LLEGAR"]].copy()
    tabla["DIST_KM"] = tabla["DIST_KM"].round(3)
    tabla["CUADRAS"] = tabla["CUADRAS"].round(1)

    st.dataframe(tabla, use_container_width=True, hide_index=True)

    # ================================
    # MAPA PYDECK SIN MAPBOX (funciona siempre)
    # ================================
    st.subheader("Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})[
        ["lat", "lon", "CAFE", "UBICACION"]
    ].dropna()

    map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")
    map_df = map_df.dropna(subset=["lat", "lon"])

    # Café → punto pequeño + cruz
    cafes_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=12,
        radius_units="meters",
        get_fill_color=[0, 0, 0, 180],
        pickable=True
    )

    cross_layer = pdk.Layer(
        "TextLayer",
        data=map_df.assign(text="＋"),
        get_position=["lon", "lat"],
        get_text="text",
        get_size=24,
        get_color=[0, 0, 0, 255],
        get_alignment_baseline="'center'"
    )

    # Tu ubicación
    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord_user[0], "lon": coord_user[1]}]),
        get_position=["lon", "lat"],
        get_radius=18,
        radius_units="meters",
        get_fill_color=[0, 100, 255, 220],
    )

    view = pdk.ViewState(
        latitude=coord_user[0],
        longitude=coord_user[1],
        zoom=14
    )

    deck = pdk.Deck(
        layers=[cafes_layer, cross_layer, user_layer],
        initial_view_state=view,
        tooltip={"html": "<b>{CAFE}</b><br/>{UBICACION}"},
        map_style=None
    )

    st.pydeck_chart(deck, use_container_width=True, height=520)
