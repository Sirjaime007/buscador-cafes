import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="wide")

st.title("☕ Buscador de Cafés Cercanos")

# Leer base real
cafes = pd.read_csv("cafes.csv")

direccion = st.text_input("Ingresá tu dirección")

if st.button("Buscar cafés cercanos"):

    if direccion:
        geolocator = Nominatim(user_agent="buscador_cafes")
        location = geolocator.geocode(direccion)

        if location:
            user_location = (location.latitude, location.longitude)

            cafes["Distancia_km"] = cafes.apply(
                lambda row: geodesic(user_location, (row["LAT"], row["LONG"])).km,
                axis=1
            )

            cafes_ordenado = cafes.sort_values("Distancia_km")

            st.subheader("☕ Los cafés más cercanos a vos")

            for index, row in cafes_ordenado.head(5).iterrows():
                st.markdown(f"""
                ### {row['CAFE']}
                📍 {row['UBICACION']}  
                🔥 Tostador: {row['TOSTADOR']}  
                ⭐ Puntaje: {row['PUNTAJE']}  
                📏 Tamaño: {row['Tamaño Local']}  
                🗓 Abre domingos: {row['¿ Abre los domingos ?']}  
                📍 Distancia: {row['Distancia_km']:.2f} km
                ---
                """)
        else:
            st.error("No se pudo encontrar la dirección. Probá escribirla completa.")
    else:
        st.warning("Por favor ingresá una dirección.")
