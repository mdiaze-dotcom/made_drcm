import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date

st.set_page_config(page_title="Actualización DRCM", layout="wide")

# ---------------------------------------------------------
# 1. Conexión a Google Sheets
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 2. Conversión de fechas
# ---------------------------------------------------------
def parse_fecha(fecha_str):
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

# ---------------------------------------------------------
# 3. Calcular días restantes globalmente
# ---------------------------------------------------------
def compute_days(fecha_exp, fecha_pase):
    if fecha_exp is None:
        return ""
    if fecha_pase is None:
        return (datetime.today() - fecha_exp).days
    return (fecha_pase - fecha_exp).days

df["Días restantes"] = df.apply(
    lambda row: compute_days(row["Fecha de Expediente"], row["Fecha Pase DRCM"]),
    axis=1
)

# ---------------------------------------------------------
# 4. Selección de dependencia y clave
# ---------------------------------------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede_seleccionada = st.sidebar.selectbox("Seleccione la dependencia", dependencias)

CLAVES = {
    "LIMA": "LIMA2025",
    "LIMA ESTE": "LIMAESTE2025",
    "CALLAO": "CALLAO2025",
    "AREQUIPA": "AREQUIPA2025",
    "CUSCO": "CUSCO2025",
    "CHICLAYO": "CHICLAYO2025",
    "PIURA": "PIURA2025",
    "TUMBES": "TUMBES2025",
    "TACNA": "TACNA2025",
    "PUCALLPA": "PUCALLPA2025",
    "TRUJILLO": "TRUJILLO2025",
    "ICA": "ICA2025"
}

if sede_seleccionada not in CLAVES:
    st.error(f"No existe clave para la sede: {sede_seleccionada}")
    st.stop()

clave_ingresada = st.sidebar.text_input("Ingrese su clave", type="password")

if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Clave incorrecta.")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------------------------------------
# 5. Filtrar expedientes pendientes
# ---------------------------------------------------------
df_filtrado = df[
    (df["Dependencia"].str.strip().str.upper() == sede_seleccionada.strip().upper()) &
    (df["Estado Trámite"].str.strip().str.upper() == "PENDIENTE")
]

if df_filtrado.empty:
    st.info("No existen expedientes pendientes en esta sede.")
    st.stop()

st.subheader("Expedientes Pendientes")

# ---------------------------------------------------------
# 6. Función para colorear días restantes en Google Sheets
# ---------------------------------------------------------
def aplicar_colores(worksheet, df):
    num_rows = len(df)
    start_row = 2          # A partir de la fila 2
    col_index = 4          # Columna D = 4 (1-based index)

    requests = []

    for i in range(num_rows):
        valor = df.iloc[i]["Días restantes"]

        # Determinar color
        if valor == "":
            color = {"red": 1, "green": 1, "blue": 1}  # blanco
        else:
            valor = int(valor)
            if valor >= 6:
                color = {"red": 1, "green": 0.2, "blue": 0.2}  # rojo
            elif 4 <= valor <= 5:
                color = {"red": 1, "green": 1, "blue": 0.2}    # amarillo
            else:
                color = {"red": 0.2, "green": 1, "blue": 0.2}  # verde

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": worksheet._properties["sheetId"],
                    "startRowIndex": start_row - 1 + i,
                    "endRowIndex": start_row + i,
                    "startColumnIndex": col_index - 1,
                    "endColumnIndex": col_index
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    worksheet.spreadsheet.batch_update({"requests": requests})

# ---------------------------------------------------------
# 7. Mostrar y actualizar expedientes
# ---------------------------------------------------------
for idx, row in df_filtrado.iterrows():

    with st.expander(f"Expediente {row['Número de Expediente']}"):

        # Default fecha segura
        default_fecha = (
            row["Fecha Pase DRCM"].date()
            if isinstance(row["Fecha Pase DRCM"], datetime)
            else date.today()
        )

        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=default_fecha,
            key=f"fecha_{idx}"
        )

        dias_nuevo = compute_days(
            row["Fecha de Expediente"],
            datetime.combine(fecha_pase, datetime.min.time())
        )

        st.write(f"Días restantes calculados: {dias_nuevo}")

        if st.button("Guardar", key=f"save_{idx}"):

            nueva_fecha = datetime.combine(fecha_pase, datetime.min.time())
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha
            df.at[idx, "Días restantes"] = dias_nuevo

            # Escribir dataframe
            df_to_write = df.astype(str)
            worksheet.update(
                f"A2:{chr(64 + df.shape[1])}{df.shape[0] + 1}",
                df_to_write.values.tolist()
            )

            # Aplicar colores
            aplicar_colores(worksheet, df)

            st.success(f"Expediente {row['Número de Expediente']} actualizado y coloreado correctamente.")

