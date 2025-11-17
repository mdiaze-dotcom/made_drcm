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

# ---------------------------------------------------
# 2. Conversión robusta de fechas
# ---------------------------------------------------
def parse_fecha(fecha_str):
    """Convierte texto a datetime manejando días/meses correctamente."""
    if not fecha_str or str(fecha_str).strip() == "":
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(fecha_str), fmt)
        except:
            pass
    return None

df["Fecha de Expediente"] = df["Fecha de Expediente"].apply(parse_fecha)
df["Fecha Pase DRCM"] = df["Fecha Pase DRCM"].apply(parse_fecha)

# ---------------------------------------------------
# 3. Selección de dependencia y clave
# ---------------------------------------------------
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

# ---------------------------------------------------
# 4. Filtrar expedientes pendientes
# ---------------------------------------------------
df_filtrado = df[
    (df["Dependencia"].str.strip().str.upper() == sede_seleccionada.strip().upper()) &
    (df["Estado Trámite"].str.strip().str.upper() == "PENDIENTE")
]

if df_filtrado.empty:
    st.info("No existen expedientes pendientes para esta dependencia.")
    st.stop()

# ---------------------------------------------------
# Función: calcular días restantes
# ---------------------------------------------------
def compute_days(fecha_exp, fecha_pase):
    if fecha_exp is None:
        return ""
    if fecha_pase is None:
        return (datetime.today() - fecha_exp).days
    return (fecha_pase - fecha_exp).days

# ---------------------------------------------------
# 5. Mostrar y actualizar expedientes
# ---------------------------------------------------
st.subheader("Expedientes Pendientes")

for idx, row in df_filtrado.iterrows():
    with st.expander(f"Expediente {row['Número de Expediente']}"):

        # Manejo seguro de fechas vacías
        if isinstance(row["Fecha Pase DRCM"], datetime):
            default_fecha_pase = row["Fecha Pase DRCM"].date()
        else:
            default_fecha_pase = date.today()

        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=default_fecha_pase,
            key=f"fecha_{idx}"
        )

        # Calcular días restantes (vista previa)
        dias_prev = compute_days(row["Fecha de Expediente"], 
                                 datetime.combine(fecha_pase, datetime.min.time()))
        st.write(f"Días restantes calculados: {dias_prev}")

        if st.button("Guardar", key=f"guardar_{idx}"):

            nueva_fecha_dt = datetime.combine(fecha_pase, datetime.min.time())

            # Actualizar dataframe
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha_dt
            df.at[idx, "Días restantes"] = compute_days(row["Fecha de Expediente"], nueva_fecha_dt)

            # Convertir para escritura
            df_to_write = df.astype(str)

            worksheet.update(
                f"A2:{chr(64 + df.shape[1])}{df.shape[0] + 1}",
                df_to_write.values.tolist()
            )

            st.success(f"Expediente {row['Número de Expediente']} actualizado correctamente.")
