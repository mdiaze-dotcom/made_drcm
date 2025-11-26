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
    try:
        return str(int(x))
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
# 5. CÁLCULO DE DÍAS HÁBILES
# ---------------------------------------------------
def compute_business_days(start_date, end_date):
    """Cuenta días hábiles (lunes–viernes)."""
    if start_date is None:
        return ""

    start = start_date.date()
    end = end_date.date() if end_date else date.today()

    if end < start:
        return ""

    total = 0
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Lunes ... 4=Viernes
            total += 1
        current += timedelta(days=1)

    return total - 1  # no contar el día inicial

def compute_days_safe(f_exp, f_pase):
    fexp = try_parse_fecha(f_exp)
    fp = try_parse_fecha(f_pase)
    return compute_business_days(fexp, fp)

# Cálculo inicial
df["Días restantes"] = df.apply(
    lambda r: compute_days_safe(
        r.get("Fecha de Expediente"),
        r.get("Fecha Pase DGTFM")
    ),
    axis=1
)

# ---------------------------------------------------
# 6. GUARDADO AUTOMÁTICO A GOOGLE SHEETS
# ---------------------------------------------------
df_write = df.copy()

for col in ["Fecha de Expediente", "Fecha Pase DGTFM",
            "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]:
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
# 7. COLORES EN GOOGLE SHEETS
# ---------------------------------------------------
def apply_colors(ws, dfc):
    sheet_id = ws._properties["sheetId"]
    requests = []
    col_idx = 3  # D = columna 4

    for i, v in enumerate(dfc["Días restantes"]):
        try:
            v = int(v)
        except:
            color = {"red": 1, "green": 1, "blue": 1}
        else:
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
# 8. ACCESO POR DEPENDENCIA
# ---------------------------------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede = st.sidebar.selectbox("Seleccione dependencia", dependencias)

CLAVES = {d: d.replace(" ", "").upper() + "2025" for d in dependencias}
clave = st.sidebar.text_input("Clave de acceso", type="password")

if clave != CLAVES.get(sede, ""):
    st.warning("Clave incorrecta.")
    st.stop()

# ---------------------------------------------------
# 9. TOOLTIP — DÍAS HÁBILES
# ---------------------------------------------------
with st.sidebar.expander("ℹ️ ¿Cómo se cuentan los días hábiles?"):
    st.markdown("""
    **Regla aplicada:**
    - Solo se cuentan los **días lunes a viernes**
    - No se consideran sábados
    - No se consideran domingos
    - No se consideran feriados
    - Cálculo estrictamente por fecha (dd/mm/yyyy)
    """)

# ---------------------------------------------------
# 10. FILTRO FINAL
# ---------------------------------------------------
df_pen = df[
    (df["Dependencia"].str.upper() == sede.upper()) &
    (df["Estado Trámite"].str.upper() == "PENDIENTE") &
    (df["Fecha Pase DGTFM"].apply(is_nat))
]

df_pen["Días restantes"] = df_pen.apply(
    lambda r: compute_days_safe(
        r.get("Fecha de Expediente"),
        r.get("Fecha Pase DGTFM")
    ),
    axis=1
)

# ---------------------------------------------------
# 11. LEYENDA + TOTALES
# ---------------------------------------------------
st.sidebar.markdown("### 🟦 Leyenda de colores")

c_rojo = sum(df_pen["Días restantes"] >= 6)
c_amar = sum((df_pen["Días restantes"] >= 4) & (df_pen["Días restantes"] <= 5))
c_verde = sum(df_pen["Días restantes"] < 4)

st.sidebar.markdown(f"🟥 **≥ 6 días**: {c_rojo}")
st.sidebar.markdown(f"🟨 **4–5 días**: {c_amar}")
st.sidebar.markdown(f"🟩 **< 4 días**: {c_verde}")

# ---------------------------------------------------
# 12. CSS PARA COLOREAR EXPANDERS
# ---------------------------------------------------
st.markdown("""
<style>
.exp-rojo {
    background-color: rgba(255, 80, 80, 0.30);
    padding: 10px;
    border-radius: 8px;
}
.exp-amarillo {
    background-color: rgba(255, 255, 120, 0.40);
    padding: 10px;
    border-radius: 8px;
}
.exp-verde {
    background-color: rgba(120, 255, 120, 0.35);
    padding: 10px;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# 13. MOSTRAR Y ACTUALIZAR
# ---------------------------------------------------
st.subheader("Expedientes pendientes")

def safe_widget_date(x):
    x = try_parse_fecha(x)
    return x.date() if x else date.today()

for idx, row in df_pen.iterrows():

    num = row.get("Número de Expediente", "")
    dias_val = compute_days_safe(
        row.get("Fecha de Expediente"),
        row.get("Fecha Pase DGTFM")
    )

    if dias_val == "" or dias_val is None:
        css_class = "exp-verde"
    elif dias_val >= 6:
        css_class = "exp-rojo"
    elif 4 <= dias_val <= 5:
        css_class = "exp-amarillo"
    else:
        css_class = "exp-verde"

    with st.expander(f"Expediente {num}"):

        st.markdown(f"<div class='{css_class}'>", unsafe_allow_html=True)

        fexp = row.get("Fecha de Expediente")
        st.write("**Fecha de expediente:** ",
                 fexp.strftime("%d/%m/%Y") if fexp else "---")

        default_date = safe_widget_date(row.get("Fecha Pase DGTFM"))

        fecha_pase = st.date_input(
            "Fecha Pase DGTFM",
            value=default_date,
            key=f"fp_{idx}"
        )

        # Mostrar días transcurridos
        st.write(f"**Días transcurridos (hábiles):** {dias_val}")

        # GUARDAR
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

        st.markdown("</div>", unsafe_allow_html=True)

