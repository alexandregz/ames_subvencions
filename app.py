import streamlit as st
import pandas as pd
import plotly.express as px
from bdns.fetch.client import BDNSClient 

st.set_page_config(
    page_title="Subvencións Concello de Ames",
    layout="wide"
)

# Función de apoio para poñer números en formato español (ex: 112.000,00 €)
def formato_euros(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

# 1. Carga e caché de datos
@st.cache_data(ttl=86400)
def cargar_datos_ames():
    client = BDNSClient()
    
    # Obter o xerador e convertelo en lista
    resultados = list(client.fetch_concesiones_busqueda(organos="35"))
    df = pd.DataFrame(resultados)
    
    if df.empty:
        st.warning("Non se atoparon datos.")
        return df

    # Identificar posíbeis nomes orixinais dos campos da BDNS
    col_fecha = next((c for c in ['fecConcesion', 'fechaConcesion', 'fecha_concesion', 'fecha'] if c in df.columns), None)
    col_importe = next((c for c in ['impConcesion', 'importeConcesion', 'importe', 'impSubvencion'] if c in df.columns), None)
    col_beneficiario = next((c for c in ['desBeneficiario', 'beneficiario', 'nombreBeneficiario', 'receptor'] if c in df.columns), None)
    col_programa = next((c for c in ['desConvocatoria', 'tituloConvocatoria', 'programa', 'numConvocatoria'] if c in df.columns), None)

    if not col_fecha:
        st.error("Non se atopou a columna de data. Columnas actuais do DataFrame:")
        st.write(list(df.columns))
        st.stop()

    # Mapeo e limpeza normalizada
    df['fecha_concesion'] = pd.to_datetime(df[col_fecha], errors='coerce')
    df['importe'] = pd.to_numeric(df[col_importe] if col_importe else 0, errors='coerce').fillna(0)
    df['beneficiario'] = df[col_beneficiario] if col_beneficiario else "Descoñecido"
    df['programa'] = df[col_programa] if col_programa else "Sen programa"

    # Columnas derivadas para as gráficas
    df['ano'] = df['fecha_concesion'].dt.year
    df['ano_mes'] = df['fecha_concesion'].dt.to_period('M').astype(str)
    
    return df

st.title("📊 Subvencións e Concesións — Concello de Ames")

try:
    with st.spinner("Descargando e procesando datos da BDNS..."):
        df = cargar_datos_ames()
    
    if not df.empty:
        # Resumo xeral
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Concesións", f"{len(df):,}".replace(",", "."))
        c2.metric("Importe Total Executado", formato_euros(df['importe'].sum()))
        c3.metric("Beneficiarios Únicos", f"{df['beneficiario'].nunique():,}".replace(",", "."))

        st.divider()

        # 2. Top 100 Receptores
        st.subheader("🏆 Top 100 Maiores Receptores de Subvencións")
        top_100 = (
            df.groupby('beneficiario')['importe']
            .sum()
            .reset_index()
            .sort_values(by='importe', ascending=False)
            .head(100)
        )
        
        fig_top100 = px.bar(
            top_100.sort_values(by='importe', ascending=True),
            x='importe',
            y='beneficiario',
            orientation='h',
            labels={'importe': 'Importe Total (€)', 'beneficiario': 'Beneficiario'},
            title="Maiores Receptores por Contía Acumulada"
        )
        
        # Formato da gráfica 1: euros, grosor dobre e hitos verticais cada 20k
        fig_top100.update_layout(
            height=2000,          # Aumentamos de 1000 a 2000 para dobrar o grosor das barras
            bargap=0.15,          # Axuste do oco entre barras
            separators=",.",      # Coma para decimais, punto para milleiros
            hovermode="y"
        )
        fig_top100.update_xaxes(
            tickformat=",.2f",    # Formato de dous decimais que usa os separators superiores
            ticksuffix=" €",
            showgrid=True,        # Mostrar marcas verticais
            gridwidth=1,
            gridcolor='rgba(128, 128, 128, 0.4)',
            dtick=20000           # Hitos cada 20.000
        )
        fig_top100.update_traces(
            hovertemplate="<b>%{y}</b><br>Importe: %{x:,.2f} €<extra></extra>"
        )
        st.plotly_chart(fig_top100, use_container_width=True)

        # -- TÁBOA COS RESULTADOS COMPLETA --
        st.info(f"ℹ️ **Hai un total de {len(df)} rexistros realmente nesta táboa, incluíndo tódolos resultados da consulta.** Podes facer scroll para velos todos.")
        
        # Seleccionamos as columnas e aplicamos o formato de euros SÓ de forma visual
        # Así a columna segue sendo numérica e a orde de frechas funcionará perfectamente
        tabela_estilizada = df[['fecha_concesion', 'beneficiario', 'importe', 'programa']].style.format({
            'importe': formato_euros
        })
        
        st.dataframe(
            tabela_estilizada, 
            height=400, 
            use_container_width=True
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
        
        fig_programas = px.bar(
            programas.sort_values(by='importe', ascending=True),
            x='importe',
            y='programa',
            orientation='h',
            height=800,
            labels={'importe': 'Gasto Total (€)', 'programa': 'Programa / Liña'},
            title="Gasto Acumulado por Programa (Top 30)"
        )
        fig_programas.update_layout(separators=",.")
        fig_programas.update_xaxes(tickformat=",.2f", ticksuffix=" €")
        fig_programas.update_traces(hovertemplate="Programa: %{y}<br>Gasto: %{x:,.2f} €<extra></extra>")
        st.plotly_chart(fig_programas, use_container_width=True)

        st.divider()

        # 4. Frecuencia e Convocatorias Recurrentes
        st.subheader("📅 Frecuencia de Concesións")
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
                custom_data=['importe_total'], # Pasamos o importe para a etiqueta flotante
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

except Exception as e:
    st.error(f"Ocorreu un erro ao extraer ou procesar os datos: {e}")