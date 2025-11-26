import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time

st.set_page_config(page_title="Actualización DRCM", layout="wide")

# ---------------------------------------------------
# 1. GOOGLE SHEETS CONNECTION
# ---------------------------------------------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)

gc = gspread.authorize(credentials)

SHEET_ID = "1mDeXDyKTZjNmRK8TnSByKbm3ny_RFhT4Rvjpqwekvjg"
SHEET_NAME = "Hoja 1"

sh = gc.open_by_key(SHEET_ID)
worksheet = sh.worksheet(SHEET_NAME)

# ---------------------------------------------------
# 2. LEER DATOS
# ---------------------------------------------------
records = worksheet.get_all_records()
df = pd.DataFrame(records)

# ---------------------------------------------------
# 3. FUNCIONES BLINDADAS DE FECHA
# ---------------------------------------------------
def is_nat(x):
    if x is None:
        return True
    try:
        if pd.isna(x):
            return True
    except:
        pass
    s = str(x).strip().upper()
    return s in ("", "NONE", "NAN", "NAT")


def try_parse_fecha(x):
    if is_nat(x):
        return None
    if isinstance(x, datetime):
        return x
    if isinstance(x, pd.Timestamp):
        return x.to_pydatetime()
    s = str(x).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    try:
        return datetime.fromisoformat(s)
    except:
        return None


def fmt_fecha_sheet(x):
    x = try_parse_fecha(x)
    if x is None:
        return ""
    return x.strftime("%d/%m/%Y %H:%M:%S")


def fmt_days_sheet(x):
    if is_nat(x):
        return ""
    try:
        return str(int(float(x)))
    except:
        return ""


# ---------------------------------------------------
# 4. NORMALIZAR FECHAS
# ---------------------------------------------------
for col in ["Fecha de Expediente", "Fecha Pase DRCM",
            "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]:
    if col in df.columns:
        df[col] = df[col].apply(try_parse_fecha)

# ---------------------------------------------------
# 5. CALCULAR DÍAS TRANS­CURRIDOS (FUNCIÓN CORREGIDA)
# ---------------------------------------------------
def compute_days_safe(f_exp, f_pase):
    fexp = try_parse_fecha(f_exp)
    if fexp is None:
        return ""

    # Asegurar que siempre use solo fecha
    fexp = fexp.date()

    # Si no hay fecha pase → hoy
    if is_nat(f_pase):
        return (date.today() - fexp).days

    fp = try_parse_fecha(f_pase)
    if fp is None:
        return (date.today() - fexp).days

    # Convertir también a date
    fp = fp.date()

    # Diferencia final
    return (fp - fexp).days


df["Días restantes"] = df.apply(
    lambda r: compute_days_safe(r.get("Fecha de Expediente"),
                                r.get("Fecha Pase DRCM")),
    axis=1
)

# ---------------------------------------------------
# 6. GUARDAR AUTOMÁTICAMENTE LOS CÁLCULOS
# ---------------------------------------------------
df_write = df.copy()

for col in ["Fecha de Expediente", "Fecha Pase DRCM",
            "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]:
    if col in df_write.columns:
        df_write[col] = df_write[col].apply(fmt_fecha_sheet)

df_write["Días restantes"] = df_write["Días restantes"].apply(fmt_days_sheet)

header = worksheet.row_values(1)
header = [h for h in header if h in df_write.columns]

df_out = df_write[header].fillna("").astype(str)

end_col = chr(64 + len(header))
worksheet.update(
    f"A2:{end_col}{df_out.shape[0] + 1}",
    df_out.values.tolist(),
    value_input_option="USER_ENTERED"
)

# ---------------------------------------------------
# 7. APLICAR COLORES A COLUMNA D
# ---------------------------------------------------
def apply_colors(ws, dfc):
    sheet_id = ws._properties["sheetId"]
    requests = []
    col_idx = 3

    dias_list = dfc["Días restantes"].tolist()

    for i, v in enumerate(dias_list):
        if is_nat(v):
            color = {"red": 1, "green": 1, "blue": 1}
        else:
            v = int(v)
            if v >= 6:
                color = {"red": 1, "green": 0, "blue": 0}
            elif 4 <= v <= 5:
                color = {"red": 1, "green": 1, "blue": 0}
            else:
                color = {"red": 0, "green": 1, "blue": 0}

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": i + 1,
                    "endRowIndex": i + 2,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1
                },
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if requests:
        ws.spreadsheet.batch_update({"requests": requests})


apply_colors(worksheet, df_write)

# ---------------------------------------------------
# 8. SELECCIÓN DE DEPENDENCIA Y CLAVE
# ---------------------------------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede = st.sidebar.selectbox("Seleccione dependencia", dependencias)

CLAVES = {d: d.replace(" ", "").upper() + "2025" for d in dependencias}
clave = st.sidebar.text_input("Clave de acceso", type="password")

if clave != CLAVES.get(sede, ""):
    st.warning("Clave incorrecta.")
    st.stop()

# ---------------------------------------------------
# 9. FILTRO FINAL
# ---------------------------------------------------
def fecha_vacia(x):
    return is_nat(x)

df_pen = df[
    (df["Dependencia"].str.upper() == sede.upper()) &
    (df["Estado Trámite"].str.upper() == "PENDIENTE") &
    (df["Fecha Pase DRCM"].apply(fecha_vacia))
]

if df_pen.empty:
    st.info("No hay expedientes pendientes.")
    st.stop()

# ---------------------------------------------------
# 10. MOSTRAR Y ACTUALIZAR (CON TEXTO Y COLOR NUEVO)
# ---------------------------------------------------
st.subheader("Expedientes pendientes")

def safe_widget_date(x):
    dt = try_parse_fecha(x)
    return dt.date() if dt else date.today()

for idx, row in df_pen.iterrows():

    num = row.get("Número de Expediente", "")
    with st.expander(f"Expediente {num}"):

        # Mostrar fecha expediente
        fecha_exp_txt = ""
        fe = try_parse_fecha(row.get("Fecha de Expediente"))
        if fe:
            fecha_exp_txt = fe.strftime("%d/%m/%Y")
        st.write(f"📌 **Fecha de Expediente:** {fecha_exp_txt}")

        default_date = safe_widget_date(row.get("Fecha Pase DRCM"))

        fecha_pase = st.date_input(
            "Fecha Pase DRCM (no puede ser menor que hoy)",
            value=default_date,
            key=f"fp_{idx}"
        )

        if fecha_pase < date.today():
            st.error("❌ La fecha no puede ser menor que hoy.")
            continue

        dias_calc = compute_days_safe(
            row.get("Fecha de Expediente"),
            datetime.combine(fecha_pase, time.min)
        )

        # Determinar color
        if dias_calc == "" or dias_calc is None:
            color_hex = "#FFFFFF"
        else:
            try:
                v = int(dias_calc)
                if v >= 6:
                    color_hex = "#FF0000"
                elif 4 <= v <= 5:
                    color_hex = "#FFFF00"
                else:
                    color_hex = "#00FF00"
            except:
                color_hex = "#FFFFFF"

        # Mostrar con estilo
        st.markdown(
            f"""
            <div style="padding:8px; font-size:16px; 
                        background-color:{color_hex};
                        width: fit-content; 
                        border-radius:5px;">
                <strong>Días transcurridos desde la recepción del trámite:</strong> {dias_calc}
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Guardar", key=f"save_{idx}"):

            nueva = datetime.combine(fecha_pase, time.min)

            df.at[idx, "Fecha Pase DRCM"] = nueva
            df.at[idx, "Días restantes"] = compute_days_safe(
                row.get("Fecha de Expediente"), nueva
            )

            df2 = df.copy()

            for col in ["Fecha de Expediente", "Fecha Pase DRCM",
                        "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]:
                df2[col] = df2[col].apply(fmt_fecha_sheet)

            df2["Días restantes"] = df2["Días restantes"].apply(fmt_days_sheet)

            df_out2 = df2[header].fillna("").astype(str)

            worksheet.update(
                f"A2:{end_col}{df_out2.shape[0] + 1}",
                df_out2.values.tolist(),
                value_input_option="USER_ENTERED"
            )

            apply_colors(worksheet, df2)

            st.success("Expediente actualizado correctamente.")
