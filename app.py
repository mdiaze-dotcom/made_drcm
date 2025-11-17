import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date

st.set_page_config(page_title="Actualización DRCM", layout="wide")

# ---------------------------
# 1. Conexión a Google Sheets
# ---------------------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

gc = gspread.authorize(credentials)

SHEET_ID = "1mDeXDyKTZjNmRK8TnSByKbm3ny_RFhT4Rvjpqwekvjg"
SHEET_NAME = "Hoja 1"

sh = gc.open_by_key(SHEET_ID)
worksheet = sh.worksheet(SHEET_NAME)

# Leer datos
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# ---------------------------
# 2. Normalizar nombres y tipos
# ---------------------------
def parse_fecha(fecha_str):
    """Convierte fechas dd/mm/yyyy o dd/mm/yyyy HH:MM:SS a objeto datetime."""
    if not fecha_str:
        return None
    try:
        return datetime.strptime(fecha_str, "%d/%m/%Y %H:%M:%S")
    except:
        try:
            return datetime.strptime(fecha_str, "%d/%m/%Y")
        except:
            return None

# Convertir fechas
df["Fecha de Expediente"] = df["Fecha de Expediente"].apply(parse_fecha)
df["Fecha Pase DRCM"] = df["Fecha Pase DRCM"].apply(parse_fecha)

# ---------------------------
# 3. Selección de dependencia
# ---------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede_seleccionada = st.sidebar.selectbox("Seleccione Dependencia", dependencias)

clave_ingresada = st.sidebar.text_input("Ingrese clave de acceso", type="password")

CLAVES = {
    "LIMA": "LIMA2025",
    "CALLAO": "CALLAO2025",
    "AREQUIPA": "AREQUIPA2025"
}

if sede_seleccionada not in CLAVES:
    st.error("No existe clave configurada para esta dependencia.")
    st.stop()

if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Ingrese la clave correcta para continuar.")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------
# 4. Filtrar expedientes pendientes
# ---------------------------
df_filtrado = df[
    (df["Dependencia"].str.strip().str.upper() == sede_seleccionada.strip().upper()) &
    (df["Estado Trámite"].str.strip().str.upper() == "PENDIENTE")
]

if df_filtrado.empty:
    st.info("No existen expedientes pendientes para esta dependencia.")
    st.stop()

# ---------------------------
# 5. Mostrar y actualizar registros
# ---------------------------
st.subheader("Expedientes Pendientes")

for idx, row in df_filtrado.iterrows():
    with st.expander(f"Expediente {row['Número de Expediente']}"):
        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=row["Fecha Pase DRCM"].date() if isinstance(row["Fecha Pase DRCM"], datetime) else date.today(),
            key=f"fecha_{idx}"
        )

        if st.button("Guardar", key=f"guardar_{idx}"):

            # Convertir a datetime
            nueva_fecha_dt = datetime.combine(fecha_pase, datetime.min.time())

            # Actualizar en DF
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha_dt

            # Recalcular días restantes
            fecha_exp = row["Fecha de Expediente"]

            if fecha_exp:
                df.at[idx, "Días restantes"] = (nueva_fecha_dt - fecha_exp).days
            else:
                df.at[idx, "Días restantes"] = ""

            # ---------------------------
            # 6. ESCRIBIR EN GOOGLE SHEETS
            # ---------------------------
            valores = df.astype(str).values.tolist()
            worksheet.update(f"A2:{chr(64 + df.shape[1])}{df.shape[0] + 1}", valores)

            st.success(f"Expediente {row['Número de Expediente']} actualizado correctamente.")


