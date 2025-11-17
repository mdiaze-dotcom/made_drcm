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
# 3. Funciones seguras para manejar fechas
# ---------------------------------------------------------
def parse_fecha(fecha_str):
    if fecha_str is None:
        return None
    if str(fecha_str).strip() == "":
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
# 4. Cálculo de días restantes (PARCHE)
# ---------------------------------------------------------
def compute_days(fecha_exp, fecha_pase):
    if fecha_exp is None:
        return ""
    # Si no hay fecha pase → usar hoy()
    if fecha_pase is None:
        return (datetime.today() - fecha_exp).days
    return (fecha_pase - fecha_exp).days

# Recalcular para TODOS los expedientes al iniciar
df["Días restantes"] = df.apply(
    lambda r: compute_days(r["Fecha de Expediente"], r["Fecha Pase DRCM"]),
    axis=1
)

# ---------------------------------------------------------
# 5. Selección de dependencia
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
    st.error(f"No existe clave configurada para {sede_seleccionada}")
    st.stop()

clave_ingresada = st.sidebar.text_input("Ingrese la clave", type="password")

if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Clave incorrecta.")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------------------------------------
# 6. Filtrar expedientes pendientes
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
# 7. Función segura para preparar valor para st.date_input
# ---------------------------------------------------------
def safe_default_date(fp):
    if fp is None:
        return date.today()

    try:
        if pd.isna(fp):
            return date.today()
    except:
        pass

    # pandas Timestamp
    if hasattr(fp, "to_pydatetime"):
        try:
            return fp.to_pydatetime().date()
        except:
            pass

    # datetime puro
    if isinstance(fp, datetime):
        return fp.date()

    # string → intentar parsear
    try:
        parsed = parse_fecha(fp)
        if parsed:
            return parsed.date()
    except:
        pass

    return date.today()

# ---------------------------------------------------------
# 8. Colores condicionales
# ---------------------------------------------------------
def aplicar_colores(worksheet, df_full):
    num_rows = df_full.shape[0]
    start_row = 2
    col_index = 4  # columna D

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

    if requests:
        worksheet.spreadsheet.batch_update({"requests": requests})

# ---------------------------------------------------------
# 9. Formateo antes de escribir
# ---------------------------------------------------------
def fmt(x):
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    if str(x).upper() in ("NONE", "NAT", ""):
        return ""

    if isinstance(x, datetime):
        return x.strftime("%d/%m/%Y %H:%M:%S")

    try:
        f = parse_fecha(x)
        if f:
            return f.strftime("%d/%m/%Y %H:%M:%S")
    except:
        pass

    return ""

def fmt_days(x):
    try:
        return int(float(str(x).replace(",", ".")))
    except:
        return ""

# ---------------------------------------------------------
# 10. Interfaz principal
# ---------------------------------------------------------
for idx, row in df_filtrado.iterrows():
    with st.expander(f"Expediente {row['Número de Expediente']}"):

        fp = row["Fecha Pase DRCM"]
        default_fecha = safe_default_date(fp)

        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=default_fecha,
            key=f"fp_{idx}"
        )

        nueva_fecha_dt = datetime.combine(fecha_pase, datetime.min.time())

        dias = compute_days(row["Fecha de Expediente"], nueva_fecha_dt)
        st.write(f"Días restantes: {dias}")

        if st.button("Guardar", key=f"save_{idx}"):

            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha_dt
            df.at[idx, "Días restantes"] = dias

            df_write = df.copy()
            df_write["Fecha de Expediente"] = df_write["Fecha de Expediente"].apply(fmt)
            df_write["Fecha Pase DRCM"] = df_write["Fecha Pase DRCM"].apply(fmt)
            df_write["Días restantes"] = df_write["Días restantes"].apply(fmt_days)

            header = worksheet.row_values(1)
            header = [c for c in header if c in df_write.columns]

            values = df_write[header].values.tolist()
            end_col = chr(64 + len(header))
            worksheet.update(f"A2:{end_col}{df_write.shape[0] + 1}", values)

            aplicar_colores(worksheet, df_write)

            st.success(f"Expediente {row['Número de Expediente']} actualizado correctamente.")



