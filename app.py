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
# SIDEBAR - SUGERENCIAS DE LA COMUNIDAD
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
        sug_ciudad = st.selectbox("Ciudad *", ["Mar del Plata", "Buenos Aires", "La Plata", "Córdoba", "Rosario", "Otra"])
        sug_comentario = st.text_area("Comentario adicional (Opcional)", height=68)
        
        btn_enviar = st.form_submit_button("Enviar sugerencia", use_container_width=True)
        
        if btn_enviar:
            if sug_nombre == "" or sug_ubicacion == "":
                st.error("Por favor, completá el nombre y la dirección.")
            else:
                # --- MAGIA DEL FORMULARIO INVISIBLE ---
                url_formulario = "https://docs.google.com/forms/d/e/1FAIpQLSeuxnoY87VlZc01atG4oqqoYq-F7L_b5tdQcq_RM2OrdfT1sQ/formResponse"
                
                # Empaquetamos los datos
                datos_a_enviar = {
                    "entry.2123411439": tipo_aporte,
                    "entry.2080751766": sug_nombre,
                    "entry.1509178125": sug_ubicacion,
                    "entry.1244504490": sug_ciudad,
                    "entry.143951500": sug_comentario
                }
                
                # Le ponemos un disfraz a Python para que Google no lo bloquee
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                try:
                    # Enviamos el paquete a Google con el disfraz puesto
                    respuesta = requests.post(url_formulario, data=datos_a_enviar, headers=headers)
                    
                    if respuesta.status_code == 200:
                        st.success("¡Gracias por tu aporte! Lo revisaremos y actualizaremos el mapa pronto. ☕")
                    else:
                        st.error(f"Google rechazó el envío (Código {respuesta.status_code}).")
                except Exception as e:
                    st.error(f"Error técnico de conexión: {e}")


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
                padding: 12px; border-radius: 10px; margin-bottom: 25px; 
                border-left: 5px solid #5f3512; display: flex; align-items: center;">
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
tabs = st.tabs(["☕ Cafés", "🔥 Tostadores", "🔍 Buscar por Nombre"])

# ======================================================
# TAB 1 – CAFÉS
# ======================================================
with tabs[0]:
    ciudad = st.selectbox(
        "🏙️ Ciudad",
        ciudades_lista,
        index=ciudades_lista.index(st.session_state["ciudad_elegida"]),
        key="selector_tab1",
        on_change=actualizar_ciudad_tab1
    )
    
    cafes = cargar_cafes(GID_CAFES[ciudad])

    direccion = st.text_input("📍 Dirección", placeholder="Ej: Av. Colón 1500")
    radio_km = st.slider("📏 Radio de búsqueda (km)", 0.5, 5.0, 2.0, 0.5)

    tostadores_disp = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
    filtro_tostador = st.selectbox("🏷️ Filtrar por tostador", tostadores_disp)

    col_buscar, col_recomendado = st.columns(2)
    with col_buscar:
        buscar_cafes = st.button("🔍 Buscar cafés", use_container_width=True)
    with col_recomendado:
        recomendar_cafe = st.button("🎯 Café recomendado", use_container_width=True)

    if buscar_cafes:
        st.session_state["recomendacion"] = None

    if "recomendacion" not in st.session_state:
        st.session_state["recomendacion"] = None

    if "recomendacion_ciudad" not in st.session_state:
        st.session_state["recomendacion_ciudad"] = None

    necesita_recomendacion = recomendar_cafe

    if necesita_recomendacion:
        coords, _ = resolver_coordenadas(direccion, ciudad, cafes)

        if not coords:
            st.error("No se pudo encontrar la dirección 😕")
            st.stop()

        recomendados = cafes_en_radio(cafes, coords, 0.75)

        if recomendados.empty:
            st.warning("No encontramos cafés en 750 m para recomendar ☹️")
            st.session_state["recomendacion"] = None
            st.stop()

        recomendado = recomendados.sample(n=1, random_state=random.randint(0, 10_000_000)).iloc[0]

        st.session_state["recomendacion"] = {
            "CAFE": normalizar_texto(recomendado.get("CAFE")),
            "UBICACION": normalizar_texto(recomendado.get("UBICACION")),
            "TOSTADOR": normalizar_texto(recomendado.get("TOSTADOR"), fallback="Sin tostador cargado"),
            "DIST_KM": float(recomendado["DIST_KM"]),
            "LAT": recomendado["LAT"],
            "LONG": recomendado["LONG"],
            "CIUDAD": ciudad
        }
        st.session_state["recomendacion_ciudad"] = ciudad

    if st.session_state["recomendacion"] is not None and st.session_state["recomendacion_ciudad"] == ciudad:
        recomendacion = st.session_state["recomendacion"]
        distancia_txt = f"{distancia_en_cuadras(recomendacion['DIST_KM'])} cuadras"
        link_maps = f"https://www.google.com/maps/search/?api=1&query={recomendacion['LAT']},{recomendacion['LONG']}"

        st.markdown(
            """
            <style>
                .card-recomendado {
                    background: linear-gradient(180deg, #f7fff9 0%, #eefaf2 100%);
                    border: 1px solid #cfe8d7; border-radius: 14px;
                    padding: 1rem; margin-top: 0.75rem;
                }
                .card-recomendado h4 { margin: 0 0 0.5rem 0; color: #1f6f43; }
                .card-recomendado p { margin: 0.2rem 0; color: #1d2a22; }
            </style>
            """,
            unsafe_allow_html=True
        )

        left, right = st.columns([2, 1])
        with left:
            st.markdown(
                f"""
                <div class="card-recomendado">
                    <h4>☕ Recomendación del momento</h4>
                    <p><strong>Café:</strong> {recomendacion['CAFE']}</p>
                    <p><strong>Ubicación:</strong> {recomendacion['UBICACION']}</p>
                    <p><strong>Tostador:</strong> {recomendacion['TOSTADOR']}</p>
                    <p><a href="{link_maps}" target="_blank">📍 Ver en Google Maps</a></p>
                </div>
                """,
                unsafe_allow_html=True
            )

        with right:
            st.metric("Distancia", distancia_txt)
            st.metric("Ciudad", recomendacion["CIUDAD"])
            if st.button("🔄 Otra recomendación", use_container_width=True):
                coords, _ = resolver_coordenadas(direccion, ciudad, cafes)
                if not coords:
                    st.error("No se pudo encontrar la dirección 😕")
                    st.stop()

                recomendados = cafes_en_radio(cafes, coords, 0.75)
                if recomendados.empty:
                    st.warning("No encontramos cafés en 750 m para recomendar ☹️")
                    st.stop()

                recomendado = recomendados.sample(n=1, random_state=random.randint(0, 10_000_000)).iloc[0]
                st.session_state["recomendacion"] = {
                    "CAFE": normalizar_texto(recomendado.get("CAFE")),
                    "UBICACION": normalizar_texto(recomendado.get("UBICACION")),
                    "TOSTADOR": normalizar_texto(recomendado.get("TOSTADOR"), fallback="Sin tostador cargado"),
                    "DIST_KM": float(recomendado["DIST_KM"]),
                    "LAT": recomendado["LAT"],
                    "LONG": recomendado["LONG"],
                    "CIUDAD": ciudad
                }
                rerun_app()

    if buscar_cafes:
        coords, _ = resolver_coordenadas(direccion, ciudad, cafes)

        if not coords:
            st.error("No se pudo encontrar la dirección 😕")
            st.stop()

        resultado = cafes_en_radio(cafes, coords, radio_km)

        if filtro_tostador != "Todos":
            resultado = resultado[resultado["TOSTADOR"] == filtro_tostador]

        resultado = resultado.sort_values("DIST_KM")

        if resultado.empty:
            st.warning("No se encontraron cafés ☹️")
            st.stop()

        resultado["DISTANCIA"] = resultado["DIST_KM"].apply(
            lambda km: f"{int(km*1000)} m" if km < 1 else f"{km:.2f} km"
        )

        resultado["MAPS"] = resultado.apply(
            lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
            axis=1
        )

        st.subheader(f"☕ Cafés encontrados ({len(resultado)})")

        st.dataframe(
            resultado[["CAFE", "UBICACION", "TOSTADOR", "DISTANCIA", "MAPS"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Abrir")
            }
        )

        map_df = resultado.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()
        max_dist = map_df["DIST_KM"].max()

        def color_por_distancia(d):
            ratio = d / max_dist if max_dist > 0 else 0
            return [int(255 * ratio), int(255 * (1 - ratio)), 80, 180]

        map_df["color"] = map_df["DIST_KM"].apply(color_por_distancia)
        idx_mas_cercano = map_df.index[0]
        map_df.at[idx_mas_cercano, "color"] = [0, 220, 0, 230]

        layer_cafes = pdk.Layer(
            "ScatterplotLayer", data=map_df, get_position=["lon", "lat"],
            get_radius=90, get_fill_color="color", pickable=True
        )

        layer_user = pdk.Layer(
            "ScatterplotLayer", data=pd.DataFrame([{"lat": coords[0], "lon": coords[1]}]),
            get_position=["lon", "lat"], get_radius=130, get_fill_color=[0, 120, 255, 220]
        )

        view_state = pdk.ViewState(latitude=coords[0], longitude=coords[1], zoom=14)
        deck = pdk.Deck(
            layers=[layer_cafes, layer_user], initial_view_state=view_state,
            tooltip={"text": "{CAFE}\n{UBICACION}\n{DISTANCIA}"}
        )
        st.pydeck_chart(deck, use_container_width=True)

# ======================================================
# TAB 2 – TOSTADORES
# ======================================================
with tabs[1]:
    ciudad_tost = st.selectbox(
        "🏙️ Ciudad", ciudades_lista,
        index=ciudades_lista.index(st.session_state["ciudad_elegida"]),
        key="selector_tab2", on_change=actualizar_ciudad_tab2
    )

    st.subheader("🔥 Tostadores")

    st.markdown(
        """
        <style>
            .tostador-card {
                background: linear-gradient(180deg, #fffef9 0%, #fff9f1 100%);
                border: 1px solid #f0e1cf; border-radius: 14px; padding: 1rem;
                min-height: 290px; box-shadow: 0 2px 8px rgba(83, 51, 20, 0.08);
                display: flex; flex-direction: column; justify-content: space-between; gap: 0.65rem;
            }
            .tostador-title { margin: 0; color: #5f3512; font-size: 1.08rem; }
            .tostador-chip {
                display: inline-block; padding: 0.22rem 0.55rem; border-radius: 999px;
                background: #f5e6d6; color: #7c4716; font-size: 0.83rem; font-weight: 600;
            }
            .tostador-desc { margin: 0; color: #3e2c1d; line-height: 1.35; font-size: 0.92rem; }
            .ig-btn {
                display: inline-block; background: linear-gradient(90deg, #f58529, #dd2a7b 60%, #8134af);
                color: white !important; padding: 0.45rem 0.7rem; border-radius: 8px;
                font-weight: 700; text-decoration: none; width: fit-content;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    tostadores_ciudad = tostadores[tostadores["CIUDAD"].str.contains(ciudad_tost, case=False, na=False)]

    if tostadores_ciudad.empty:
        st.info("No hay tostadores cargados para esta ciudad.")
    else:
        tostadores_ciudad = tostadores_ciudad.fillna("-").reset_index(drop=True)
        for i in range(0, len(tostadores_ciudad), 3):
            cols = st.columns(3)
            fila = tostadores_ciudad.iloc[i:i + 3]
            for col, (_, r) in zip(cols, fila.iterrows()):
                with col:
                    st.markdown(
                        f"""
                        <div class="tostador-card"> 
                            <div>
                                <h4 class="tostador-title">☕ {r['TOSTADOR']}</h4>
                                <span class="tostador-chip">🌱 {r['VARIEDADES']}</span>
                                <p class="tostador-desc">{r['DESCRIPCION']}</p>
                            </div>
                            <a class="ig-btn" href="{r['INSTAGRAM']}" target="_blank">📸 Ver Instagram</a>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

# ======================================================
# TAB 3 – BUSCADOR GLOBAL POR NOMBRE
# ======================================================
with tabs[2]:
    st.subheader("🔍 Encontrá tu café favorito")
    
    if not todos_los_cafes.empty:
        nombres_cafes = sorted(todos_los_cafes["CAFE"].dropna().unique().tolist())
        cafe_buscado = st.selectbox(
            "Escribí o seleccioná el nombre del café:",
            options=[""] + nombres_cafes, index=0
        )
        
        if cafe_buscado != "":
            resultados = todos_los_cafes[todos_los_cafes["CAFE"] == cafe_buscado].copy()
            st.success(f"Encontramos {len(resultados)} sucursal(es) para **{cafe_buscado}**:")
            
            resultados["MAPS"] = resultados.apply(
                lambda r: f"https://www.google.com/maps/search/?api=1&query={r['LAT']},{r['LONG']}",
                axis=1
            )
            
            st.dataframe(
                resultados[["CAFE", "UBICACION", "CIUDAD", "TOSTADOR", "MAPS"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "MAPS": st.column_config.LinkColumn("Google Maps", display_text="📍 Ver en el mapa")
                }
            )
            
            st.markdown("### 🗺️ Ubicación")
            map_df = resultados.rename(columns={"LAT": "lat", "LONG": "lon"}).copy()
            centro_lat, centro_lon = map_df["lat"].mean(), map_df["lon"].mean()
            
            layer_busqueda = pdk.Layer(
                "ScatterplotLayer", data=map_df, get_position=["lon", "lat"],
                get_radius=150, get_fill_color=[255, 90, 60, 220], pickable=True
            )
            
            zoom_inicial = 14 if len(resultados) == 1 else 11
            view_state = pdk.ViewState(latitude=centro_lat, longitude=centro_lon, zoom=zoom_inicial)
            deck_busqueda = pdk.Deck(
                layers=[layer_busqueda], initial_view_state=view_state,
                tooltip={"text": "{CAFE}\n{UBICACION}\n{CIUDAD}"}
            )
            st.pydeck_chart(deck_busqueda, use_container_width=True)
            
    else:
        st.info("Cargando la base de datos global...")
