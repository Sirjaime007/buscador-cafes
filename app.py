import streamlit as st
import pandas as pd
from geopy.geocoders import ArcGIS
from geopy.distance import geodesic
import pydeck as pdk

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
# GOOGLE SHEETS CONFIG
# =========================
SPREADSHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"

GID_CAFES = {
    "Mar del Plata": "0",
    "Buenos Aires": "1296176686",
    "La Plata": "208452991",
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

    return df.dropna(subset=["LAT", "LONG"])


@st.cache_data(ttl=600)
def cargar_tostadores():
    try:
        return pd.read_csv(sheet_url(GID_TOSTADORES), dtype=str)
    except Exception:
        return pd.DataFrame(
            columns=["TOSTADOR", "VARIEDADES", "DESCRIPCION", "INSTAGRAM", "CIUDAD"]
        )


# =========================
# GEOCODER
# =========================
@st.cache_resource
def get_geocoder():
    return ArcGIS(timeout=10)


def geocodificar(direccion, ciudad):
    geo = get_geocoder()
    loc = geo.geocode(f"{direccion}, {ciudad}, Buenos Aires, Argentina")
    if loc:
        return loc.latitude, loc.longitude
    return None


# =========================
# UI – SELECT CITY
# =========================
ciudad = st.selectbox(
    "🏙️ Ciudad",
    list(GID_CAFES.keys())
)

cafes = cargar_cafes(GID_CAFES[ciudad])
tostadores = cargar_tostadores()

tabs = st.tabs(["☕ Cafés", "🔥 Tostadores"])

# ======================================================
# TAB 1 – CAFÉS
# ======================================================
with tabs[0]:
    direccion = st.text_input(
        "📍 Dirección",
        placeholder="Ej: Av. Colón 1500"
    )

    radio_km = st.slider(
        "📏 Radio de búsqueda (km)",
        0.5, 5.0, 2.0, 0.5
    )

    tostadores_disp = ["Todos"] + sorted(cafes["TOSTADOR"].dropna().unique())
    filtro_tostador = st.selectbox(
        "🏷️ Filtrar por tostador",
        tostadores_disp
    )

    if st.button("🔍 Buscar cafés"):
        coords = geocodificar(direccion, ciudad)

        if not coords:
            st.error("No se pudo encontrar la dirección 😕")
            st.stop()

        cafes_calc = cafes.copy()
        cafes_calc["DIST_KM"] = cafes_calc.apply(
            lambda r: geodesic(coords, (r["LAT"], r["LONG"])).km,
            axis=1
        )

        resultado = cafes_calc[cafes_calc["DIST_KM"] <= radio_km]

        if filtro_tostador != "Todos":
            resultado = resultado[
                resultado["TOSTADOR"] == filtro_tostador
            ]

        resultado = resultado.sort_values("DIST_KM")

        if resultado.empty:
            st.warning("No se encontraron cafés ☹️")
            st.stop()

        # Texto distancia
        resultado["DISTANCIA"] = resultado["DIST_KM"].apply(
            lambda km: f"{int(km*1000)} m" if km < 1 else f"{km:.2f} km"
        )

        resultado["MAPS"] = resultado.apply(
            lambda r: (
                "https://www.google.com/maps/search/?api=1"
                f"&query={r['LAT']},{r['LONG']}"
            ),
            axis=1
        )

        st.subheader(f"☕ Cafés encontrados ({len(resultado)})")

        st.dataframe(
            resultado[
                ["CAFE", "UBICACION", "TOSTADOR", "DISTANCIA", "MAPS"]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "MAPS": st.column_config.LinkColumn(
                    "Google Maps",
                    display_text="📍 Abrir"
                )
            }
        )

        # =========================
        # MAPA – HEATMAP LIGHT
        # =========================
        map_df = resultado.rename(
            columns={"LAT": "lat", "LONG": "lon"}
        ).copy()

        max_dist = map_df["DIST_KM"].max()

        def color_por_distancia(d):
            ratio = d / max_dist if max_dist > 0 else 0
            r = int(255 * ratio)
            g = int(255 * (1 - ratio))
            return [r, g, 80, 180]

        map_df["color"] = map_df["DIST_KM"].apply(color_por_distancia)

        idx_mas_cercano = map_df.index[0]
        map_df.at[idx_mas_cercano, "color"] = [0, 220, 0, 230]

        layer_cafes = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["lon", "lat"],
            get_radius=90,
            get_fill_color="color",
            pickable=True
        )

        layer_user = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{
                "lat": coords[0],
                "lon": coords[1]
            }]),
            get_position=["lon", "lat"],
            get_radius=130,
            get_fill_color=[0, 120, 255, 220]
        )

        view_state = pdk.ViewState(
            latitude=coords[0],
            longitude=coords[1],
            zoom=14
        )

        deck = pdk.Deck(
            layers=[layer_cafes, layer_user],
            initial_view_state=view_state,
            tooltip={
                "text": "{CAFE}\n{UBICACION}\n{DISTANCIA}"
            }
        )

        st.pydeck_chart(deck, use_container_width=True)

# ======================================================
# TAB 2 – TOSTADORES
# ======================================================
with tabs[1]:
    st.subheader("🔥 Tostadores")

    st.markdown(
        """
        <style>
            .tostador-card {
                background: linear-gradient(180deg, #fffef9 0%, #fff9f1 100%);
                border: 1px solid #f0e1cf;
                border-radius: 14px;
                padding: 1rem;
                min-height: 290px;
                box-shadow: 0 2px 8px rgba(83, 51, 20, 0.08);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: 0.65rem;
            }
            .tostador-title {
                margin: 0;
                color: #5f3512;
                font-size: 1.08rem;
            }
            .tostador-chip {
                display: inline-block;
                padding: 0.22rem 0.55rem;
                border-radius: 999px;
                background: #f5e6d6;
                color: #7c4716;
                font-size: 0.83rem;
                font-weight: 600;
            }
            .tostador-desc {
                margin: 0;
                color: #3e2c1d;
                line-height: 1.35;
                font-size: 0.92rem;
            }
            .ig-btn {
                display: inline-block;
                background: linear-gradient(90deg, #f58529, #dd2a7b 60%, #8134af);
                color: white !important;
                padding: 0.45rem 0.7rem;
                border-radius: 8px;
                font-weight: 700;
                text-decoration: none;
                width: fit-content;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    tostadores_ciudad = tostadores[
        tostadores["CIUDAD"]
        .str.contains(ciudad, case=False, na=False)
    ]

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

