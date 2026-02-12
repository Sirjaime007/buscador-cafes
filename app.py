import streamlit as st
import pandas as pd
from geopy.distance import geodesic

st.set_page_config(page_title="Buscador de Cafés", page_icon="☕", layout="centered")

st.title("☕ Buscador de Cafés Cercanos")

cafes = pd.DataFrame({
    "Nombre": ["Cafe Centro", "Cafe Güemes", "Cafe Puerto"],
    "Latitud": [-38.0000, -38.0050, -38.0100],
    "Longitud": [-57.5500, -57.5450, -57.5400]
})

lat_user = st.number_input("Tu latitud", format="%.6f")
lon_user = st.number_input("Tu longitud", format="%.6f")

if st.button("Buscar cafés cercanos"):

    if lat_user != 0 and lon_user != 0:
        user_location = (lat_user, lon_user)

        cafes["Distancia_km"] = cafes.apply(
            lambda row: geodesic(user_location, (row["Latitud"], row["Longitud"])).km,
            axis=1
        )

        cafes_ordenado = cafes.sort_values("Distancia_km")

        st.subheader("Los 3 cafés más cercanos:")

        for index, row in cafes_ordenado.head(3).iterrows():
            st.write(f"☕ {row['Nombre']} - {row['Distancia_km']:.2f} km")
    else:
        st.warning("Ingresá latitud y longitud válidas")
