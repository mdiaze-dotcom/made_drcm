import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time

st.set_page_config(page_title="Actualización DRCM", layout="wide")

# ----------------------------
# Config Google Sheets
# ----------------------------
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
gc = gspread.authorize(credentials)

SHEET_ID = "1mDeXDyKTZjNmRK8TnSByKbm3ny_RFhT4Rvjpqwekvjg"
SHEET_NAME = "Hoja 1"

sh = gc.open_by_key(SHEET_ID)
worksheet = sh.worksheet(SHEET_NAME)

# ----------------------------
# Leer datos
# ----------------------------
records = worksheet.get_all_records()
df = pd.DataFrame(records)

# ----------------------------
# Utilidades de fecha (robustas)
# ----------------------------
def try_parse_fecha(x):
    """Intenta convertir x a datetime o devuelve None. Acepta datetime, pandas.Timestamp, o strings dd/mm/YYYY[ HH:MM:SS]."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except:
        pass
    if isinstance(x, datetime):
        return x
    # pandas Timestamp
    try:
        import pandas as _pd
        if isinstance(x, _pd.Timestamp):
            return x.to_pydatetime()
    except:
        pass
    s = str(x).strip()
    if s == "" or s.upper() in ("NONE", "NAT", "NAN"):
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    # if it's ISO-like try parse
    try:
        return datetime.fromisoformat(s)
    except:
        return None

def fmt_fecha_sheet(x):
    """Formatea datetime a dd/mm/YYYY HH:MM:SS o devuelve ''."""
    if isinstance(x, datetime):
        return x.strftime("%d/%m/%Y %H:%M:%S")
    try:
        if pd.isna(x):
            return ""
    except:
        pass
    return ""

def fmt_days_sheet(x):
    """Devuelve string entero o ''."""
    try:
        if x is None or str(x).strip() == "":
            return ""
        return str(int(float(x)))
    except:
        return ""

# ----------------------------
# Normalizar columnas de fecha (si existen)
# ----------------------------
cols_fecha = ["Fecha de Expediente", "Fecha Pase DRCM", "Fecha Inicio de Etapa", "Fecha Fin de Etapa"]
for c in cols_fecha:
    if c in df.columns:
        df[c] = df[c].apply(try_parse_fecha)

# ----------------------------
# Cálculo seguro de días restantes
# ----------------------------
def compute_days_safe(fecha_exp, fecha_pase):
    """
    - Si fecha_exp no es válida => return ''
    - Si fecha_pase es None => diferencia entre hoy y fecha_exp (en días)
    - Si ambos válidos => fecha_pase - fecha_exp
    """
    fe = try_parse_fecha(fecha_exp)
    fp = try_parse_fecha(fecha_pase)
    if fe is None:
        return ""
    if fp is None:
        delta = datetime.combine(date.today(), time.min) - fe
    else:
        delta = fp - fe
    try:
        return int(delta.days)
    except:
        return ""

# recalcular siempre en memoria
df["Días restantes"] = df.apply(lambda r: compute_days_safe(r.get("Fecha de Expediente"), r.get("Fecha Pase DRCM")), axis=1)

# ----------------------------
# Escribir AUTOMÁTICAMENTE los días calculados (y formatear fechas) al Sheet
# ----------------------------
# Preparar df para escritura: forzar strings y formatos que Sheets interprete
df_write = df.copy()
for c in cols_fecha:
    if c in df_write.columns:
        df_write[c] = df_write[c].apply(fmt_fecha_sheet)
if "Días restantes" in df_write.columns:
    df_write["Días restantes"] = df_write["Días restantes"].apply(fmt_days_sheet)

# Respetar encabezado real
header = worksheet.row_values(1)
header_use = [h for h in header if h in df_write.columns]

values_df = df_write[header_use].fillna("").astype(str)
values = values_df.values.tolist()

# calcular columna final (<=26 columnas asumido)
end_col = chr(64 + len(header_use))
range_a2 = f"A2:{end_col}{df_write.shape[0] + 1}"

worksheet.update(range_a2, values, value_input_option="USER_ENTERED")

# ----------------------------
# Colorear columna D (Días restantes) con batch_update
# ----------------------------
def apply_colors(worksheet, df_colored):
    # sheetId
    sheet_id = worksheet._properties.get("sheetId")
    requests = []
    start_row_index = 1  # row 2 -> index 1
    # column D is index 3 (0-based)
    col_idx = 3
    for i, val in enumerate(df_colored["Días restantes"].fillna("").tolist()):
        if val == "":
            # make white (or skip)
            color = {"red": 1.0, "green": 1.0, "blue": 1.0}
        else:
            try:
                v = int(float(str(val)))
            except:
                color = {"red": 1.0, "green": 1.0, "blue": 1.0}
            else:
                if v >= 6:
                    color = {"red": 1.0, "green": 0.2, "blue": 0.2}
                elif 4 <= v <= 5:
                    color = {"red": 1.0, "green": 1.0, "blue": 0.2}
                else:
                    color = {"red": 0.2, "green": 1.0, "blue": 0.2}
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row_index + i,
                    "endRowIndex": start_row_index + i + 1,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1
                },
                "cell": {"userEnteredFormat": {"backgroundColor": color}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })
    if requests:
        worksheet.spreadsheet.batch_update({"requests": requests})

apply_colors(worksheet, df_write)

# ----------------------------
# Sidebar: seleccionar dependencia
# ----------------------------
dependencias = sorted(df["Dependencia"].dropna().unique()) if "Dependencia" in df.columns else []
sede = st.sidebar.selectbox("Seleccione Dependencia", dependencias)

# Generar claves dinámicas (puedes personalizar)
CLAVES = {dep: dep.replace(" ", "").upper() + "2025" for dep in dependencias}

clave = st.sidebar.text_input("Clave", type="password")
if clave != CLAVES.get(sede):
    st.warning("Clave incorrecta o no ingresada.")
    st.stop()

st.success(f"Acceso autorizado: {sede}")

# ----------------------------
# Filtrar pendientes
# ----------------------------
if "Estado Trámite" not in df.columns:
    st.error("La columna 'Estado Trámite' no está en la hoja.")
    st.stop()

df_pending = df[
    (df["Dependencia"].str.strip().str.upper() == sede.strip().upper()) &
    (df["Estado Trámite"].str.strip().str.upper() == "PENDIENTE")
].copy()

if df_pending.empty:
    st.info("No hay expedientes pendientes para esta dependencia.")
    st.stop()

st.subheader("Expedientes pendientes")

# ----------------------------
# helper para safe default date para widget
# ----------------------------
def safe_default_date(fp):
    p = try_parse_fecha(fp)
    if p is None:
        return date.today()
    return p.date()

# ----------------------------
# Mostrar y permitir actualizar cada expediente
# ----------------------------
for idx, row in df_pending.iterrows():
    with st.expander(f"Expediente {row.get('Número de Expediente', '')}"):
        fp = row.get("Fecha Pase DRCM", None)
        default_d = safe_default_date(fp)
        fecha_pase = st.date_input("Fecha Pase DRCM", value=default_d, key=f"fp_{idx}")

        # mostrar días calculados (vista)
        dias_calc = compute_days_safe(row.get("Fecha de Expediente"), datetime.combine(fecha_pase, time.min))
        st.write(f"Días restantes calculados: {dias_calc}")

        if st.button("Guardar", key=f"guardar_{idx}"):
            # actualizamos df global (cuidado: idx se refiere al index del df original)
            nueva_dt = datetime.combine(fecha_pase, time.min)
            df.at[idx, "Fecha Pase DRCM"] = nueva_dt
            df.at[idx, "Días restantes"] = compute_days_safe(df.at[idx, "Fecha de Expediente"], nueva_dt)

            # preparar df para escritura (formateo)
            df_write2 = df.copy()
            for c in cols_fecha:
                if c in df_write2.columns:
                    df_write2[c] = df_write2[c].apply(fmt_fecha_sheet)
            df_write2["Días restantes"] = df_write2["Días restantes"].apply(fmt_days_sheet)

            values_df2 = df_write2[header_use].fillna("").astype(str)
            values2 = values_df2.values.tolist()
            worksheet.update(range_a2, values2, value_input_option="USER_ENTERED")

            # aplicar colores de nuevo usando df_write2
            apply_colors(worksheet, df_write2)

            st.success("Expediente actualizado correctamente.")




