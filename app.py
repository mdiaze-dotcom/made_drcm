# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from google.oauth2.service_account import Credentials
import gspread
from gspread.utils import rowcol_to_a1

st.set_page_config(page_title="BD_Expedientes_DRCM", layout="wide")
st.title("📋 Actualización de Expedientes - DRCM")

SHEET_ID = "1mDeXDyKTZjNmRK8TnSByKbm3ny_RFhT4Rvjpqwekvjg"
SHEET_INDEX = 0

EXPECTED_COLS = [
    "Número de Expediente",
    "Dependencia",
    "Fecha de Expediente",
    "Días restantes",
    "Tipo de Proceso",
    "Tipo de Calidad Migratoria",
    "Fecha Inicio de Etapa",
    "Fecha Fin de Etapa",
    "Estado de Trámite",
    "Fecha Pase DRCM"
]

def get_gs_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=30)
def load_sheet():
    client = get_gs_client()
    sh = client.open_by_key(SHEET_ID)
    ws = sh.get_worksheet(SHEET_INDEX)
    header = ws.row_values(1)
    records = ws.get_all_records()
    df = pd.DataFrame(records) if records else pd.DataFrame(columns=EXPECTED_COLS)
    df.columns = [c.strip() for c in df.columns]
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    for col in ["Fecha de Expediente", "Fecha Inicio de Etapa", "Fecha Fin de Etapa", "Fecha Pase DRCM"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
    return df, ws, header

def compute_days(fecha_expediente, fecha_pase):
    if pd.isna(fecha_expediente):
        return None
    ref = pd.to_datetime(date.today()) if pd.isna(fecha_pase) else pd.to_datetime(fecha_pase)
    return int((ref.normalize() - fecha_expediente.normalize()).days)

df_all, ws_obj, header = load_sheet()
dependencias = sorted(df_all["Dependencia"].dropna().unique().tolist())

dep = st.selectbox("Seleccione la Dependencia:", ["-- Seleccione --"] + dependencias)
if dep == "-- Seleccione --":
    st.stop()

clave = st.text_input("Clave (DEPENDENCIA + 2025):", type="password")
if clave != dep.upper() + "2025":
    st.warning("Clave incorrecta.")
    st.stop()

st.success(f"Acceso concedido: {dep}")

df_dep = df_all[(df_all["Dependencia"] == dep) &
                (df_all["Estado de Trámite"].str.lower() == "pendiente")]

if df_dep.empty:
    st.info("No hay expedientes pendientes.")
    st.stop()

for idx, row in df_dep.iterrows():
    cols = st.columns([2,1,1,1])
    expediente = row["Número de Expediente"]

    with cols[0]:
        st.markdown(f"### {expediente}")
        fe = row["Fecha de Expediente"]
        st.write("Fecha Expediente:", fe.strftime("%d/%m/%Y %H:%M:%S") if not pd.isna(fe) else "---")

    with cols[1]:
        fecha_pase = row["Fecha Pase DRCM"]
        default_date = fecha_pase.date() if not pd.isna(fecha_pase) else date.today()
        nueva_fecha = st.date_input("Fecha Pase DRCM", value=default_date, key=f"f_{idx}")

    with cols[2]:
        dias = compute_days(row["Fecha de Expediente"], fecha_pase)
        st.write(f"Días restantes: {dias if dias is not None else '---'}")

    with cols[3]:
        if st.button("Guardar", key=f"g_{idx}"):

            try:
                client = get_gs_client()
                sh = client.open_by_key(SHEET_ID)
                ws_live = sh.get_worksheet(SHEET_INDEX)

                header_live = ws_live.row_values(1)
                if "Fecha Pase DRCM" not in header_live or "Días restantes" not in header_live:
                    st.error("Las columnas no existen físicamente en la hoja.")
                    continue

                col_fecha = header_live.index("Fecha Pase DRCM") + 1
                col_dias = header_live.index("Días restantes") + 1

                live_records = ws_live.get_all_records()
                df_live = pd.DataFrame(live_records)
                df_live.columns = [c.strip() for c in df_live.columns]

                matches = df_live.index[df_live["Número de Expediente"] == expediente].tolist()
                if not matches:
                    st.error("Expediente no encontrado.")
                    continue

                row_number = matches[0] + 2

                fecha_dt = datetime.combine(nueva_fecha, time())
                fecha_str = fecha_dt.strftime("%d/%m/%Y %H:%M:%S")

                fecha_exp_td = pd.to_datetime(df_live.loc[matches[0], "Fecha de Expediente"], errors="coerce", dayfirst=True)
                dias_calc = compute_days(fecha_exp_td, fecha_dt)
                dias_val = int(dias_calc) if dias_calc is not None else ""

                start = rowcol_to_a1(row_number, col_fecha)
                end = rowcol_to_a1(row_number, col_dias)
                ws_live.update(f"{start}:{end}", [[fecha_str, dias_val]], value_input_option='USER_ENTERED')

                st.success(f"Actualizado correctamente: {expediente}")
                st.cache_data.clear()

            except Exception as e:
                st.error("Error al actualizar Google Sheets.")
                st.exception(e)
