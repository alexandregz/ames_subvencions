import streamlit as st
import pandas as pd
import plotly.express as px
from bdns.fetch.client import BDNSClient 

st.set_page_config(
    page_title="Buscador BDNS",
    layout="wide"
)

# Función de apoio para poñer números en formato español
def formato_euros(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

# 1. Carga de datos base (Cacheada por 24 horas)
@st.cache_data(ttl=86400)
def cargar_datos_base(ambito_busca):
    client = BDNSClient()
    
    try:
        if ambito_busca == "Concello de Ames":
            resultados = list(client.fetch_concesiones_busqueda(organos="35"))
        else:
            resultados = list(client.fetch_concesiones_busqueda())
    except Exception:
        resultados = list(client.fetch_concesiones_busqueda(organos="35"))

    df = pd.DataFrame(resultados)
    
    if df.empty:
        return df

    col_fecha = next((c for c in ['fecConcesion', 'fechaConcesion', 'fecha_concesion', 'fecha'] if c in df.columns), None)
    col_importe = next((c for c in ['impConcesion', 'importeConcesion', 'importe', 'impSubvencion'] if c in df.columns), None)
    col_beneficiario = next((c for c in ['desBeneficiario', 'beneficiario', 'nombreBeneficiario', 'receptor'] if c in df.columns), None)
    col_programa = next((c for c in ['desConvocatoria', 'programa', 'numConvocatoria'] if c in df.columns), None)
    
    col_id_convocatoria = 'numeroConvocatoria' if 'numeroConvocatoria' in df.columns else None
    col_id_persona = 'idPersona' if 'idPersona' in df.columns else None
    col_convocatoria = 'convocatoria' if 'convocatoria' in df.columns else None
    col_nivel3 = 'nivel3' if 'nivel3' in df.columns else None
    col_bases = next((c for c in ['basesReguladoras', 'bases', 'urlBasesReguladoras'] if c in df.columns), None)

    if not col_fecha:
        return pd.DataFrame()

    df['fecha_concesion'] = pd.to_datetime(df[col_fecha], errors='coerce')
    df['importe'] = pd.to_numeric(df[col_importe] if col_importe else 0, errors='coerce').fillna(0)
    df['beneficiario'] = df[col_beneficiario] if col_beneficiario else "Descoñecido"
    df['programa'] = df[col_programa] if col_programa else "Sen programa"
    
    df['id_convocatoria'] = df[col_id_convocatoria].astype(str) if col_id_convocatoria else "0"
    df['id_persona'] = df[col_id_persona].astype(str) if col_id_persona else "0"
    df['convocatoria'] = df[col_convocatoria] if col_convocatoria else "Sen datos da convocatoria"
    df['concedente'] = df[col_nivel3] if col_nivel3 else "Sen datos do concedente"
    df['bases_reguladoras'] = df[col_bases] if col_bases else "Sen datos das bases"

    df['url_convocatoria'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/" + df['id_convocatoria']
    df['url_persona'] = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/concesiones/consulta/" + df['id_persona']

    df['ano'] = df['fecha_concesion'].dt.year
    df['ano_mes'] = df['fecha_concesion'].dt.to_period('M').astype(str)
    
    return df

# ==========================================
# INTERFAZ DE USUARIO: FORMULARIO LATERAL
# ==========================================
st.sidebar.title("🔍 Buscador de Subvencións")

with st.sidebar.form("form_busca"):
    texto_beneficiario = st.text_input("Beneficiario (NIF ou Nome)", help="Exemplo: G15895527 ou nome parcial")
    ambito_busca = st.selectbox(
        "Administración / Ámbito", 
        ["Concello de Ames", "Todas as administracións"]
    )
    buscar_btn = st.form_submit_button("Aplicar Filtros")

# ==========================================
# LÓXICA PRINCIPAL
# ==========================================
titulo_principal = "Subvencións do Concello de Ames" if ambito_busca == "Concello de Ames" else "Busca de Subvencións a Nivel Nacional"
st.title(f"📊 {titulo_principal}")

try:
    with st.spinner("Cargando e procesando datos da BDNS..."):
        df = cargar_datos_base(ambito_busca)
    
    if df.empty:
        st.warning("Non se atoparon datos dispoñibles.")
    else:
        if texto_beneficiario.strip():
            filtro = texto_beneficiario.strip().lower()
            df = df[df['beneficiario'].astype(str).str.lower().str.contains(filtro, na=False)]
            st.caption(f"Filtro aplicado por texto: **'{texto_beneficiario}'** ({len(df)} resultados atopados)")

        if df.empty:
            st.warning("Ningún rexistro coincide co texto de busca introducido.")
        else:
            # Resumo xeral
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Concesións", f"{len(df):,}".replace(",", "."))
            c2.metric("Importe Total Executado", formato_euros(df['importe'].sum()))
            c3.metric("Beneficiarios Únicos", f"{df['beneficiario'].nunique():,}".replace(",", "."))

            st.divider()

            # 2. Top Receptores
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

            # -- TÁBOA COS RESULTADOS COMPLETA --
            st.info(f"ℹ️ **Hai un total de {len(df)} rexistros realmente nesta táboa.** Podes facer scroll para velos todos.")
            
            columnas_tabela = [
                'fecha_concesion', 'url_persona', 'beneficiario', 'importe', 
                'concedente', 'url_convocatoria', 'convocatoria', 'bases_reguladoras'
            ]
            tabela_estilizada = df[columnas_tabela].style.format({
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
                        "ID Convocatoria",
                        help="Fai clic para abrir a convocatoria na BDNS",
                        display_text=r"https://www\.pap\.hacienda\.gob\.es/bdnstrans/GE/es/convocatorias/(.*)"
                    ),
                    "convocatoria": st.column_config.TextColumn(
                        "Convocatoria",
                        help="Descrición da convocatoria da subvención",
                        width="large" 
                    ),
                    "bases_reguladoras": st.column_config.TextColumn(
                        "Bases Reguladoras",
                        help="Publicación das bases reguladoras",
                        width="large"
                    )
                }
            )

            st.divider()

            # 3. Maiores Programas por Gasto
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

            # 4. Frecuencia e Convocatorias Recurrentes (Número de Concesións)
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

            # 5. Evolución Económica (Importes por Ano e Mes)
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
                fig_ano_imp.update_layout(separators=",.")
                fig_ano_imp.update_xaxes(type='category')
                fig_ano_imp.update_yaxes(tickformat=",.2f", ticksuffix=" €")
                fig_ano_imp.update_traces(
                    hovertemplate="Ano: %{x}<br>Importe Total: %{y:,.2f} €<br>Concesións: %{customdata[0]}<extra></extra>"
                )
                st.plotly_chart(fig_ano_imp, use_container_width=True)

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