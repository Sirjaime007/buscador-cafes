import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from geopy.geocoders import ArcGIS
import pydeck as pdk
import uuid
import time
import os
from datetime import datetime
import json
import streamlit.components.v1 as components

VOTES_FILE = "votes.csv"  # persistencia de votos

# ================================
# Configuración general
# ================================
st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")
st.title("☕ Buscador de Cafés Cercanos")
st.write("Ingresá una **dirección de Mar del Plata** y te mostramos los cafés cercanos. ¡Ahora también podés **votar** tu favorito!")

# ================================
# Utilidad: Cookie voter_id (persistente en el navegador)
# ================================
def ensure_voter_cookie():
    """
    Asegura que exista una cookie 'voter_id' en el navegador del usuario.
    Si no existe, crea una con un UUID y la devuelve.
    """
    # Componente HTML para leer/escribir la cookie
    cookie_js = """
    <script>
    (function() {
        function getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        }
        function setCookie(name, value, days) {
            const d = new Date();
            d.setTime(d.getTime() + (days*24*60*60*1000));
            const expires = "expires=" + d.toUTCString();
            document.cookie = name + "=" + value + ";" + expires + ";path=/;SameSite=Lax";
        }

        let voter = getCookie("voter_id");
        if (!voter) {
            // Creamos un UUID simple (no 100% RFC pero suficiente para identificar al browser)
            voter = self.crypto && crypto.randomUUID ? crypto.randomUUID() : (Date.now()+"-"+Math.random());
            setCookie("voter_id", voter, 3650); // 10 años
        }
        // Enviamos el valor a Streamlit
        const streamlitDoc = window.parent.document;
        const el = streamlitDoc.getElementById("voter_cookie_sink");
        if (el) { el.value = voter; el.dispatchEvent(new Event("change", { bubbles: true })); }
    })();
    </script>
    """
    # Input oculto para recoger la cookie hacia Streamlit
    voter_id = st.text_input("voter_cookie_sink", key="voter_cookie_sink", label_visibility="collapsed")
    components.html(cookie_js, height=0, scrolling=False)
    return voter_id

voter_id = ensure_voter_cookie()

# ================================
# Cargar CSV de cafés (tildes + decimales OK)
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
# Votos: carga/guardado
# ================================
def load_votes() -> pd.DataFrame:
    if not os.path.exists(VOTES_FILE):
        return pd.DataFrame(columns=["voter_id", "CAFE", "score", "ts"])
    try:
        df = pd.read_csv(VOTES_FILE, encoding="utf-8")
        # normalizo tipos
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        return df.dropna(subset=["voter_id", "CAFE"])
    except Exception:
        return pd.DataFrame(columns=["voter_id", "CAFE", "score", "ts"])

def upsert_vote(voter_id: str, cafe_name: str, score: float):
    """
    Inserta o actualiza el voto del usuario para ese café (1–10).
    """
    votes = load_votes()
    now_iso = datetime.utcnow().isoformat()

    # Si ya votó este café, actualizamos
    mask = (votes["voter_id"] == voter_id) & (votes["CAFE"] == cafe_name)
    if mask.any():
        votes.loc[mask, ["score", "ts"]] = [score, now_iso]
    else:
        votes = pd.concat([
            votes,
            pd.DataFrame([{"voter_id": voter_id, "CAFE": cafe_name, "score": score, "ts": now_iso}])
        ], ignore_index=True)

    votes.to_csv(VOTES_FILE, index=False, encoding="utf-8")

def ranking_from_votes(cafes_df: pd.DataFrame, votes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula ranking con promedio bayesiano:
    score_adj = (v/(v+m))*avg + (m/(v+m))*C
    donde:
      v = cantidad de votos del café
      avg = promedio del café
      C = promedio global
      m = mínimo de votos para estabilizar (ej: 5)
    """
    if votes_df.empty:
        out = cafes_df[["CAFE"]].copy()
        out["votos"] = 0
        out["promedio"] = np.nan
        out["score_ajustado"] = np.nan
        return out

    agg = votes_df.groupby("CAFE")["score"].agg(["count", "mean"]).rename(columns={"count": "votos", "mean": "promedio"}).reset_index()
    global_mean = votes_df["score"].mean()
    m = 5  # umbral de suavizado
    agg["score_ajustado"] = (agg["votos"]/(agg["votos"]+m))*agg["promedio"] + (m/(agg["votos"]+m))*global_mean

    # Unimos con cafés para no perder los que aún no tienen votos
    out = cafes_df[["CAFE"]].merge(agg, on="CAFE", how="left").fillna({"votos": 0})
    return out

# ================================
# Inputs
# ================================
col1, col2, col3 = st.columns([3, 1, 1])

with col1:
    direccion = st.text_input("Dirección", "Av. Colón 1500")

with col2:
    radio_km = st.number_input("Radio (km)", min_value=0.1, value=2.0, step=0.1)

with col3:
    agrupar = st.checkbox("Agrupar (zoom alejado)", value=True)

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
    # VOTAR (UI por fila)
    # ============================
    st.caption("🗳️ **Votá tu favorito** (1 a 10). Podés actualizar tu voto cuando quieras.")
    vote_cols = st.columns([1, 3, 2, 2, 2, 2])
    vote_cols[0].markdown("**#**")
    vote_cols[1].markdown("**Café**")
    vote_cols[2].markdown("**Puntaje**")
    vote_cols[3].markdown("**Votar**")
    vote_cols[4].markdown("**Dist. (km)**")
    vote_cols[5].markdown("**Cuadras**")

    for idx, row in resultado.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([1, 3, 2, 2, 2, 2])
        c1.write(idx+1)
        c2.write(f"{row['CAFE']} — {row['UBICACION']}")
        score_val = c3.slider(f"punt_{idx}", 1.0, 10.0, 8.0, 0.5, label_visibility="collapsed", key=f"score_{idx}")
        if c4.button("Votar", key=f"vote_{idx}", help="Guarda/actualiza tu voto para este café"):
            if not voter_id:
                st.error("No pudimos leer tu cookie de votante. Refrescá la página e intentá de nuevo.")
            else:
                upsert_vote(voter_id=voter_id, cafe_name=row["CAFE"], score=score_val)
                st.success(f"¡Voto registrado para **{row['CAFE']}** con {score_val} puntos!")

        c5.write(round(row["DIST_KM"], 3))
        c6.write(round(row["CUADRAS"], 1))

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

    # ============================
    # RANKING (promedio + votos + score ajustado)
    # ============================
    st.subheader("🏆 Ranking por votos de la gente")
    votes_df = load_votes()
    ranking = ranking_from_votes(cafes_df=cafes, votes_df=votes_df)

    # Mostrar solo cafés dentro del radio para ranking local (opcional)
    ranking_local = ranking.merge(resultado[["CAFE"]], on="CAFE", how="inner").copy()

    # Orden: score ajustado (desc), luego votos (desc)
    ranking_local = ranking_local.sort_values(["score_ajustado", "votos"], ascending=[False, False]).reset_index(drop=True)

    # Mostrar limpio
    ranking_show = ranking_local.copy()
    ranking_show["promedio"] = ranking_show["promedio"].round(2)
    ranking_show["score_ajustado"] = ranking_show["score_ajustado"].round(2)

    st.dataframe(
        ranking_show.rename(columns={
            "CAFE": "Café",
            "votos": "Votos",
            "promedio": "Promedio",
            "score_ajustado": "Ranking (ajustado)"
        }),
        use_container_width=True,
        hide_index=True
    )

    # ================================
    # MAPA (IconLayer + color por puntaje + densidad opcional)
    # ================================
    st.subheader("Mapa")

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
        size_scale=8,
        icon_atlas=icon_atlas,
        icon_mapping=icon_mapping,
        get_color="COLOR",
        pickable=True
    )

    heat_layer = pdk.Layer(
        "HeatmapLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_weight="PUNTAJE",
        radius_pixels=40,
    ) if agrupar else None

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
        map_style=None
    )
    st.pydeck_chart(deck, use_container_width=True, height=520)
