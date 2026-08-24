import streamlit as st
import pandas as pd
import plotly.express as px
import os
import logging
from datetime import datetime
from bdns.fetch.client import BDNSClient 

import textwrap

# Configuración do sistema de Logs
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/consultas.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

st.set_page_config(
    page_title="Buscador BDNS",
    layout="wide"
)

# CSS para forzar o texto multilíña nas celas da táboa
st.markdown("""
    <style>
    [data-testid="stDataFrame"] div[role="gridcell"] {
        white-space: normal !important;
        overflow-wrap: break-word !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

def formato_euros(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

def arranxar_url(url):
    if pd.isna(url) or not str(url).strip() or str(url).strip() == "None":
        return None
    url_str = str(url).strip()
    if not url_str.startswith('http'):
        return 'https://' + url_str
    return url_str

@st.cache_data(ttl=86400)
def cargar_datos_base(ambito_busca, nif_beneficiario, numero_convocatoria):
    client = BDNSClient()
    
    parametros = {}
    
    if ambito_busca == "Concello de Ames":
        parametros["organos"] = "35"
        
    nif = nif_beneficiario.strip() if nif_beneficiario else ""
    if nif:
        parametros["nifCif"] = nif
        
    conv = numero_convocatoria.strip() if numero_convocatoria else ""
    if conv:
        parametros["numeroConvocatoria"] = conv

    status_log = "OK"
    num_rexistros = 0
    erro_detalle = ""

    try:
        resultados = list(client.fetch_concesiones_busqueda(**parametros))
    except Exception as e:
        erro_detalle = str(e)
        try:
            resultados = list(client.fetch_concesiones_busqueda(organos="35" if ambito_busca == "Concello de Ames" else None))
        except Exception as e2:
            resultados = []
            status_log = "ERROR"
            erro_detalle = f"Principal: {erro_detalle} | Fallback: {str(e2)}"

    df = pd.DataFrame(resultados)
    num_rexistros = len(df)

    log_msg = f"Consulta BDNS | Parámetros: {parametros} | Ámbito: {ambito_busca} | Status: {status_log} | Rexistros obtidos: {num_rexistros}"
    if erro_detalle:
        log_msg += f" | Detalle: {erro_detalle}"
    logging.info(log_msg)

    if df.empty:
        return df

    col_fecha = next((c for c in ['fecConcesion', 'fechaConcesion', 'fecha_concesion', 'fecha'] if c in df.columns), None)
    col_importe = next((c for c in ['impConcesion', 'importeConcesion', 'importe', 'impSubvencion'] if c in df.columns), None)
    col_beneficiario = next((c for c in ['desBeneficiario', 'beneficiario', 'nombreBeneficiario', 'receptor'] if c in df.columns), None)
    col_nif = next((c for c in ['nifCif', 'nif', 'cif', 'nifBeneficiario'] if c in df.columns), None)
    col_programa = next((c for c in ['desConvocatoria', 'programa', 'numConvocatoria'] if c in df.columns), None)
    
    col_numero_convocatoria = next((c for c in ['numeroConvocatoria', 'idConvocatoria'] if c in df.columns), None)
    col_id_persona = 'idPersona' if 'idPersona' in df.columns else None
    col_convocatoria = 'convocatoria' if 'convocatoria' in df.columns else None
    col_nivel3 = 'nivel3' if 'nivel3' in df.columns else None
    col_bases = next((c for c in ['urlBR', 'basesReguladoras', 'bases', 'urlBasesReguladoras'] if c in df.columns), None)

    if not col_fecha:
        return pd.DataFrame()

    df['fecha_concesion'] = pd.to_datetime(df[col_fecha], errors='coerce')
    df['importe'] = pd.to_numeric(df[col_importe] if col_importe else 0, errors='coerce').fillna(0)
    df['beneficiario'] = df[col_beneficiario] if col_beneficiario else "Descoñecido"
    df['nif'] = df[col_nif] if col_nif else "Descoñecido"
    df['programa'] = df[col_programa] if col_programa else "Sen programa"
    
    df['numero_convocatoria'] = df[col_numero_convocatoria].astype(str) if col_numero_convocatoria else "0"
    df['id_persona'] = df[col_id_persona].astype(str) if col_id_persona else "0"
    df['convocatoria'] = df[col_convocatoria] if col_convocatoria else "Sen datos da convocatoria"
    df['convocatoria'] = df['convocatoria'].apply(lambda x: textwrap.fill(str(x), width=70) if pd.notna(x) else "Sen datos da convocatoria")
    
    df['concedente'] = df[col_nivel3] if col_nivel3 else "Sen datos do concedente"
    df['bases_reguladoras'] = df[col_bases].apply(arranxar_url) if col_bases else None

    df['url_convocatoria'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/" + df['numero_convocatoria']
    df['url_persona'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/concesiones/consulta/" + df['id_persona']

    df['ano'] = df['fecha_concesion'].dt.year
    df['ano_mes'] = df['fecha_concesion'].dt.to_period('M').astype(str)
    
    return df

# ==========================================
# INTERFAZ DE USUARIO
# ==========================================
st.sidebar.title("🔍 Buscador de Subvencións")

with st.sidebar.form("form_busca"):
    nif_beneficiario = st.text_input("NIF do Beneficiario", help="Exemplo: G70370713")
    numero_convocatoria = st.text_input("Nº BDNS da Convocatoria", help="Exemplo: 890379")
    
    ambito_busca = st.selectbox(
        "Administración / Ámbito", 
        ["Concello de Ames", "Todas as administracións"]
    )
    
    st.markdown("---")
    st.markdown("**Filtro por Importe (€)**")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        importe_min = st.number_input("Mínimo", min_value=0.0, value=0.0, step=100.0)
    with col_m2:
        importe_max = st.number_input("Máximo", min_value=0.0, value=0.0, step=100.0, help="Deixa en 0.0 para sen límite")

    buscar_btn = st.form_submit_button("Aplicar Filtros")

if ambito_busca == "Todas as administracións" and not (nif_beneficiario.strip() or numero_convocatoria.strip()):
    st.title("📊 Buscador de Subvencións a Nivel Nacional")
    st.error("🛑 **NON ESTÁ PERMITIDO:** Se seleccionas 'Todas as administracións', **é obrigatorio** introducir un NIF ou un Número de Convocatoria no buscador lateral para evitar colapsar a base de datos.")
    st.stop()

titulo_principal = "Subvencións do Concello de Ames" if ambito_busca == "Concello de Ames" else "Busca de Subvencións a Nivel Nacional"
st.title(f"📊 {titulo_principal}")

try:
    with st.spinner("Cargando e procesando datos da BDNS..."):
        df = cargar_datos_base(ambito_busca, nif_beneficiario, numero_convocatoria)
    
    if df.empty:
        st.warning("Non se atoparon datos dispoñibles co ámbito seleccionado.")
    else:
        if nif_beneficiario.strip() and 'nif' in df.columns:
            filtro_nif = nif_beneficiario.strip().lower()
            df_nif_check = df[df['nif'].astype(str).str.lower().str.contains(filtro_nif, na=False)]
            if not df_nif_check.empty:
                df = df_nif_check

        if numero_convocatoria.strip() and not df.empty:
            filtro_conv = numero_convocatoria.strip()
            df_conv_check = df[df['numero_convocatoria'].astype(str) == filtro_conv]
            if not df_conv_check.empty:
                df = df_conv_check

        if not df.empty:
            if importe_min > 0:
                df = df[df['importe'] >= importe_min]
            
            if importe_max > 0:
                df = df[df['importe'] <= importe_max]

        if df.empty:
            st.warning("Ningún rexistro coincide cos criterios de busca ou rangos de importe introducidos.")
        else:
            # Resumo xeral
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Concesións", f"{len(df):,}".replace(",", "."))
            c2.metric("Importe Total Executado", formato_euros(df['importe'].sum()))
            c3.metric("Beneficiarios Únicos", f"{df['beneficiario'].nunique():,}".replace(",", "."))

            st.divider()

            # Top Receptores
            st.subheader(f"🏆 Maiores Receptores de Subvencións")
            top_receptores = (
                df.groupby('beneficiario')['importe']
                .sum()
                .reset_index()
                .sort_values(by='importe', ascending=False)
                .head(100)
            )
            
            altura_grafica1 = max(400, len(top_receptores) * 20) 
            
            fig_top = px.bar(
                top_receptores.sort_values(by='importe', ascending=True),
                x='importe',
                y='beneficiario',
                orientation='h',
                labels={'importe': 'Importe Total (€)', 'beneficiario': 'Beneficiario'},
                title="Maiores Receptores por Contía Acumulada"
            )
            
            fig_top.update_layout(
                height=altura_grafica1, 
                bargap=0.15,
                separators=",.",
                hovermode="y"
            )
            fig_top.update_xaxes(
                tickformat=",.2f",
                ticksuffix=" €",
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128, 128, 128, 0.4)',
                dtick=20000
            )
            fig_top.update_traces(
                hovertemplate="<b>%{y}</b><br>Importe: %{x:,.2f} €<extra></extra>"
            )
            st.plotly_chart(fig_top, use_container_width=True)

            # ==========================================
            # TÁBOA 1: RESULTADOS DETALLADOS COMPLETA
            # ==========================================
            st.info(f"ℹ️ **Detalle de concesións (Total: {len(df)} rexistros).**")
            
            filtro_local = st.text_input(
                "🔍 Busca rápida na táboa (Beneficiario, Nº Convocatoria, Título da Convocatoria, Concedente ou Data):", 
                ""
            )
            
            df_tabla1 = df.copy()
            
            if filtro_local.strip():
                f = filtro_local.strip().lower()
                df_tabla1['fecha_str'] = df_tabla1['fecha_concesion'].dt.strftime('%d/%m/%Y').fillna('')
                
                mask = (
                    df_tabla1['beneficiario'].astype(str).str.lower().str.contains(f, na=False) |
                    df_tabla1['convocatoria'].astype(str).str.lower().str.contains(f, na=False) |
                    df_tabla1['fecha_str'].str.lower().str.contains(f, na=False) |
                    df_tabla1['concedente'].astype(str).str.lower().str.contains(f, na=False) |
                    df_tabla1['numero_convocatoria'].astype(str).str.lower().str.contains(f, na=False)
                )
                df_tabla1 = df_tabla1[mask]
                st.caption(f"Amosando **{len(df_tabla1)}** resultados que coinciden coa busca '{filtro_local}'.")
            
            columnas_tabela = [
                'fecha_concesion', 'url_persona', 'beneficiario', 'importe', 
                'concedente', 'url_convocatoria', 'convocatoria', 'bases_reguladoras'
            ]
            
            tabela_estilizada = df_tabla1[columnas_tabela].style.format({
                'importe': formato_euros
            })
            
            st.dataframe(
                tabela_estilizada, 
                height=800,
                use_container_width=True,
                hide_index=True, 
                column_config={
                    "fecha_concesion": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY"),
                    "url_persona": st.column_config.LinkColumn(
                        "ID Persoa",
                        help="Fai clic para ver as concesións desta persoa/entidade",
                        display_text=r"https://www\.pap\.hacienda\.gob\.es/bdnstrans/GE/es/concesiones/consulta/(.*)"
                    ),
                    "beneficiario": "Beneficiario",
                    "importe": "Importe",
                    "concedente": "Concedente",
                    "url_convocatoria": st.column_config.LinkColumn(
                        "Nº Convocatoria",
                        help="Fai clic para abrir a convocatoria na BDNS",
                        display_text=r"https://www\.pap\.hacienda\.gob\.es/bdnstrans/GE/es/convocatorias/(.*)"
                    ),
                    "convocatoria": st.column_config.TextColumn(
                        "Convocatoria",
                        help="Descrición da convocatoria da subvención",
                        width="large" 
                    ),
                    "bases_reguladoras": st.column_config.LinkColumn(
                        "Bases Reguladoras",
                        help="Ligazón ás bases reguladoras no boletín correspondente",
                        display_text="Ver Bases"
                    )
                }
            )

            # TÁBOA 2: RESUMO POR BENEFICIARIO
            st.subheader("👥 Resumo por Beneficiario")
            
            resumo_beneficiarios = (
                df.groupby('beneficiario')
                .agg(
                    importe_total=('importe', 'sum'),
                    numero_subvencions=('importe', 'count'),
                    importe_medio=('importe', 'mean'),
                    primeira_subvencion=('fecha_concesion', 'min'),
                    ultima_subvencion=('fecha_concesion', 'max')
                )
                .reset_index()
                .sort_values(by='importe_total', ascending=False)
            )

            resumo_estilizado = resumo_beneficiarios.style.format({
                'importe_total': formato_euros,
                'importe_medio': formato_euros
            })

            st.dataframe(
                resumo_estilizado,
                height=400,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "beneficiario": "Nome do Beneficiario",
                    "importe_total": "Importe Total",
                    "numero_subvencions": "Nº Subvencións",
                    "importe_medio": "Importe Medio",
                    "primeira_subvencion": st.column_config.DatetimeColumn("1ª Concesión", format="DD/MM/YYYY"),
                    "ultima_subvencion": st.column_config.DatetimeColumn("Última Concesión", format="DD/MM/YYYY")
                }
            )

            # TÁBOA 3: RESUMO POR CONCEDENTE
            st.subheader("🏛️ Resumo por Concedente")
            
            resumo_concedentes = (
                df.groupby('concedente')
                .agg(
                    importe_total=('importe', 'sum'),
                    numero_subvencions=('importe', 'count'),
                    importe_medio=('importe', 'mean'),
                    primeira_subvencion=('fecha_concesion', 'min'),
                    ultima_subvencion=('fecha_concesion', 'max')
                )
                .reset_index()
                .sort_values(by='importe_total', ascending=False)
            )

            resumo_conc_estilizado = resumo_concedentes.style.format({
                'importe_total': formato_euros,
                'importe_medio': formato_euros
            })

            st.dataframe(
                resumo_conc_estilizado,
                height=400,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "concedente": "Organismo Concedente",
                    "importe_total": "Importe Total Concedido",
                    "numero_subvencions": "Nº Subvencións",
                    "importe_medio": "Importe Medio",
                    "primeira_subvencion": st.column_config.DatetimeColumn("1ª Concesión", format="DD/MM/YYYY"),
                    "ultima_subvencion": st.column_config.DatetimeColumn("Última Concesión", format="DD/MM/YYYY")
                }
            )

            st.divider()

            # Maiores Programas por Gasto
            st.subheader("💡 Maiores Programas de Subvencións (por Gasto)")
            programas = (
                df.groupby('programa')['importe']
                .sum()
                .reset_index()
                .sort_values(by='importe', ascending=False)
                .head(30)
            )
            
            altura_grafica2 = max(400, len(programas) * 25)
            
            fig_programas = px.bar(
                programas.sort_values(by='importe', ascending=True),
                x='importe',
                y='programa',
                orientation='h',
                height=altura_grafica2,
                labels={'importe': 'Gasto Total (€)', 'programa': 'Programa / Liña'},
                title="Gasto Acumulado por Programa (Top 30)"
            )
            fig_programas.update_layout(separators=",.")
            fig_programas.update_xaxes(tickformat=",.2f", ticksuffix=" €")
            fig_programas.update_traces(hovertemplate="Programa: %{y}<br>Gasto: %{x:,.2f} €<extra></extra>")
            st.plotly_chart(fig_programas, use_container_width=True)

            st.divider()

            # Frecuencia e Convocatorias
            st.subheader("📅 Frecuencia de Concesións (Número)")
            tab_ano, tab_mes = st.tabs(["Por Ano", "Por Mes (Evolución)"])

            with tab_ano:
                por_ano = (
                    df.groupby('ano')
                    .agg(num_concesions=('importe', 'count'), importe_total=('importe', 'sum'))
                    .reset_index()
                    .dropna(subset=['ano'])
                )
                
                fig_ano = px.bar(
                    por_ano,
                    x='ano',
                    y='num_concesions',
                    custom_data=['importe_total'], 
                    labels={'ano': 'Ano', 'num_concesions': 'Número de Concesións'},
                    title="Número de Concesións por Ano"
                )
                fig_ano.update_layout(separators=",.")
                fig_ano.update_xaxes(type='category')
                fig_ano.update_traces(
                    hovertemplate="Ano: %{x}<br>Concesións: %{y}<br>Importe Total: %{customdata[0]:,.2f} €<extra></extra>"
                )
                st.plotly_chart(fig_ano, use_container_width=True)

            with tab_mes:
                por_mes = (
                    df.groupby('ano_mes')
                    .agg(num_concesions=('importe', 'count'), importe_total=('importe', 'sum'))
                    .reset_index()
                )
                por_mes = por_mes[por_mes['ano_mes'] != 'NaT']
                
                fig_mes = px.line(
                    por_mes,
                    x='ano_mes',
                    y='num_concesions',
                    custom_data=['importe_total'],
                    labels={'ano_mes': 'Ano-Mes', 'num_concesions': 'Número de Concesións'},
                    title="Evolución Mensual do Número de Concesións"
                )
                fig_mes.update_layout(separators=",.")
                fig_mes.update_traces(
                    hovertemplate="Mes: %{x}<br>Concesións: %{y}<br>Importe Total: %{customdata[0]:,.2f} €<extra></extra>"
                )
                st.plotly_chart(fig_mes, use_container_width=True)

            st.divider()

            # Evolución Económica
            st.subheader("💶 Evolución Económica (Importe Total en €)")
            tab_ano_imp, tab_mes_imp = st.tabs(["Importe por Ano", "Importe por Mes (Evolución)"])

            with tab_ano_imp:
                por_ano_imp = (
                    df.groupby('ano')
                    .agg(importe_total=('importe', 'sum'), num_concesions=('importe', 'count'))
                    .reset_index()
                    .dropna(subset=['ano'])
                )
                
                fig_ano_imp = px.bar(
                    por_ano_imp,
                    x='ano',
                    y='importe_total',
                    custom_data=['num_concesions'],
                    labels={'ano': 'Ano', 'importe_total': 'Importe Total (€)'},
                    title="Importe Total Concedido por Ano"
                )
                fig_fig_imp = fig_ano_imp
                fig_fig_imp.update_layout(separators=",.")
                fig_fig_imp.update_xaxes(type='category')
                fig_fig_imp.update_yaxes(tickformat=",.2f", ticksuffix=" €")
                fig_fig_imp.update_traces(
                    hovertemplate="Ano: %{x}<br>Importe Total: %{y:,.2f} €<br>Concesións: %{customdata[0]}<extra></extra>"
                )
                st.plotly_chart(fig_fig_imp, use_container_width=True)

            with tab_mes_imp:
                por_mes_imp = (
                    df.groupby('ano_mes')
                    .agg(importe_total=('importe', 'sum'), num_concesions=('importe', 'count'))
                    .reset_index()
                )
                por_mes_imp = por_mes_imp[por_mes_imp['ano_mes'] != 'NaT']
                
                fig_mes_imp = px.line(
                    por_mes_imp,
                    x='ano_mes',
                    y='importe_total',
                    custom_data=['num_concesions'],
                    labels={'ano_mes': 'Ano-Mes', 'importe_total': 'Importe Total (€)'},
                    title="Evolución Mensual do Importe Total Concedido"
                )
                fig_mes_imp.update_layout(separators=",.")
                fig_mes_imp.update_yaxes(tickformat=",.2f", ticksuffix=" €")
                fig_mes_imp.update_traces(
                    hovertemplate="Mes: %{x}<br>Importe Total: %{y:,.2f} €<br>Concesións: %{customdata[0]}<extra></extra>"
                )
                st.plotly_chart(fig_mes_imp, use_container_width=True)

except Exception as e:
    st.error(f"Ocorreu un erro ao extraer ou procesar os datos: {e}")