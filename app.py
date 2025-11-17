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
# 3. Calcular días restantes globalmente (para todas las filas)
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
# 4. Selección de dependencia y claves (editable)
# ---------------------------------------------------------
dependencias = sorted(df["Dependencia"].dropna().unique())
sede_seleccionada = st.sidebar.selectbox("Seleccione la dependencia", dependencias)

# Diccionario de claves editable
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
    st.error(f"No existe clave para la sede: {sede_seleccionada}")
    st.stop()

clave_ingresada = st.sidebar.text_input("Ingrese su clave", type="password")
if clave_ingresada != CLAVES[sede_seleccionada]:
    st.warning("Clave incorrecta.")
    st.stop()

st.success(f"Acceso autorizado para {sede_seleccionada}")

# ---------------------------------------------------------
# 5. Filtrar expedientes pendientes para la sede
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
def aplicar_colores(worksheet, df_full):
    """
    Aplica color por valor en la columna 'Días restantes' (columna D).
    - >=6 rojo
    - 4-5 amarillo
    - <=3 verde
    Ignora valores no numéricos.
    """
    num_rows = df_full.shape[0]  # número de filas en el DataFrame que escribimos
    start_row = 2  # datos empiezan en la fila 2 (A2)
    col_index = 4  # columna D -> índice 4 (1-based)

    requests = []
    sheet_id = worksheet._properties.get("sheetId")

    for i in range(num_rows):
        raw_val = df_full.iloc[i].get("Días restantes", "")
        # convertir a entero de forma segura
        try:
            # Manejar strings numéricos con decimales también
            if raw_val is None or str(raw_val).strip() == "":
                raise ValueError("empty")
            val = int(float(str(raw_val).replace(",", ".")))
        except Exception:
            # no es numérico: pintar blanco/transparente (saltear)
            color = {"red": 1.0, "green": 1.0, "blue": 1.0}
        else:
            if val >= 6:
                color = {"red": 1.0, "green": 0.2, "blue": 0.2}   # rojo
            elif 4 <= val <= 5:
                color = {"red": 1.0, "green": 1.0, "blue": 0.2}   # amarillo
            else:
                color = {"red": 0.2, "green": 1.0, "blue": 0.2}   # verde

        # startRowIndex is 0-based and inclusive, endRowIndex exclusive
        start_r = start_row - 1 + i
        end_r = start_r + 1
        start_c = col_index - 1
        end_c = col_index

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_r,
                    "endRowIndex": end_r,
                    "startColumnIndex": start_c,
                    "endColumnIndex": end_c
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if requests:
        try:
            worksheet.spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            # Mostrar el error en Streamlit para diagnóstico
            st.error("Error aplicando colores en Google Sheets.")
            st.exception(e)

# ---------------------------------------------------------
# 7. Mostrar y actualizar expedientes (interfaz principal)
# ---------------------------------------------------------
# Nota: escribimos el df completo en el sheet cuando guardamos, así la correspondencia fila<->index se mantiene
for idx, row in df_filtrado.iterrows():
    with st.expander(f"Expediente {row['Número de Expediente']}"):
        # selector de fecha con manejo seguro de NaT
        if isinstance(row["Fecha Pase DRCM"], datetime):
            default_fecha = row["Fecha Pase DRCM"].date()
        else:
            default_fecha = date.today()

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
            # actualizar valores en el DataFrame global (df)
            nueva_fecha = datetime.combine(fecha_pase, datetime.min.time())
            df.at[idx, "Fecha Pase DRCM"] = nueva_fecha
            df.at[idx, "Días restantes"] = dias_nuevo

            # escribir todo el dataframe al sheet (A2:...)
            df_to_write = df.astype(str)
            try:
                worksheet.update(
                    f"A2:{chr(64 + df.shape[1])}{df.shape[0] + 1}",
                    df_to_write.values.tolist()
                )
            except Exception as e:
                st.error("Error escribiendo datos en Google Sheets.")
                st.exception(e)
                continue

            # aplicar colores sobre la columna D según los nuevos valores
            aplicar_colores(worksheet, df)

            st.success(f"Expediente {row['Número de Expediente']} actualizado y coloreado correctamente.")


