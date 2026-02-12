import streamlit as st
import pandas as pd
from geopy.distance import geodesic

st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Permitir ubicación para encontrar cafés cercanos.")

# ---------- Lectura de datos ----------
@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Validación básica de columnas esperadas
    cols_req = {"CAFE", "UBICACION", "PUNTAJE", "TOSTADOR", "LAT", "LONG"}
    faltantes = cols_req - set(df.columns)
    if faltantes:
        st.error(f"Faltan columnas en Cafes.csv: {', '.join(sorted(faltantes))}")
        st.stop()
    # Limpieza/normalización mínima
    # Aseguramos tipo numérico de LAT/LONG y PUNTAJE
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"], errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"], errors="coerce")
    return df

cafes = load_cafes("Cafes.csv")

# ---------- Utilidades ----------
def parse_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

def get_query_params_safe():
    """Soporta API nueva y antigua de Streamlit."""
    params = {}
    # API nueva: st.query_params (Streamlit >= 1.37 aprox)
    if hasattr(st, "query_params"):
        try:
            # st.query_params es un Mapping
            params = dict(st.query_params)
        except Exception:
            params = {}
    # Fallback: experimental_get_query_params (antigua)
    if not params and hasattr(st, "experimental_get_query_params"):
        try:
            old = st.experimental_get_query_params()  # dict[str, list[str]]
            # Aplanamos a str (tomamos el primer valor si es lista)
            params = {k: v[0] if isinstance(v, list) and v else v for k, v in old.items()}
        except Exception:
            params = {}
    return params

params = get_query_params_safe()
lat_qp = parse_float(params.get("lat"))
lon_qp = parse_float(params.get("lon"))
r_qp   = parse_float(params.get("r"))  # radio opcional desde la URL, en km

# ---------- Inputs con valores por defecto de la URL (si existen) ----------
col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    lat = st.number_input(
        "Tu latitud",
        value=lat_qp if lat_qp is not None else -38.0055,  # Mar del Plata por defecto
        format="%.6f",
        help="Podés completar manualmente o pasar ?lat=-38.00&lon=-57.55 en la URL."
    )
with col2:
    lon = st.number_input(
        "Tu longitud",
        value=lon_qp if lon_qp is not None else -57.5426,
        format="%.6f"
    )
with col3:
    radio_km = st.number_input(
        "Radio de búsqueda (km)",
        min_value=0.1,
        value=r_qp if r_qp is not None and r_qp > 0 else 2.0,
        step=0.5
    )

# Filtros opcionales
with st.expander("Filtros avanzados", expanded=False):
    puntaje_min = st.slider("Puntaje mínimo", min_value=0.0, max_value=5.0, value=0.0, step=0.1)
    tostadores = ["(Todos)"] + sorted([t for t in cafes["TOSTADOR"].dropna().unique()])
    tost_sel = st.selectbox("Tostador", tostadores)

# ---------- Cálculo de distancias ----------
def fila_valida(row):
    return pd.notna(row["LAT"]) and pd.notna(row["LONG"])

if lat is None or lon is None:
    st.warning("Completá latitud y longitud válidas.")
    st.stop()

coord_user = (lat, lon)

cafes_validos = cafes[cafes.apply(fila_valida, axis=1)].copy()
if cafes_validos.empty:
    st.warning("No hay cafés con coordenadas válidas en el dataset.")
    st.stop()

def distance_km(row):
    try:
        return geodesic(coord_user, (row["LAT"], row["LONG"])).km
    except Exception:
        return float("inf")

cafes_validos["DIST_KM"] = cafes_validos.apply(distance_km, axis=1)

# Aplico filtros
mask = cafes_validos["DIST_KM"] <= radio_km
if puntaje_min is not None:
    mask &= (cafes_validos["PUNTAJE"].fillna(0) >= puntaje_min)
if tost_sel and tost_sel != "(Todos)":
    mask &= (cafes_validos["TOSTADOR"] == tost_sel)

resultado = cafes_validos[mask].sort_values("DIST_KM").reset_index(drop=True)

# ---------- Resultados ----------
st.subheader("Resultados")
st.caption(f"Mostrando cafés dentro de {radio_km:.1f} km, ordenados por cercanía.")

if resultado.empty:
    st.info("No se encontraron cafés con los filtros aplicados. Probá ampliar el radio o bajar el puntaje mínimo.")
else:
    # Tabla amigable
    cols_show = ["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG", "DIST_KM"]
    st.dataframe(
        resultado[cols_show].assign(DIST_KM=lambda d: d["DIST_KM"].round(3)),
        use_container_width=True,
        hide_index=True
    )

    # Mapa (Streamlit espera columnas 'lat' y 'lon')
    st.subheader("Mapa")
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})
    st.map(map_df[["lat", "lon"]], zoom=13)

# ---------- Tips ----------
st.markdown(
    """
**Tips**
- Podés pasar parámetros en la URL: `?lat=-38.00&lon=-57.55&r=3`.
- Verificá que `Cafes.csv` tenga columnas: `CAFE, UBICACION, PUNTAJE, TOSTADOR, LAT, LONG`.
- Si usás una versión vieja de Streamlit, se usa `experimental_get_query_params`; en nuevas, `st.query_params`.
"""
)
