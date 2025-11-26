import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time, timedelta

st.set_page_config(page_title="Actualización DGTFM", layout="wide")

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
for col in ["Fecha de Expediente", "Fecha Pase DGTFM",
            "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]:
    if col in df.columns:
        df[col] = df[col].apply(try_parse_fecha)

# ---------------------------------------------------
# 5. CALCULAR DÍAS HÁBILES
# ---------------------------------------------------
def compute_business_days(start_date, end_date):
    if start_date is None:
        return ""

    start_date = start_date.date()
    end_date = end_date.date()

    delta = (end_date - start_date).days
    if delta < 0:
        return 0

    count = 0
    for i in range(delta + 1):
        d = start_date + timedelta(days=i)
        if d.weekday() < 5:  # 0=lunes, 6=domingo
            count += 1
    return count - 1  # no contar el día inicial


def compute_days_safe(f_exp, f_pase):
    fe = try_parse_fecha(f_exp)
    if fe is None:
        return ""
    fp = try_parse_fecha(f_pase)
    if fp is None:
        fp = datetime.combine(date.today(), time.min)
    return compute_business_days(fe, fp)

df["Días restantes"] = df.apply(
    lambda r: compute_days_safe(
        r.get("Fecha de Expediente"),
        r.get("Fecha Pase DGTFM")
    ),
    axis=1
)

# ---------------------------------------------------
# 6. GUARDAR AUTOMÁTICAMENTE LOS CÁLCULOS
# ---------------------------------------------------
df_write = df.copy()

for col in ["Fecha de Expediente", "Fecha Pase DGTFM",
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
    col_idx = 3  # D

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
# TOOLTIP / MODAL
# ---------------------------------------------------
with st.sidebar.expander("ℹ️ ¿Cómo se cuentan los días hábiles?"):
    st.markdown("""
    **Regla aplicada:**
    
    - Solo se contabilizan **días hábiles (lunes a viernes)**  
    - No se cuentan sábados  
    - No se cuentan domingos  
    - No se consideran feriados  
    - El cálculo es solo por fecha (**dd/mm/yyyy**)  
    """)

# ---------------------------------------------------
# 9. FILTRO FINAL
# ---------------------------------------------------
def fecha_vacia(x):
    return is_nat(x)

df_pen = df[
    (df["Dependencia"].str.upper() == sede.upper()) &
    (df["Estado Trámite"].str.upper() == "PENDIENTE") &
    (df["Fecha Pase DGTFM"].apply(fecha_vacia))
]

# ---------------------------------------------------
# 10. LEYENDA Y TOTALES
# ---------------------------------------------------
st.sidebar.markdown("### 🟩 Leyenda de colores")
st.sidebar.markdown("""
- 🟥 **Rojo:** 6 días o más  
- 🟨 **Amarillo:** 4 a 5 días  
- 🟩 **Verde:** 0 a 3 días  
""")

if not df_pen.empty:
    c_rojo = sum(df_pen["Días restantes"] >= 6)
    c_amar = sum((df_pen["Días restantes"] >= 4) & (df_pen["Días restantes"] <= 5))
    c_verde = sum(df_pen["Días restantes"] <= 3)

    st.sidebar.markdown("### 📊 Totales por color")
    st.sidebar.write(f"🟥 Rojo: **{c_rojo}**")
    st.sidebar.write(f"🟨 Amarillo: **{c_amar}**")
    st.sidebar.write(f"🟩 Verde: **{c_verde}**")

if df_pen.empty:
    st.info("No hay expedientes pendientes.")
    st.stop()

# ---------------------------------------------------
# 11. MOSTRAR Y ACTUALIZAR
# ---------------------------------------------------
st.subheader("Expedientes pendientes")

def safe_widget_date(x):
    x = try_parse_fecha(x)
    return x.date() if x else date.today()

for idx, row in df_pen.iterrows():
    num = row.get("Número de Expediente", "")
    with st.expander(f"Expediente {num}"):

        default_date = safe_widget_date(row.get("Fecha Pase DGTFM"))

        fecha_pase = st.date_input(
            "Fecha Pase DGTFM",
            value=default_date,
            key=f"fp_{idx}"
        )

        dias_calc = compute_days_safe(
            row.get("Fecha de Expediente"),
            datetime.combine(fecha_pase, time.min)
        )

        st.write(f"**Días transcurridos desde recepción:** {dias_calc}")

        if st.button("Guardar", key=f"save_{idx}"):

            nueva = datetime.combine(fecha_pase, time.min)
            df.at[idx, "Fecha Pase DGTFM"] = nueva
            df.at[idx, "Días restantes"] = compute_days_safe(
                row.get("Fecha de Expediente"), nueva
            )

            df2 = df.copy()

            for col in ["Fecha de Expediente", "Fecha Pase DGTFM",
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
