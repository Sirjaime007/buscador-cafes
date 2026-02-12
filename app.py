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
    return df

cafes = load_cafes("Cafes.csv")

# ---------- Utilidades ----------
def parse_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None

# ---------- Leer lat/lon de query params (API nueva) ----------
# Si estás en una versión vieja, esto seguirá existiendo como atributo ausente,
# pero acá asumimos la versión nueva (que es lo que rompe el experimental).
params = {}
if hasattr(st, "query_params"):
    # st.query_params es un Mapping[str, str]
    params = dict(st.query_params)

lat_qp = parse_float(params.get("lat"))
lon_qp = parse_float(params.get("lon"))

# ---------- Inputs con valores por defecto de la URL (si existen) ----------
col1, col2 = st.columns(2)
with col1:
    lat = st.number_input("Tu latitud", value=lat_qp if lat_qp is not None else 0.0, format="%.6f")
with col2:
