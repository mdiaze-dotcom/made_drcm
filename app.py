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
# 2. Cargar datos
# ---------------------------------------------------------
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# ---------------------------------------------------------
# 3. Funciones seguras de fecha
# ---------------------------------------------------------
def parse_fecha(x):
    if x is None or str(x).strip() == "":
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(x, fmt)
        except:
            pass
    return None


def fmt_datetime_for_sheet(x):
    """Nunca lanza error. Devuelve fecha formateada o ''."""
    if isinstance(x, datetime):
        return x.strftime("%d/%m/%Y %H:%M:%S")

    if x is None:
        return ""

    try:
        if pd.isna(x):
            return ""
    except:
        pass

    if str(x).strip().upper() in ("", "NONE", "NAN", "NAT"):
        return ""

    return ""


def fmt_days_for_sheet(x):
    try:
        return str(int(float(x)))
    except:
        return ""


# ---------------------------------------------------------
# 4. Convertir fechas originales
# ---------------------------------------------------------
df["Fecha de Expediente"] = df["Fecha de Expediente"].apply(parse_fecha)
df["Fecha Pase DRCM"] = df["Fecha Pase DRCM"].apply(parse_fecha)

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
# 6. Guardar automáticamente días recalculados
# ---------------------------------------------------------
df_auto = df.copy()

df_auto["Fecha de Expediente"] = df_auto["Fecha de Expediente"].apply(fmt_datetime_for_sheet)
df_auto["Fecha Pase DRCM"] = df_auto["Fecha Pase DRCM"].apply(fmt_datetime_for_sheet)
df_auto["Días restantes"] = df_auto["Días restantes"].apply(fmt_days_for_sheet)

header = worksheet.row_values(1)
header = [c for c in header if c in df_auto.columns]

values_df = df_auto[header].fillna("").astype(str)
values = values_df.values.tolist()

end_col = chr(64 + len(header))
worksheet.update(
    f"A2:{end_col}{df_auto.shape[0] + 1}",
    values,
    value_input_option='USER_ENTERED'
)

# ---------------------------------------------------------
# 7. Aplicar colores a la columna D
# ---------------------------------------------------------
def aplicar_colores(ws, df):
    rows = df.shape[0]
    days = df["Días restantes"].tolist()

    requests = []
    for i, valor in enumerate(days):
        fila = i + 2
        try:
            valor = int(valor)
        except:
            continue

        if valor >= 6:
            color = {"red": 1, "green": 0, "blue": 0}
        elif 4 <= valor <= 5:
            color = {"red": 1, "green": 1, "blue": 0}
        else:
            color = {"red": 0, "green": 1, "blue": 0}

        requests.append({
            "updateCells": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": fila - 1,
                    "endRowIndex": fila,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4
                },
                "rows": [{
                    "values": [{
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    }]
                }],
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if requests:
        sh.batch_update({"requests": requests})

aplicar_colores(worksheet, df_auto)

# ---------------------------------------------------------
# 8. Selección de dependencia y clave
# ---------------------------------------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede_seleccionada = st.sidebar.selectbox("Seleccione Dependencia", dependencias)

clave_ingresada = st.sidebar.text_input("Ingrese clave de acceso", type="password")

CLAVES = {
    d: d.replace(" ", "").upper() + "2025"
    for d in dependencias
}

if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Clave incorrecta.")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------------------------------------
# 9. Filtrar pendientes de la sede
# ---------------------------------------------------------
df_filtrado = df[
    (df["Dependencia"].str.upper() == sede_seleccionada.upper()) &
    (df["Estado Trámite"].str.upper() == "PENDIENTE")
]

if df_filtrado.empty:
    st.info("No existen pendientes.")
    st.stop()

# ---------------------------------------------------------
# 10. Mostrar y actualizar individualmente
# ---------------------------------------------------------
st.subheader("Expedientes pendientes")

for idx, row in df_filtrado.iterrows():

    with st.expander(f"Expediente {row['Número de Expediente']}"):

        default_fecha = (
            row["Fecha Pase DRCM"].date()
            if isinstance(row["Fecha Pase DRCM"], datetime)
            else date.today()
        )

        fecha_pase = st.date_input(
            "Fecha Pase DRCM",
            value=default_fecha,
            key=f"fp_{idx}"
        )

        if st.button("Guardar", key=f"save_{idx}"):

            nueva_fecha_dt = datetime.combine(fecha_pase, datetime.min.time())
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha_dt

            fecha_exp = row["Fecha de Expediente"]
            df.at[idx, "Días restantes"] = compute_days(fecha_exp, nueva_fecha_dt)

            df_write = df.copy()
            df_write["Fecha de Expediente"] = df_write["Fecha de Expediente"].apply(fmt_datetime_for_sheet)
            df_write["Fecha Pase DRCM"] = df_write["Fecha Pase DRCM"].apply(fmt_datetime_for_sheet)
            df_write["Días restantes"] = df_write["Días restantes"].apply(fmt_days_for_sheet)

            values_df2 = df_write[header].fillna("").astype(str)
            values2 = values_df2.values.tolist()

            worksheet.update(
                f"A2:{end_col}{df_write.shape[0] + 1}",
                values2,
                value_input_option='USER_ENTERED'
            )

            aplicar_colores(worksheet, df_write)

            st.success(f"Expediente {row['Número de Expediente']} actualizado.")



