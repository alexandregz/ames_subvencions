import streamlit as st
import pandas as pd
import plotly.express as px
import os
import re
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

# Inicializar o estado para a busca local se non existe
if "filtro_local_text" not in st.session_state:
    st.session_state["filtro_local_text"] = ""

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

# ==========================================
# DEFINICIÓN E DEDUCION DE ÁREAS
# ==========================================
REGLAS_AREAS = [
    (r"empresas|promoción del comercio|escaparates|hostelería|audiovisual|decoración de navidad|concurso de premios", "Comercio"),
    (r"educativos|educación", "Educación"),
    (r"literario|culturales", "Cultura"),
    (r"festejos|fiestas|baila con ames|canta con ames", "Festas"),
    (r"deportivas|deporte|clubs|deportistas|bertamiráns fc|milladoiro sd|milladorio sd", "Deporte"),
    (r"protección civil", "Protección Civil"),
    (r"nominativa", "Nominativa"),
    (r"servicios sociales|inclusión|familias numerosas", "Servizos Sociais"),
    (r"premio lengua|galetiktokers", "Lingua"),
]

# Áreas únicas ordenadas alfabeticamente + Sen clasificar
LISTA_AREAS_ORDENADAS = sorted(list(set([area for _, area in REGLAS_AREAS]))) + ["Sen clasificar"]

def deducir_area(texto):
    if not isinstance(texto, str):
        return ""
    txt = texto.lower()
    for patron, area in REGLAS_AREAS:
        if re.search(patron, txt):
            return area
    return ""

@st.cache_data(ttl=86400, show_spinner="⏳ Cargando datos base de BDNS...")
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
    df['concedente'] = df[col_nivel3] if col_nivel3 else "Sen datos do concedente"
    df['bases_reguladoras'] = df[col_bases].apply(arranxar_url) if col_bases else None

    df['url_convocatoria'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/" + df['numero_convocatoria']
    df['url_persona'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/concesiones/consulta/" + df['id_persona']
    df['area'] = df['convocatoria'].apply(deducir_area)

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

    area_seleccionada = st.selectbox(
        "Área da Convocatoria",
        ["Tódalas áreas"] + LISTA_AREAS_ORDENADAS
    )
    
    st.markdown("---")
    st.markdown("**Filtro por Importe (€)**")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        importe_min = st.number_input("Mínimo", min_value=0.0, value=0.0, step=100.0)
    with col_m2:
        importe_max = st.number_input("Máximo", min_value=0.0, value=0.0, step=100.0, help="Deixa en 0.0 para sen límite")

    buscar_btn = st.form_submit_button("Aplicar Filtros")

# Resetear o filtro de busca rápida na táboa cando se preme "Aplicar Filtros"
if buscar_btn:
    st.session_state["filtro_local_text"] = ""

if ambito_busca == "Todas as administracións" and not (nif_beneficiario.strip() or numero_convocatoria.strip()):
    st.title("📊 Buscador de Subvencións a Nivel Nacional")
    st.error("🛑 **NON ESTÁ PERMITIDO:** Se seleccionas 'Todas as administracións', **é obrigatorio** introducir un NIF ou un Número de Convocatoria no buscador lateral para evitar colapsar a base de datos.")
    st.stop()

titulo_principal = "Subvencións do Concello de Ames" if ambito_busca == "Concello de Ames" else "Busca de Subvencións a Nivel Nacional"
st.title(f"📊 {titulo_principal}")

if area_seleccionada != "Tódalas áreas":
    st.markdown(f"### 🏷️ Área seleccionada: **{area_seleccionada}**")

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

        # Filtro por Área
        if not df.empty and area_seleccionada != "Tódalas áreas":
            if area_seleccionada == "Sen clasificar":
                df = df[df['area'] == ""]
            else:
                df = df[df['area'] == area_seleccionada]

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
                key="filtro_local_text"
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

            # ====================================
            # AgGrid (para multilinea)
            # ====================================
            from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

            link_renderer = JsCode("""
            class UrlCellRenderer {
                init(params) {
                    this.eGui = document.createElement('a');
                    this.eGui.innerText = params.value ? params.value.split('/').pop() : '';
                    this.eGui.setAttribute('href', params.value);
                    this.eGui.setAttribute('target', '_blank');
                    this.eGui.style.textDecoration = 'underline';
                }
                getGui() {
                    return this.eGui;
                }
            }
            """)

            euro_formatter = JsCode("""
            function(params) {
                if (params.value == null) { return ''; }
                return params.value.toLocaleString('es-ES', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }) + ' €';
            }
            """)

            df_filtrado = df_tabla1[columnas_tabela]

            gb = GridOptionsBuilder.from_dataframe(df_filtrado)

            gb.configure_default_column(
                resizable=True,
                filter=True,
                sortable=True,
            )

            gb.configure_column(
                "fecha_concesion",
                header_name="Data", maxWidth=80,
                type=["dateColumnFilter", "customDateTimeFormat"],
                custom_format_string="dd/MM/yyyy",
            )

            gb.configure_column(
                "url_persona",
                header_name="ID Persoa",
                cellRenderer=link_renderer, maxWidth=90,
                tooltipField="url_persona",
            )

            gb.configure_column(
                "beneficiario",
                header_name="Beneficiario",
                minWidth=300, flex=2,
            )

            gb.configure_column(
                "importe",
                header_name="Importe",
                type=["numericColumn"],
                valueFormatter=euro_formatter, maxWidth=90,
                cellStyle={"textAlign": "right"},
            )

            gb.configure_column(
                "concedente",
                header_name="Concedente",
            )

            gb.configure_column(
                "url_convocatoria",
                header_name="Nº Convocatoria",
                cellRenderer=link_renderer, maxWidth=120,
                tooltipField="url_convocatoria",
            )

            gb.configure_column(
                "convocatoria",
                header_name="Convocatoria",
                wrapText=True,
                autoHeight=True,
                cellStyle={"white-space": "normal", "line-height": "1.4"},
                minWidth=300, flex=2,
                tooltipField="convocatoria",
            )

            gb.configure_column(
                "bases_reguladoras",
                header_name="Bases reguladoras",
                cellRenderer=link_renderer,
                tooltipField="bases_reguladoras",
            )

            grid_options = gb.build()
            grid_options["onGridReady"] = JsCode("""
            function(params) {
                var allColumnIds = [];
                params.columnApi.getAllColumns().forEach(function(column) {
                    allColumnIds.push(column.getId());
                });
                params.columnApi.autoSizeColumns(allColumnIds, false);
            }
            """)

            gb.configure_grid_options(
                enableRangeSelection=True,
                enableCellTextSelection=True,
                clipboardDelimiter="\t",
            )

            # Cálculo de altura elástica para Táboa 1 (mínimo 180px, máximo 800px)
            altura_t1 = max(180, min(800, len(df_tabla1) * 55 + 60))

            AgGrid(
                df_tabla1,
                gridOptions=grid_options,
                height=altura_t1,
                allow_unsafe_jscode=True,
                theme="streamlit",
                enable_enterprise_modules=False,
                fit_columns_on_grid_load=False,
            )

            # TÁBOA 2: RESUMO POR BENEFICIARIO
            st.subheader("👥 Resumo por Beneficiario")
            
            total_acumulado = df['importe'].sum()

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

            resumo_beneficiarios['porcentaxe_total'] = (
                (resumo_beneficiarios['importe_total'] / total_acumulado * 100)
                if total_acumulado > 0 else 0
            )

            columnas_resumo_ben = [
                'beneficiario', 'importe_total', 'porcentaxe_total',
                'numero_subvencions', 'importe_medio', 'primeira_subvencion', 'ultima_subvencion'
            ]
            resumo_beneficiarios = resumo_beneficiarios[columnas_resumo_ben]

            resumo_estilizado = resumo_beneficiarios.style.format({
                'importe_total': formato_euros,
                'porcentaxe_total': lambda x: f"{x:,.2f}".replace(".", ",") + " %",
                'importe_medio': formato_euros
            })

            # Cálculo de altura elástica para Resumo por Beneficiario (mínimo 140px, máximo 600px)
            altura_ben = max(140, min(600, (len(resumo_beneficiarios) + 1) * 38 + 25))

            st.dataframe(
                resumo_estilizado,
                height=altura_ben,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "beneficiario": "Nome do Beneficiario",
                    "importe_total": "Importe Total",
                    "porcentaxe_total": "% do Total",
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

            resumo_concedentes['porcentaxe_total'] = (
                (resumo_concedentes['importe_total'] / total_acumulado * 100)
                if total_acumulado > 0 else 0
            )

            columnas_resumo_conc = [
                'concedente', 'importe_total', 'porcentaxe_total',
                'numero_subvencions', 'importe_medio', 'primeira_subvencion', 'ultima_subvencion'
            ]
            resumo_concedentes = resumo_concedentes[columnas_resumo_conc]

            resumo_conc_estilizado = resumo_concedentes.style.format({
                'importe_total': formato_euros,
                'porcentaxe_total': lambda x: f"{x:,.2f}".replace(".", ",") + " %",
                'importe_medio': formato_euros
            })

            # Cálculo de altura elástica para Resumo por Concedente (mínimo 140px, máximo 500px)
            altura_conc = max(140, min(500, (len(resumo_concedentes) + 1) * 38 + 25))

            st.dataframe(
                resumo_conc_estilizado,
                height=altura_conc,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "concedente": "Organismo Concedente",
                    "importe_total": "Importe Total Concedido",
                    "porcentaxe_total": "% do Total",
                    "numero_subvencions": "Nº Subvencións",
                    "importe_medio": "Importe Medio",
                    "primeira_subvencion": st.column_config.DatetimeColumn("1ª Concesión", format="DD/MM/YYYY"),
                    "ultima_subvencion": st.column_config.DatetimeColumn("Última Concesión", format="DD/MM/YYYY")
                }
            )

            # TÁBOA 4: RESUMO POR CONVOCATORIA (AgGrid con Multilinea)
            st.subheader("📋 Resumo por Convocatoria")

            resumo_convocatorias = (
                df.groupby('numero_convocatoria')
                .agg(
                    url_convocatoria=('url_convocatoria', 'first'),
                    convocatoria=('convocatoria', 'first'),
                    area=('area', 'first'),
                    concedente=('concedente', 'first'),
                    numero_beneficiarios=('beneficiario', 'nunique'),
                    importe_total=('importe', 'sum'),
                    bases_reguladoras=('bases_reguladoras', 'first')
                )
                .reset_index()
            )

            columnas_resumo_conv = [
                'url_convocatoria', 'convocatoria', 'area', 'concedente',
                'numero_beneficiarios', 'importe_total', 'bases_reguladoras'
            ]

            df_conv_filtrado = resumo_convocatorias[columnas_resumo_conv].sort_values(by='importe_total', ascending=False)

            gb_conv = GridOptionsBuilder.from_dataframe(df_conv_filtrado)

            gb_conv.configure_default_column(
                resizable=True,
                filter=True,
                sortable=True,
            )

            gb_conv.configure_column(
                "url_convocatoria",
                header_name="Nº Convocatoria",
                cellRenderer=link_renderer, maxWidth=120,
                tooltipField="url_convocatoria",
            )

            gb_conv.configure_column(
                "convocatoria",
                header_name="Convocatoria",
                wrapText=True,
                autoHeight=True,
                cellStyle={"white-space": "normal", "line-height": "1.4"},
                minWidth=300, flex=2,
                tooltipField="convocatoria",
            )

            gb_conv.configure_column(
                "area",
                header_name="Área",
                maxWidth=130,
            )

            gb_conv.configure_column(
                "concedente",
                header_name="Concedente",
                minWidth=200,
            )

            gb_conv.configure_column(
                "numero_beneficiarios",
                header_name="Nº Total Beneficiarios",
                type=["numericColumn"],
                cellStyle={"textAlign": "right"},
                maxWidth=160,
            )

            gb_conv.configure_column(
                "importe_total",
                header_name="Importe Total Concedido",
                type=["numericColumn"],
                valueFormatter=euro_formatter,
                maxWidth=180,
                cellStyle={"textAlign": "right"},
            )

            gb_conv.configure_column(
                "bases_reguladoras",
                header_name="Bases reguladoras",
                cellRenderer=link_renderer,
                tooltipField="bases_reguladoras",
            )

            grid_options_conv = gb_conv.build()

            gb_conv.configure_grid_options(
                enableRangeSelection=True,
                enableCellTextSelection=True,
                clipboardDelimiter="\t",
            )

            # Cálculo de altura elástica para Táboa 4 (mínimo 180px, máximo 600px)
            altura_conv = max(180, min(600, len(df_conv_filtrado) * 55 + 60))

            AgGrid(
                df_conv_filtrado,
                gridOptions=grid_options_conv,
                height=altura_conv,
                allow_unsafe_jscode=True,
                theme="streamlit",
                enable_enterprise_modules=False,
                fit_columns_on_grid_load=False,
            )

            st.divider()

            # ==========================================
            # ANÁLISE VISUAL POR ÁREA (VERTICAMENTE)
            # ==========================================
            st.subheader("📌 Análise de Subvencións por Área")

            filas_apiladas = []
            for area_val in df['area'].unique():
                area_nome = area_val if area_val != "" else "Sen clasificar"
                df_area_item = df[df['area'] == area_val]
                total_area_item = df_area_item['importe'].sum()

                if total_area_item <= 0:
                    continue

                benef_area = (
                    df_area_item.groupby('beneficiario')['importe']
                    .sum()
                    .reset_index()
                    .sort_values(by='importe', ascending=False)
                )

                top5 = benef_area.head(5).copy()
                resto = benef_area.iloc[5:]

                if not resto.empty:
                    resto_sum = resto['importe'].sum()
                    row_outros = pd.DataFrame([{'beneficiario': 'Outros/as', 'importe': resto_sum}])
                    top5 = pd.concat([top5, row_outros], ignore_index=True)

                top5['area'] = area_nome
                top5['porcentaxe_area'] = (top5['importe'] / total_area_item) * 100
                filas_apiladas.append(top5)

            if filas_apiladas:
                df_apilado = pd.concat(filas_apiladas, ignore_index=True)

                totais_area_ordem = (
                    df_apilado.groupby('area')['importe']
                    .sum()
                    .reset_index()
                    .sort_values(by='importe', ascending=True)
                )
                ordem_areas = totais_area_ordem['area'].tolist()
                df_apilado['area_cat'] = pd.Categorical(df_apilado['area'], categories=ordem_areas, ordered=True)
                df_apilado = df_apilado.sort_values(by=['area_cat', 'importe'], ascending=[True, False])

                fig_apilada = px.bar(
                    df_apilado,
                    x='importe',
                    y='area',
                    color='beneficiario',
                    orientation='h',
                    title="Top 5 Beneficiarios por Área (€)",
                    labels={'importe': 'Importe Total (€)', 'area': 'Área', 'beneficiario': 'Beneficiario'},
                    custom_data=['beneficiario', 'porcentaxe_area']
                )

                fig_apilada.update_layout(
                    barmode='stack',
                    separators=",.",
                    height=max(450, len(ordem_areas) * 45),
                    showlegend=False
                )
                fig_apilada.update_xaxes(tickformat=",.2f", ticksuffix=" €")
                fig_apilada.update_traces(
                    hovertemplate="<b>Área: %{y}</b><br>Beneficiario: %{customdata[0]}<br>Importe: %{x:,.2f} €<br>% da Área: %{customdata[1]:,.2f} %<extra></extra>"
                )
                st.plotly_chart(fig_apilada, use_container_width=True)

                df_tabla_area = df_apilado[['area', 'beneficiario', 'porcentaxe_area']].sort_values(
                    by=['area', 'porcentaxe_area'], ascending=[True, False]
                )

                tabla_area_estilizada = df_tabla_area.style.format({
                    'porcentaxe_area': lambda x: f"{x:,.2f}".replace(".", ",") + " %"
                })

                altura_tab_area = max(180, min(650, (len(df_tabla_area) + 1) * 35 + 25))

                st.dataframe(
                    tabla_area_estilizada,
                    height=altura_tab_area,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "area": "Área",
                        "beneficiario": "Beneficiario",
                        "porcentaxe_area": "% do Total"
                    }
                )

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