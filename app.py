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
    df = None
    for enc in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except Exception:
            continue
    if df is None:
        df = pd.read_csv(path, dtype=str)

    def fix_text(x):
        try:
            return x.encode("latin1").decode("utf-8")
        except Exception:
            return x

    for col in df.select_dtypes(include="object"):
        df[col] = df[col].apply(lambda x: fix_text(str(x)) if x is not None else x)

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
col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    direccion = st.text_input("Dirección", "Av. Colón 1500")

with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)

with col3:
    agrupar = st.checkbox("Agrupar (zoom alejado)", value=True,
                          help="Usa un mapa de densidad para mejorar el rendimiento cuando hay muchos puntos.")

# ================================
# Acción principal
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

    # Filtrar por radio
    resultado = cafes_validos[cafes_validos["DIST_KM"] <= radio_km] \
        .sort_values("DIST_KM") \
        .reset_index(drop=True)

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio indicado.")
        st.stop()

    # ============================
    # TABLA + Link a Google Maps
    # ============================
    def link_maps(lat, lon):
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    tabla = resultado.copy()
    tabla["DIST_KM"] = tabla["DIST_KM"].round(3)
    tabla["CUADRAS"] = tabla["CUADRAS"].round(1)
    tabla["COMO_LLEGAR"] = tabla.apply(lambda r: link_maps(r["LAT"], r["LONG"]), axis=1)

    st.dataframe(
        tabla[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS", "COMO_LLEGAR"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "COMO_LLEGAR": st.column_config.LinkColumn(
                "Cómo llegar", help="Abrir en Google Maps", display_text="Abrir Maps"
            )
        }
    )

    # ================================
    # MAPA (IconLayer + colores por puntaje + agrupación opcional)
    # ================================
    st.subheader("Mapa")

    # Data para el mapa
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})[
        ["lat", "lon", "CAFE", "UBICACION", "PUNTAJE"]
    ].dropna()
    map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")
    map_df["PUNTAJE"] = pd.to_numeric(map_df["PUNTAJE"], errors="coerce")
    map_df = map_df.dropna(subset=["lat", "lon"])

    if map_df.empty:
        st.info("No hay coordenadas válidas para el mapa.")
        st.stop()

    # ---- Color por puntaje (rojo<6, naranja 6–8, verde>=8) ----
    def color_por_puntaje(p):
        try:
            p = float(p)
        except Exception:
            return [120, 120, 120, 230]  # gris si no hay puntaje
        if p >= 8.0:
            return [0, 170, 80, 230]     # verde
        if p >= 6.0:
            return [255, 140, 0, 230]    # naranja
        return [220, 0, 0, 230]          # rojo

    map_df["COLOR"] = map_df["PUNTAJE"].apply(color_por_puntaje)

    # ---- IconLayer (atlas público de deck.gl) ----
    # TODO (opcional): cambiar 'icon_atlas' por URL de una taza PNG si me la pasás.
    icon_atlas = "https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png"
    icon_mapping = "https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.json"
    # En ese atlas vamos a usar el ícono 'marker' (ya definido en el mapping)
    map_df = map_df.assign(icon_name="marker", size=3)  # size escalable: 2–4 queda bien

    icon_layer = pdk.Layer(
        "IconLayer",
        data=map_df,
        get_icon="icon_name",
        get_position=["lon", "lat"],
        get_size="size",
        size_scale=8,                # 8 px aprox (pequeño)
        icon_atlas=icon_atlas,
        icon_mapping=icon_mapping,
        get_color="COLOR",
        pickable=True
    )

    # ---- Capa de densidad para "agrupar" cuando hay muchos puntos ----
    # Si está activo 'agrupar', mostramos una capa HeatmapLayer (no requiere token)
    heat_layer = pdk.Layer(
        "HeatmapLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_weight="PUNTAJE",    # más peso a mejores puntajes
        radius_pixels=40,        # cuanto mayor, más agrupación visual
    ) if agrupar else None

    # ---- Tu ubicación ----
    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord_user[0], "lon": coord_user[1]}]),
        get_position=["lon", "lat"],
        get_radius=18,
        radius_units="meters",
        get_fill_color=[0, 120, 255, 220],
    )

    view = pdk.ViewState(latitude=coord_user[0], longitude=coord_user[1], zoom=14)

    layers = [icon_layer, user_layer] if not agrupar else [heat_layer, icon_layer, user_layer]

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view,
        tooltip={"html": "<b>{CAFE}</b><br/>{UBICACION}<br/>Puntaje: {PUNTAJE}"},
        map_style=None  # sin token
    )

    st.pydeck_chart(deck, use_container_width=True, height=520)
