import streamlit as st
import pandas as pd
from geopy.distance import geodesic

st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")

st.title("☕ Buscador de Cafés Cercanos")

cafes = pd.read_csv("Cafes.csv")

st.write("Permitir ubicación para encontrar cafés cercanos.")

user_location = st.experimental_get_query_params()

lat = st.number_input("Tu latitud")
lon = st.number_input("Tu longitud")

if st.button("Buscar cafés cercanos"):

    if lat != 0 and lon != 0:

        user_coords = (lat, lon)

        cafes["Distancia_km"] = cafes.apply(
            lambda row: geodesic(user_coords, (row["LAT"], row["LONG"])).km,
            axis=1
        )

        cafes_ordenado = cafes.sort_values("Distancia_km")

        st.subheader("☕ Cafés más cercanos")

        for index, row in cafes_ordenado.head(5).iterrows():
            st.markdown(f"""
            ### {row['CAFE']}
            📍 {row['UBICACION']}  
            ⭐ Puntaje: {row['PUNTAJE']}  
            🔥 Tostador: {row['TOSTADOR']}  
            📏 Distancia: {row['Distancia_km']:.2f} km
            ---
            """)

