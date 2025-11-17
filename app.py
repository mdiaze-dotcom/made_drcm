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

# ---------------------------------------------------------
# 2. Leer datos
# ---------------------------------------------------------
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# ---------------------------------------------------------
# 3. Funciones para parsear fechas
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
# 4. NORMALIZAR TODAS LAS FECHAS PARA QUE NO HAYA NaT
# ---------------------------------------------------------
def clean_dt(x):
    if isinstance(x, datetime):
        return x
    return None

df["Fecha de Expediente"] = df["Fecha de Expediente"].apply(clean_dt)
df["Fecha Pase DRCM"] = df["Fecha Pase DRCM"].apply(clean_dt)

# ---------------------------------------------------------
# 5. Calcular días restantes
# ---------------------------------------------------------
def compute_days(fecha_exp, fecha_pase):
    if fecha_exp is None:
        return ""
    if fecha_pase is None:
        return (datetime.today() - fecha_exp).days
    return (fecha_pase - fecha_exp).days

df["Días restantes"] = df.apply(
    lambda r: compute_days(r["Fecha de Expediente"], r["Fecha Pase DRCM"]),
    axis=1
)

# ---------------------------------------------------------
# 6. Selección de dependencia + claves
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
    "PUNO": "PUNO2025",
    "TUMBES": "TUMBES2025",
    "TACNA": "TACNA2025",
    "PUCALLPA": "PUCALLPA2025",
    "TRUJILLO": "TRUJILLO2025",
    "ICA": "ICA2025"
}

if sede_seleccionada not in CLAVES:
    st.error(f"No existe clave configurada para: {sede_seleccionada}")
    st.stop()

clave_ingresada = st.sidebar.text_input("Ingrese la clave", type="password")

if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Clave incorrecta")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------------------------------------
# 7. Filtrar pendientes
# ---------------------------------------------------------
df_filtrado = df[
    (df["Dependencia"].str.upper().str.strip() == sede_seleccionada.upper().strip()) &
    (df["Estado Trámite"].str.upper().str.strip() == "PENDIENTE")
]

if df_filtrado.empty:
    st.info("No existen expedientes pendientes.")
    st.stop()

st.subheader("Expedientes pendientes")

# ---------------------------------------------------------
# 8. Colorear en Google Sheets
# ---------------------------------------------------------
def aplicar_colores(worksheet, df_full):
    num_rows = df_full.shape[0]
    start_row = 2
    col_index = 4

    sheet_id = worksheet._properties.get("sheetId")
    requests = []

    for i in range(num_rows):
        raw = df_full.iloc[i]["Días restantes"]

        try:
            val = int(float(str(raw).replace(",", ".")))
        except:
            color = {"red": 1, "green": 1, "blue": 1}
        else:
            if val >= 6:
                color = {"red": 1, "green": 0.2, "blue": 0.2}
            elif 4 <= val <= 5:
                color = {"red": 1, "green": 1, "blue": 0.2}
            else:
                color = {"red": 0.2, "green": 1, "blue": 0.2}

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1 + i,
                    "endRowIndex": start_row + i,
                    "startColumnIndex": col_index - 1,
                    "endColumnIndex": col_index
                },
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    worksheet.spreadsheet.batch_update({"requests": requests})

# ---------------------------------------------------------
# 9. Formateo de escritura
# ---------------------------------------------------------
def fmt(x):
    if x is None:
        return ""
    if isinstance(x, datetime):
        return x.strftime("%d/%m/%Y %H:%M:%S")
    d = parse_fecha(x)
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else ""

def fmt_days(x):
    try:
        return int(float(str(x).replace(",", ".")))
    except:
        return ""

# ---------------------------------------------------------
# 10. INTERFAZ PRINCIPAL
# ---------------------------------------------------------
for idx, row in df_filtrado.iterrows():
    with st.expander(f"Expediente {row['Número de Expediente']}"):

        # Fecha Exp seguras
        fecha_exp = row["Fecha de Expediente"]

        # Fecha Pase DRCM seguras
        fp = row["Fecha Pase DRCM"]
        if isinstance(fp, datetime):
            default_fecha = fp.date()
        else:
            default_fecha = date.today()

        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=default_fecha,
            key=f"fp_{idx}"
        )

        dias_prev = compute_days(fecha_exp, datetime.combine(fecha_pase, datetime.min.time()))
        st.write(f"Días restantes: {dias_prev}")

        if st.button("Guardar", key=f"save_{idx}"):

            nueva_fecha = datetime.combine(fecha_pase, datetime.min.time())
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha
            df.at[idx, "Días restantes"] = dias_prev

            df_write = df.copy()

            df_write["Fecha de Expediente"] = df_write["Fecha de Expediente"].apply(fmt)
            df_write["Fecha Pase DRCM"] = df_write["Fecha Pase DRCM"].apply(fmt)
            df_write["Días restantes"] = df_write["Días restantes"].apply(fmt_days)

            header = worksheet.row_values(1)
            header = [c for c in header if c in df_write.columns]

            values = df_write[header].values.tolist()
            end_col = chr(64 + len(header))
            rango = f"A2:{end_col}{df_write.shape[0] + 1}"

            worksheet.update(rango, values, value_input_option="USER_ENTERED")

            new_data = worksheet.get_all_records()
            df = pd.DataFrame(new_data)

            df["Fecha de Expediente"] = df["Fecha de Expediente"].apply(parse_fecha)
            df["Fecha Pase DRCM"] = df["Fecha Pase DRCM"].apply(parse_fecha)
            df["Días restantes"] = df.apply(
                lambda r: compute_days(r["Fecha de Expediente"], r["Fecha Pase DRCM"]),
                axis=1
            )

            aplicar_colores(worksheet, df)

            st.success(f"Expediente {row['Número de Expediente']} actualizado correctamente.")
