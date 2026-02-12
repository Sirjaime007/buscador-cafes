import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS

# ---------------------------------------
# Configuración general
# ---------------------------------------
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés más cercanos dentro del radio elegido.")

# ---------------------------------------
# Cargar dataset de cafés
# ---------------------------------------

@st.cache_data
def load_cafes(path: str) -> pd.DataFrame:
    # Leer con la codificación correcta
    df = pd.read_csv(path, encoding="latin-1", dtype=str)  
    # dtype=str ES CLAVE: evita que Pandas trunque números

    # Validar columnas obligatorias
    required_cols = {"CAFE","UBICACION","TOSTADOR","PUNTAJE","LAT","LONG"}
    if not required_cols.issubset(df.columns):
        st.error(f"El CSV no contiene estas columnas: {required_cols}")
        st.stop()

    # -------------------------------
    # NORMALIZADOR AVANZADO DE NÚMEROS
    # Mantiene todos los decimales siempre
    # -------------------------------
    def fix_number(x):
        if pd.isna(x):
            return None
        x = x.strip()

        # Caso 1: formato AR: -38,0056 → -38.0056
        if x.count(",") == 1 and x.count(".") == 0:
            return x.replace(",", ".")

        # Caso 2: miles + decimales: 1.234,567 → 1234.567
        if x.count(".") == 1 and x.count(",") == 1:
            x = x.replace(".", "").replace(",", ".")
            return x

        # Caso 3: formato raro (dejamos como viene)
        return x

    # Aplicar a coordenadas y puntajes (SIN truncado)
    df["LAT"] = df["LAT"].apply(fix_number)
    df["LONG"] = df["LONG"].apply(fix_number)
    df["PUNTAJE"] = df["PUNTAJE"].apply(fix_number)

    # Convertir ahora sí a float conservando decimales
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"], errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"], errors="coerce")

    # Verificar coordenadas válidas
    if df["LAT"].isna().all() or df["LONG"].isna().all():
        st.error("Error: No hay coordenadas válidas. Revisá LAT/LONG en el CSV.")
        st.stop()

    return df


cafes = load_cafes("Cafes.csv")

# ---------------------------------------
# Geocoder ArcGIS (no requiere API KEY)
# ---------------------------------------
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address_arcgis(address: str):
    if not address:
        return None

    # Sesgo automático a Mar del Plata
    query = f"{address}, Mar del Plata, Buenos Aires, Argentina"

    geolocator = get_geocoder()
    loc = geolocator.geocode(query)

    if loc is None:
        return None

    return (loc.latitude, loc.longitude)

# ---------------------------------------
# Inputs
# ---------------------------------------
col1, col2 = st.columns([3, 1])

with col1:
    direccion = st.text_input(
        "Dirección",
        value="Av. Colón 1500",
        placeholder="Ej.: Gascon 2525, Córdoba 1800, etc."
    )

with col2:
    radio_km = st.number_input(
        "Radio (km)",
        min_value=0.1,
        value=2.0,
        step=0.5
    )

buscar = st.button("🔎 Buscar cafés cercanos")

# ---------------------------------------
# Lógica principal
# ---------------------------------------
if buscar:
    with st.spinner("Buscando dirección…"):
        coord_user = geocode_address_arcgis(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Probá agregar altura o revisar la calle.")
        st.stop()

    st.success(f"Dirección encontrada: lat={coord_user[0]:.5f}, lon={coord_user[1]:.5f}")

    # Filtrar cafés con coordenadas válidas
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

    st.dataframe(
        resultado.assign(DIST_KM=lambda d: d["DIST_KM"].round(3)),
        use_container_width=True,
        hide_index=True
    )

    # Mapa de cafés cerca de la dirección
    st.subheader("Mapa")
    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})
    st.map(map_df[["lat", "lon"]], zoom=14)
