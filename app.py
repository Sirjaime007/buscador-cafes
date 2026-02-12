import os
from datetime import datetime

import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# =========================================
# CONFIGURACIÓN
# =========================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.caption("Ingresá una **dirección de Mar del Plata**. Mostramos cafés cercanos, podés **votar** tu favorito y abajo verás un **índice completo** ordenado por cercanía.")

CUADRA_METROS = 87
GSHEET_NAME = "cafes_reviews"   # <-- nombre de tu Google Sheet (pestaña principal: Hoja 1 con encabezados: voter_id | CAFE | score | ts)

# =========================================
# UTILIDADES: Google Sheets
# =========================================
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource(show_spinner=False)
def get_gsheet():
    """Conecta a Google Sheets usando credenciales en st.secrets['gcp_service_account']."""
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(GSHEET_NAME).sheet1  # Hoja 1
    return sheet

def load_votes() -> pd.DataFrame:
    """Lee todos los votos desde Google Sheets."""
    try:
        sheet = get_gsheet()
        rows = sheet.get_all_records()
        if not rows:
            return pd.DataFrame(columns=["voter_id", "CAFE", "score", "ts"])
        df = pd.DataFrame(rows)
        # normalizo tipos
        if "score" in df.columns:
            df["score"] = pd.to_numeric(df["score"], errors="coerce")
        return df
    except Exception as e:
        st.warning(f"No se pudo leer votos de Google Sheets: {e}")
        return pd.DataFrame(columns=["voter_id", "CAFE", "score", "ts"])

def upsert_vote(voter_id: str, cafe_name: str, score: float):
    """Inserta o actualiza el voto del usuario para ese café en Google Sheets."""
    sheet = get_gsheet()
    rows = sheet.get_all_records()
    # Buscar si ya existe (fila 2 en adelante porque 1 es encabezado)
    for i, row in enumerate(rows, start=2):
        if str(row.get("voter_id")) == voter_id and str(row.get("CAFE")) == cafe_name:
            sheet.update_cell(i, 3, float(score))                 # score (col 3)
            sheet.update_cell(i, 4, datetime.utcnow().isoformat())# ts (col 4)
            return
    # Si no existe, lo agrego
    sheet.append_row([voter_id, cafe_name, float(score), datetime.utcnow().isoformat()])

# =========================================
# UTILIDADES: Carga y normalización del CSV
# =========================================
@st.cache_data(show_spinner=False)
def load_cafes(path: str) -> pd.DataFrame:
    df = None
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except Exception:
            continue
    if df is None:
        df = pd.read_csv(path, dtype=str)

    # Arreglo básico de mojibake (HipÃ³lito → Hipólito; Â¿ → ¿)
    def fix_text(x):
        try:
            return x.encode("latin1").decode("utf-8")
        except Exception:
            return x

    for c in df.select_dtypes(include="object"):
        df[c] = df[c].apply(lambda x: fix_text(str(x)) if x is not None else x)

    # Normalización numérica sin perder decimales
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

    required_cols = {"CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "LAT", "LONG"}
    faltan = required_cols - set(df.columns)
    if faltan:
        st.error(f"Faltan columnas requeridas en Cafes.csv: {', '.join(sorted(faltan))}")
        st.stop()

    df["LAT"] = pd.to_numeric(df["LAT"].apply(fix_number), errors="coerce")
    df["LONG"] = pd.to_numeric(df["LONG"].apply(fix_number), errors="coerce")
    df["PUNTAJE"] = pd.to_numeric(df["PUNTAJE"].apply(fix_number), errors="coerce")
    return df

cafes = load_cafes("Cafes.csv")

# =========================================
# Geocoder ArcGIS (sin API key)
# =========================================
@st.cache_resource(show_spinner=False)
def get_geocoder():
    return ArcGIS(timeout=10)

def geocode_address(address: str):
    loc = get_geocoder().geocode(f"{address}, Mar del Plata, Buenos Aires, Argentina")
    if loc:
        return float(loc.latitude), float(loc.longitude)
    return None

# =========================================
# UI: una sola barra de búsqueda
# =========================================
col1, col2 = st.columns([3, 1])
with col1:
    direccion = st.text_input("Dirección", value="Av. Colón 1500", placeholder="Ej.: Gascón 2525")
with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)

# ID simple por sesión para el voto
if "voter_id" not in st.session_state:
    import uuid
    st.session_state["voter_id"] = str(uuid.uuid4())
voter_id = st.session_state["voter_id"]

# =========================================
# ACCIÓN
# =========================================
if st.button("🔎 Buscar cafés cercanos", use_container_width=True):
    with st.spinner("Geocodificando dirección…"):
        coord_user = geocode_address(direccion)

    if coord_user is None:
        st.error("No se pudo ubicar la dirección. Usá calle + altura + ciudad (Mar del Plata).")
        st.stop()

    st.success("Dirección encontrada ✔️")

    # Distancias para TODOS (índice completo)
    cafes_all = cafes.dropna(subset=["LAT", "LONG"]).copy()
    cafes_all["DIST_KM_TOTAL"] = cafes_all.apply(
        lambda r: geodesic(coord_user, (float(r["LAT"]), float(r["LONG"]))).km, axis=1
    )
    cafes_all["CUADRAS_TOTAL"] = cafes_all["DIST_KM_TOTAL"] * 1000.0 / CUADRA_METROS

    # Resultados por radio para la sección principal
    resultado = (
        cafes_all[cafes_all["DIST_KM_TOTAL"] <= radio_km]
        .sort_values("DIST_KM_TOTAL")
        .reset_index(drop=True)
        .rename(columns={"DIST_KM_TOTAL": "DIST_KM", "CUADRAS_TOTAL": "CUADRAS"})
    )

    st.subheader("Resultados en el radio seleccionado")

    if resultado.empty:
        st.info("No hay cafés dentro del radio. Probá ampliar el radio.")
        st.stop()

    # Tabla + link "Abrir Maps"
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

    # ============================
    # Mapa (IconLayer + color por puntaje)
    # ============================
    st.subheader("Mapa")

    map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"})[
        ["lat", "lon", "CAFE", "UBICACION", "PUNTAJE"]
    ].dropna()
    map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")
    map_df["PUNTAJE"] = pd.to_numeric(map_df["PUNTAJE"], errors="coerce")
    map_df = map_df.dropna(subset=["lat", "lon"])

    def color_por_puntaje(p):
        try:
            p = float(p)
        except Exception:
            return [120, 120, 120, 230]
        if p >= 8.0:
            return [0, 170, 80, 230]     # verde
        if p >= 6.0:
            return [255, 140, 0, 230]    # naranja
        return [220, 0, 0, 230]          # rojo

    map_df["COLOR"] = map_df["PUNTAJE"].apply(color_por_puntaje)

    icon_atlas = "https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png"
    icon_mapping = "https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.json"
    map_df = map_df.assign(icon_name="marker", size=3)

    icon_layer = pdk.Layer(
        "IconLayer",
        data=map_df,
        get_icon="icon_name",
        get_position=["lon", "lat"],
        get_size="size",
        size_scale=8,                # pequeño
        icon_atlas=icon_atlas,
        icon_mapping=icon_mapping,
        get_color="COLOR",
        pickable=True
    )

    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": coord_user[0], "lon": coord_user[1]}]),
        get_position=["lon", "lat"],
        get_radius=18,
        radius_units="meters",
        get_fill_color=[0, 120, 255, 220],
    )

    view = pdk.ViewState(latitude=coord_user[0], longitude=coord_user[1], zoom=14)
    deck = pdk.Deck(
        layers=[icon_layer, user_layer],
        initial_view_state=view,
        tooltip={"html": "<b>{CAFE}</b><br/>{UBICACION}<br/>Puntaje: {PUNTAJE}"},
        map_style=None  # sin token
    )
    st.pydeck_chart(deck, use_container_width=True, height=420)

    # ============================
    # Votar (simple, en una línea)
    # ============================
    st.subheader("Votar tu café favorito (simple)")
    v1, v2, v3 = st.columns([3, 2, 1])
    with v1:
        cafe_sel = st.selectbox("Café", options=list(resultado["CAFE"].unique()), label_visibility="collapsed")
    with v2:
        puntaje_sel = st.slider("Puntaje (1–10)", 1.0, 10.0, 8.0, 0.5, label_visibility="collapsed")
    with v3:
        if st.button("Votar", use_container_width=True):
            try:
                upsert_vote(voter_id=voter_id, cafe_name=cafe_sel, score=puntaje_sel)
                st.success(f"¡Voto guardado para **{cafe_sel}** con {puntaje_sel} puntos!")
            except Exception as e:
                st.error(f"No se pudo guardar el voto en Google Sheets: {e}")

    # ============================
    # Ranking global (Google Sheets)
    # ============================
    st.subheader("🏆 Ranking (global, votos reales en Google Sheets)")
    votes_df = load_votes()
    if votes_df.empty:
        st.info("Aún no hay votos registrados.")
    else:
        ranking = (
            votes_df.groupby("CAFE")["score"]
            .agg(["count", "mean"])
            .rename(columns={"count": "Votos", "mean": "Promedio"})
            .reset_index()
            .sort_values(["Promedio", "Votos"], ascending=[False, False])
        )
        ranking["Promedio"] = ranking["Promedio"].round(2)
        st.dataframe(ranking, use_container_width=True, hide_index=True)

    # ============================
    # Índice completo (todo el CSV, ordenado por cercanía)
    # ============================
    st.subheader("Índice completo de cafés (del más cerca al más lejos)")
    indice = cafes_all.sort_values("DIST_KM_TOTAL").copy()
    indice["DIST_KM_TOTAL"] = indice["DIST_KM_TOTAL"].round(3)
    indice["CUADRAS_TOTAL"] = indice["CUADRAS_TOTAL"].round(1)
    st.dataframe(
        indice[["CAFE", "UBICACION", "TOSTADOR", "PUNTAJE", "DIST_KM_TOTAL", "CUADRAS_TOTAL"]],
        use_container_width=True,
        hide_index=True
    )
