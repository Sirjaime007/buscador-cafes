import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# ---------------------------------------
# Configuración de sitio
# ---------------------------------------
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección** y te mostramos los cafés más cercanos dentro del radio que elijas.")

# ---------------------------------------
# Cargar dataset
# ---------------------------------------
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols_req = {"CAFE", "UBICACION", "PUNTAJE", "TOSTADOR", "LAT", "LONG"}
    falt = cols_req - set(df.columns)
    if falt:
        st.error(f"Faltan columnas en Cafes.csv: {', '.join(falt)}")
        st.stop()

    # Normalizamos numéricos
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"], errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"], errors="coerce")
    return df

cafes = load_cafes("Cafes.csv")

# ---------------------------------------
# Obtener parámetros desde la URL
# ---------------------------------------
def get_query_params_safe():
    params = {}
    if hasattr(st, "query_params"):
        try:
            params = dict(st.query_params)
        except:
            pass

    if not params and hasattr(st, "experimental_get_query_params"):
        try:
            old = st.experimental_get_query_params()
            params = {k: v[0] if isinstance(v, list) else v for k, v in old.items()}
        except:
            pass

    return params

params = get_query_params_safe()
q_url = params.get("q")
r_url = params.get("r")

def parse_float(x):
    try:
        return float(x)
    except:
        return None

# ---------------------------------------
# Geocodificador Nominatim
# ---------------------------------------
@st.cache_resource
def get_geocoder():
    g = Nominatim(user_agent="mdp-cafes")
    return RateLimiter(g.geocode, min_delay_seconds=1)

geocode = get_geocoder()

@st.cache_data(show_spinner=False)
def geocode_address(q: str):
    """Devuelve (lat, lon) o None"""
    if not q or not q.strip():
        return None

    # Sesgo automático a Mar del Plata + Argentina
    query = q.strip()
    if "mar del plata" not in query.lower():
        query += ", Mar del Plata"
    if "arg" not in query.lower():
        query += ", Argentina"

    loc = geocode(query)
    if loc is None:
        return None
    return (loc.latitude, loc.longitude)

# ---------------------------------------
# Inputs de usuario
# ---------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input(
        "Dirección",
        value=q_url if q_url else "Av. Colón 1500",
        placeholder="Ej.: Córdoba 1800",
    )

with col2:
    radio_km = st.number_input(
        "Radio (km)",
        min_value=0.1,
        value=parse_float(r_url) if parse_float(r_url) else 2.0,
        step=0.5,
    )

buscar = st.button("🔎 Buscar cafés cercanos")

# ---------------------------------------
# Acción principal
# ---------------------------------------
if buscar:
    with st.spinner("Buscando dirección..."):
        coord_user = geocode_address(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá agregar altura o calle más exacta.")
        st.stop()

    st.success(f"Dirección ubicada en: lat {coord_user[0]:.5f}, lon {coord_user[1]:.5f}")

    # ---------------------------------------
    # Filtrar cafés con coordenadas válidas
    # ---------------------------------------
    cafes_validos = cafes.dropna(subset=["LAT", "LONG"]).copy()

    cafes_validos["DIST_KM"] = cafes_validos.apply(
        lambda row: geodesic(coord_user, (row["LAT"], row["LONG"])).km,
        axis=1
    )

    resultado = cafes_validos[cafes_validos["DIST_KM"] <= radio_km] \
                .sort_values("DIST_KM") \
                .reset_index(drop=True)

    st.subheader("Resultados")

    if resultado.empty:
        st.warning("No hay cafés dentro del radio seleccionado.")
        st.stop()

    # Tabla
    st.dataframe(
        resultado.assign(DIST_KM=lambda d: d["DIST_KM"].round(3)),
        use_container_width=True,
        hide_index=True
    )

    # Mapa
    st.subheader("Mapa")
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})
    st.map(map_df[["lat", "lon"]], zoom=14)
