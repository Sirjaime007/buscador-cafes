import streamlit as st
import pandas as pd
import random
import re
import unicodedata
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk
import requests

# =========================
# CONFIG APP
# =========================
st.set_page_config(
    page_title="Buscador de Cafés",
    page_icon="☕",
    layout="wide"
)

st.title("☕ Buscador de Cafés")

# =========================
# SIDEBAR - SUGERENCIAS DE LA COMUNIDAD (TELEGRAM)
# =========================
with st.sidebar:

    st.header("💡 Ayudanos a mejorar")
    st.markdown("¿Falta tu café favorito o encontraste algún dato desactualizado? ¡Avisanos!")

    with st.form("form_sugerencia", clear_on_submit=True):

        tipo_aporte = st.radio(
            "¿Qué querés reportar?",
            ["✨ Nuevo local", "✏️ Corregir datos", "❌ Local cerrado"]
        )

        sug_nombre = st.text_input("Nombre del local *")
        sug_ubicacion = st.text_input("Dirección exacta *")
        sug_ciudad = st.selectbox(
            "Ciudad *",
            ["Mar del Plata", "Buenos Aires", "La Plata", "Córdoba", "Rosario", "Otra"]
        )
        sug_comentario = st.text_area("Comentario adicional (Opcional)", height=68)

        btn_enviar = st.form_submit_button("Enviar sugerencia", use_container_width=True)

        if btn_enviar:
            if sug_nombre == "" or sug_ubicacion == "":
                st.error("Por favor, completá el nombre y la dirección.")
            else:
                try:
                    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
                    CHAT_ID = str(st.secrets["CHAT_ID"])

                    mensaje = (
                        f"🚨 NUEVO REPORTE EN LA APP 🚨\n\n"
                        f"📌 Tipo: {tipo_aporte}\n"
                        f"☕ Café: {sug_nombre}\n"
                        f"📍 Dirección: {sug_ubicacion}\n"
                        f"🏙️ Ciudad: {sug_ciudad}\n"
                        f"💬 Comentario: {sug_comentario if sug_comentario else 'Sin comentarios'}"
                    )

                    url_telegram = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

                    respuesta = requests.post(
                        url_telegram,
                        data={"chat_id": CHAT_ID, "text": mensaje}
                    )

                    if respuesta.status_code == 200:
                        st.success("¡Gracias por tu aporte! Lo revisaremos pronto. ☕")
                    else:
                        st.error("Hubo un problema enviando el mensaje a Telegram.")

                except KeyError:
                    st.error("Falta guardar las claves secretas en la configuración de Streamlit Cloud.")
                except Exception as e:
                    st.error(f"Error técnico: {e}")

# =========================
# GOOGLE SHEETS CONFIG
# =========================
SPREADSHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

GID_CAFES = {
    "Mar del Plata": "0",
    "Buenos Aires": "1296176686",
    "La Plata": "208452991",
    "Córdoba": "1250014567",
    "Rosario": "1691979590",
}

GID_TOSTADORES = "1590442133"


def sheet_url(gid: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
        f"/gviz/tq?tqx=out:csv&gid={gid}"
    )

# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=600)
def cargar_cafes(gid):
    try:
        df = pd.read_csv(sheet_url(gid), dtype=str)
    except Exception:
        df = pd.read_csv("Cafes.csv", dtype=str)

    df["LAT"] = pd.to_numeric(
        df["LAT"].str.replace(",", ".", regex=False),
        errors="coerce"
    )

    df["LONG"] = pd.to_numeric(
        df["LONG"].str.replace(",", ".", regex=False),
        errors="coerce"
    )

    df = df.dropna(subset=["LAT", "LONG"])
    df = df[(df["LAT"] >= -90) & (df["LAT"] <= 90)]
    df = df[(df["LONG"] >= -180) & (df["LONG"] <= 180)]

    return df


@st.cache_data(ttl=600)
def cargar_tostadores():
    try:
        return pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str)
    except Exception:
        return pd.DataFrame(
            columns=["TOSTADOR", "VARIEDADES", "DESCRIPCION", "INSTAGRAM", "CIUDAD"]
        )


@st.cache_data(ttl=600)
def cargar_todos_los_cafes():
    dfs = []

    for ciudad_nombre, gid in GID_CAFES.items():
        try:
            df_ciudad = cargar_cafes(gid).copy()
            df_ciudad["CIUDAD"] = ciudad_nombre
            dfs.append(df_ciudad)
        except Exception:
            continue

    if dfs:
        return pd.concat(dfs, ignore_index=True)

    return pd.DataFrame()

# =========================
# GEOCODER & LOGIC
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)


def geocodificar(direccion, ciudad):
    if not direccion or not direccion.strip():
        return None

    geo = get_geocoder()

    try:
        loc = geo.geocode(f"{direccion}, {ciudad}, Argentina")
    except Exception:
        return None

    if loc:
        return loc.latitude, loc.longitude

    return None


def cafes_en_radio(cafes_df, coords, radio_km):
    cafes_calc = cafes_df.copy()

    cafes_calc["DIST_KM"] = cafes_calc.apply(
        lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
        axis=1
    )

    return cafes_calc[cafes_calc["DIST_KM"] <= radio_km]


def normalizar_texto(valor, fallback="Sin dato"):
    if pd.isna(valor):
        return fallback

    texto = str(valor).strip()

    if texto == "" or texto.lower() == "nan":
        return fallback

    return texto


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def distancia_en_cuadras(dist_km):
    metros = dist_km * 1000
    cuadras = int((metros + 99) // 100)
    return max(cuadras, 1)


def texto_normalizado(valor):
    texto = normalizar_texto(valor, fallback="")
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def geocodificar_desde_cafes(direccion, cafes_df):
    direccion_norm = texto_normalizado(direccion)

    if not direccion_norm:
        return None

    tokens = [t for t in direccion_norm.split() if len(t) >= 3]

    if not tokens:
        tokens = direccion_norm.split()

    candidatos = cafes_df.copy()

    candidatos["UBICACION_NORM"] = candidatos["UBICACION"].fillna("").apply(texto_normalizado)
    candidatos["CAFE_NORM"] = candidatos["CAFE"].fillna("").apply(texto_normalizado)

    def score(row):
        texto = f"{row['UBICACION_NORM']} {row['CAFE_NORM']}"
        return sum(1 for tok in tokens if tok in texto)

    candidatos["MATCH"] = candidatos.apply(score, axis=1)

    mejor = candidatos.sort_values("MATCH", ascending=False).iloc[0]

    if mejor["MATCH"] <= 0:
        return None

    return float(mejor["LAT"]), float(mejor["LONG"])


def resolver_coordenadas(direccion, ciudad, cafes_df):
    coords = geocodificar(direccion, ciudad)

    if coords:
        return coords, "online"

    coords_local = geocodificar_desde_cafes(direccion, cafes_df)

    if coords_local:
        return coords_local, "local"

    return None, None

# =========================
# UI – CONTADOR GLOBAL
# =========================
todos_los_cafes = cargar_todos_los_cafes()
total_cafeterias = len(todos_los_cafes) if not todos_los_cafes.empty else 0

st.markdown(
    f"""
    <div style="background: linear-gradient(90deg, #f0e1cf 0%, #fdf8f2 100%);
                padding: 12px;
                border-radius: 10px;
                margin-bottom: 25px;
                border-left: 5px solid #5f3512;
                display: flex;
                align-items: center;">
        <h4 style="margin: 0; color: #5f3512; font-size: 1.1rem;">
            📍 Total cafeterías registradas: <strong>{total_cafeterias}</strong>
        </h4>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# UI – SELECT CITY & TABS
# =========================
ciudades_lista = list(GID_CAFES.keys())

if "ciudad_elegida" not in st.session_state:
    st.session_state["ciudad_elegida"] = ciudades_lista[0]


def actualizar_ciudad_tab1():
    st.session_state["ciudad_elegida"] = st.session_state["selector_tab1"]


def actualizar_ciudad_tab2():
    st.session_state["ciudad_elegida"] = st.session_state["selector_tab2"]


tostadores = cargar_tostadores()

tabs = st.tabs([
    "☕ Cafés",
    "🔥 Tostadores",
    "🔍 Buscar por Nombre"
])# ======================================================
# TAB 1 – CAFÉS
# ======================================================
with tabs[0]:

    st.selectbox(
        "Seleccioná tu ciudad",
        ciudades_lista,
        key="selector_tab1",
        on_change=actualizar_ciudad_tab1
    )

    ciudad = st.session_state["ciudad_elegida"]

    cafes = cargar_cafes(GID_CAFES[ciudad])

    direccion = st.text_input("Ingresá tu dirección")

    radio_km = st.slider(
        "Radio de búsqueda (km)",
        min_value=1,
        max_value=20,
        value=5
    )

    if st.button("Buscar cafeterías cercanas"):

        if not direccion:
            st.warning("Ingresá una dirección primero.")
        else:
            coords, modo = resolver_coordenadas(direccion, ciudad, cafes)

            if not coords:
                st.error("No se pudo encontrar la ubicación.")
            else:

                cafes_cercanos = cafes_en_radio(cafes, coords, radio_km)

                if cafes_cercanos.empty:
                    st.info("No se encontraron cafeterías en ese radio.")
                else:

                    cafes_cercanos = cafes_cercanos.sort_values("DIST_KM")

                    st.success(f"Se encontraron {len(cafes_cercanos)} cafeterías cercanas.")

                    for _, row in cafes_cercanos.iterrows():

                        nombre = normalizar_texto(row.get("CAFE"))
                        ubicacion = normalizar_texto(row.get("UBICACION"))
                        distancia = row.get("DIST_KM", 0)

                        cuadras = distancia_en_cuadras(distancia)

                        st.markdown(
                            f"""
                            **☕ {nombre}**  
                            📍 {ubicacion}  
                            🚶 {cuadras} cuadras aprox.
                            """
                        )

                    st.subheader("🗺️ Mapa")

                    mapa_df = cafes_cercanos[["LAT", "LONG"]].copy()

                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=mapa_df,
                        get_position='[LONG, LAT]',
                        get_radius=60,
                        pickable=True
                    )

                    view_state = pdk.ViewState(
                        latitude=coords[0],
                        longitude=coords[1],
                        zoom=13
                    )

                    deck = pdk.Deck(
                        layers=[layer],
                        initial_view_state=view_state,
                        tooltip={"text": "Cafetería"}
                    )

                    st.pydeck_chart(deck)

# ======================================================
# TAB 2 – TOSTADORES
# ======================================================
with tabs[1]:

    st.selectbox(
        "Seleccioná ciudad",
        ciudades_lista,
        key="selector_tab2",
        on_change=actualizar_ciudad_tab2
    )

    ciudad = st.session_state["ciudad_elegida"]

    if tostadores.empty:
        st.info("No hay tostadores cargados.")
    else:

        tostadores_ciudad = tostadores[
            tostadores["CIUDAD"] == ciudad
        ]

        if tostadores_ciudad.empty:
            st.info("No hay tostadores en esta ciudad.")
        else:

            for _, row in tostadores_ciudad.iterrows():

                nombre = normalizar_texto(row.get("TOSTADOR"))
                variedades = normalizar_texto(row.get("VARIEDADES"))
                descripcion = normalizar_texto(row.get("DESCRIPCION"))
                instagram = normalizar_texto(row.get("INSTAGRAM"))

                st.markdown(
                    f"""
                    ### 🔥 {nombre}
                    **Variedades:** {variedades}  
                    **Descripción:** {descripcion}  
                    **Instagram:** {instagram}
                    """
                )

# ======================================================
# TAB 3 – BUSCAR POR NOMBRE
# ======================================================
with tabs[2]:

    st.subheader("Buscar cafetería por nombre")

    ciudad_busqueda = st.selectbox(
        "Seleccioná ciudad",
        ciudades_lista,
        key="selector_tab3"
    )

    cafes = cargar_cafes(GID_CAFES[ciudad_busqueda])

    nombre_busqueda = st.text_input("Nombre del café")

    if nombre_busqueda:

        nombre_norm = texto_normalizado(nombre_busqueda)

        cafes["NOMBRE_NORM"] = cafes["CAFE"].fillna("").apply(texto_normalizado)

        resultados = cafes[
            cafes["NOMBRE_NORM"].str.contains(nombre_norm, na=False)
        ]

        if resultados.empty:
            st.info("No se encontraron coincidencias.")
        else:

            for _, row in resultados.iterrows():

                nombre = normalizar_texto(row.get("CAFE"))
                ubicacion = normalizar_texto(row.get("UBICACION"))

                st.markdown(
                    f"""
                    **☕ {nombre}**  
                    📍 {ubicacion}
                    """
                )
