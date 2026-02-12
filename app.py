import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk

# =========================================
# Configuración
# =========================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# =========================================
# Carga de datos (tildes OK y decimales sin truncar)
# =========================================
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    # Leemos en latin-1 para corregir caracteres como ñ/á/¿ sin agregar artefactos
    df = pd.read_csv(path, encoding="latin-1", dtype=str)

    # Validación mínima
    required_cols = {"CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG"}
    faltan = required_cols - set(df.columns)
    if faltan:
        st.error(f"Faltan columnas en el CSV: {', '.join(sorted(faltan))}")
        st.stop()

    # Normalizador numérico (conserva decimales)
    def fix_number(x):
        if x is None:
            return None
        x = str(x).strip()
        if x == "":
            return None
        # -38,0056 -> -38.0056
        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")
        # 1.234,567 -> 1234.567
        if x.count(".") == 1 and x.count(",") == 1:
            return x.replace(".", "").replace(",", ".")
        return x

    # Convertimos columnas numéricas (sin truncar)
    df["LAT"] = pd.to_numeric(df["LAT"].apply(fix_number), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].apply(fix_number), errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"].apply(fix_number), errors="coerce")

    # Aseguramos texto en las columnas de strings (para tildes correctas)
    for col in ["CAFE", "UBICACION", "TOSTADOR"]:
        df[col] = df[col].astype(str)

    return df

cafes = load_cafes("Cafes.csv")

# =========================================
# Geocoder ArcGIS (sin API Key)
# =========================================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address_arcgis(address: str):
    if not address:
        return None
    loc = get_geocoder().geocode(f"{address}, Mar del Plata, Buenos Aires, Argentina")
    if loc is None:
        return None
    return (float(loc.latitude), float(loc.longitude))

# =========================================
# UI
# =========================================
col1, col2 = st.columns([3, 1])
with col1:
    direccion = st.text_input("Dirección", value="Av. Colón 1500", placeholder="Ej.: Gascón 2525")
with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)

if st.button("🔎 Buscar cafés cercanos"):
    with st.spinner("Geocodificando…"):
        coord_user = geocode_address_arcgis(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá con calle + altura + ciudad.")
        st.stop()

    # Mostramos confirmación sin lat/lon numéricas
    st.success("Dirección encontrada ✔️")

    # =========================================
    # Distancias
    # =========================================
    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    # Calculamos distancia en km y en cuadras
    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda r: geodesic(coord_user, (float(r["LAT"]), float(r["LONG"]))).km,
        axis=1
    )
    cafes_validos["CUADRAS"] = cafes_validos["DIST_KM"] * 1000.0 / 87.0

    # Filtramos por radio
    resultado = (
        cafes_validos[cafes_validos["DIST_KM"] <= radio_km]
        .sort_values("DIST_KM")
        .reset_index(drop=True)
    )

    st.subheader("Resultados")

    if resultado.empty:
        st.info("No hay cafés dentro del radio seleccionado. Probá ampliar el radio.")
        st.stop()

    # =========================================
    # Tabla (sin LAT/LONG)
    # =========================================
    tabla = resultado.copy()
    tabla["DIST_KM"] = tabla["DIST_KM"].round(3)
    tabla["CUADRAS"] = tabla["CUADRAS"].round(1)

    st.dataframe(
        tabla[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM", "CUADRAS"]],
        use_container_width=True,
        hide_index=True,
    )

    # =========================================
    # Mapa con puntos pequeños (pydeck)
    # =========================================
    st.subheader("Mapa")

    # Preparamos datos del mapa (nombres correctos y tipos numéricos)
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})[["lat", "lon", "CAFE", "UBICACION"]].dropna()
    map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")
    map_df = map_df.dropna(subset=["lat", "lon"])

    if map_df.empty:
        st.info("No hay coordenadas válidas para mostrar en el mapa.")
        st.stop()

    # Capa de cafés (puntos pequeños; negro)
    cafes_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=10,           # punto chico (en metros)
        radius_units="meters",
        get_fill_color=[0, 0, 0, 220],  # negro
        pickable=True,
    )

    # Capa para tu ubicación (un círculo celeste un poco más visible)
    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord_user[0], "lon": coord_user[1]}]),
        get_position=["lon", "lat"],
        get_radius=18,
        radius_units="meters",
        get_fill_color=[0, 122, 255, 230],  # celeste
        pickable=False,
    )

    # Estado de vista centrado en tu ubicación
    view = pdk.ViewState(
        latitude=coord_user[0],
        longitude=coord_user[1],
        zoom=14,
        pitch=0,
        bearing=0
    )

    # Tooltip (cuando hacés hover)
    tooltip = {
        "html": "<b>{CAFE}</b><br/>{UBICACION}",
        "style": {"backgroundColor": "white", "color": "black"}
    }

    deck = pdk.Deck(
        layers=[cafes_layer, user_layer],
        initial_view_state=view,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v9"  # basemap claro
    )

    st.pydeck_chart(deck, use_container_width=True, height=500)
``
