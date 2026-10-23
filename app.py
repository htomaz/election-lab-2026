"""Painel independente de apuração e projeção experimental presidencial (2026)."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from demo import gerar_demo
from modelo import carregar_historico, projetar_locais
from registro import salvar, serie
from tse import coletar, UFS, resultado_disponivel

st.set_page_config(page_title='Election Lab · Projeção 2026',layout='wide',page_icon='📊')
CORES={'Lula':'#ed6868','Flávio':'#36b5eb','Projeção Lula':'#f4ad91','Projeção Flávio':'#75d0ff'}

st.markdown('''<style>
.block-container{padding-top:1.5rem;max-width:1440px}
.hero{padding:17px 23px;border-radius:13px;background:linear-gradient(110deg,#17283f,#0b1423);border:1px solid #2b425b;margin-bottom:1rem}
.hero .eyebrow{color:#60dac7;font-weight:600;font-size:12px;letter-spacing:2px}
.hero h1{margin:0.2rem 0 0.4rem;font-size:2rem}
.hero .descr{color:#bbcadc;font-size:14px}
.stMetric{border:1px solid #2b4058;border-radius:12px;padding:12px;background:#142337}
[data-testid="stMetricLabel"]{font-size:13px}
</style>''',unsafe_allow_html=True)

st.markdown('''<div class="hero"><div class="eyebrow">ELECTION LAB / BRASIL 2026</div>
<h1>Apuração & projeção presidencial</h1><div class="descr">Resultado oficial do TSE separado de estimativas estatísticas · 2º turno · 25 de outubro de 2026</div></div>''',unsafe_allow_html=True)

with st.sidebar:
    st.header('Controle')
    modo=st.radio('Fonte de dados',['Demonstração fictícia','TSE oficial · 2º turno'],index=0)
    if modo.startswith('Demonstração'):
        nivel=st.slider('Apuração simulada (%)',1,100,43,1)
    else:
        st.caption('Consultas oficiais somente após 25/10/2026, 17h (horário de Brasília).')
    st.divider()
    st.subheader('Parâmetros experimentais')
    peso=st.slider('Peso do 1º turno 2026 no prior',0.,1.,.75,.05,
                   help='O restante do peso é aplicado à proporção de Lula no 2º turno de 2022.')
    vol=st.slider('Fator de votos válidos esperados',.90,1.10,1.,.01)
    intensidade=st.slider('Transmissão da parcial da UF aos votos restantes',0.,.8,.35,.05)
    st.caption('Uma projeção não calibrada tem erro desconhecido. Não é pesquisa eleitoral.')
    st.divider()
    st.markdown('[Fonte: dados TSE](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)')
    st.caption('Projeto independente; não é um produto do TSE.')

@st.cache_data(ttl=55,show_spinner=False)
def obter_tse():
    return coletar()

@st.fragment(run_every='60s')
def painel():
    demo=modo.startswith('Demonstração')
    if demo:
        brutos,historico=gerar_demo(nivel)
        erros={}
        st.warning('MODO DEMONSTRAÇÃO — todos os votos, parciais e projeções nesta tela são fictícios. Não são dados eleitorais reais.')
    else:
        if not resultado_disponivel():
            st.info('O 2º turno acontecerá em 25/10/2026. O TSE prevê divulgação a partir das 17h (Brasília). Nenhuma parcial do segundo turno está disponível aqui antes desse horário.')
            return
        with st.spinner('Consultando arquivos públicos EA20 do TSE (Brasil + 28 localidades)...'):
            brutos,erros=obter_tse()
        historico=carregar_historico()
        if 'BR' not in brutos:
            st.error('Não foi possível obter o arquivo nacional oficial. Nenhum resultado foi inferido ou inventado.')
            if erros:st.write('Diagnóstico:',erros)
            return
        if not historico:
            st.warning('Base histórica ausente: exibição oficial habilitada, mas projeção nacional desativada. Use IMPORTAR_HISTORICO.bat para carregar os ZIPs originais do TSE.')
        if len(brutos)<29:
            st.warning(f'{29-len(brutos)} arquivo(s) de localidades indisponível(is). As projeções só serão exibidas com cobertura histórica e arquivos suficientes; o resultado oficial nacional permanece independente.')
    nacional=brutos['BR']
    rel=projetar_locais(brutos,historico,peso,vol,intensidade)
    cobertura = rel['completo'] and len(brutos)==29 and all(brutos.get(uf,{}).get('secoes_total',0)>0 for uf in UFS)
    # Modelo não pode ser vendido como calibrado apenas porque 2022 está disponível.
    bases_26=sum(1 for uf in UFS if (2026,1) in historico.get(uf,{}))
    prior_completo=bases_26==len(UFS)
    mostrar_projecao=bool(cobertura and (demo or prior_completo) and (demo or nacional.get('validos',0)>0))
    p_secoes=100*nacional['secoes']/nacional['secoes_total'] if nacional['secoes_total'] else 0
    votos_2=nacional['lula']+nacional['flavio']
    pct_l=100*nacional['lula']/votos_2 if votos_2 else None
    pct_f=100*nacional['flavio']/votos_2 if votos_2 else None
    texto_pct=lambda x: f'{x:.2f}%'.replace('.',',') if x is not None else '—'
    def fmt_int(x):return f'{int(round(x)):,}'.replace(',','.')

    c1,c2,c3,c4=st.columns([1.25,1,1,1])
    c1.metric('Seções totalizadas',texto_pct(p_secoes),f"{fmt_int(nacional['secoes'])} / {fmt_int(nacional['secoes_total'])}",delta_color='off')
    c2.metric('Lula · parcial oficial' if not demo else 'Lula · parcial simulada',texto_pct(pct_l),fmt_int(nacional['lula']))
    c3.metric('Flávio · parcial oficial' if not demo else 'Flávio · parcial simulada',texto_pct(pct_f),fmt_int(nacional['flavio']))
    c4.metric('Votos válidos apurados',fmt_int(nacional['validos']))
    st.caption(f"Arquivo nacional gerado em: {nacional['geracao']} (horário conforme TSE) · Localidades recebidas: {max(0,len(brutos)-1)}/28")
    st.divider()
    l,r=st.columns([1.15,1])
    with l:
        st.subheader('Projeção nacional experimental')
        if mostrar_projecao:
            st.metric('Lula · votos válidos projetados',texto_pct(rel['lula_pct']),fmt_int(rel['lula']))
            st.metric('Flávio · votos válidos projetados',texto_pct(rel['flavio_pct']),fmt_int(rel['flavio']))
            st.caption('Modelo v0.1: soma dos votos apurados com estimativa dos votos restantes por UF. Não calibrado por município/zona nem acompanhado de intervalos de confiança.')
        else:
            st.info('Projeção não disponível: exigimos a base completa do 1º turno de 2026, histórico territorial para 28 localidades e leituras dos arquivos estaduais/exterior. Não substituímos dados ausentes por números fictícios.')
            st.caption(f'Base 2026 carregada em {bases_26}/28 localidades. Cobertura histórica geral: {len(rel["linhas"])}/28.')
    with r:
        st.subheader('Composição dos votos projetados')
        if mostrar_projecao:
            graf=go.Figure(go.Bar(x=[rel['lula_pct'],rel['flavio_pct']],y=['Lula','Flávio'],orientation='h',
                            marker_color=[CORES['Lula'],CORES['Flávio']],text=[texto_pct(rel['lula_pct']),texto_pct(rel['flavio_pct'])],textposition='inside'))
            graf.update_layout(height=230,margin=dict(l=20,r=15,t=5,b=25),xaxis=dict(range=[0,100],title='Votos válidos (%)'),
                               yaxis=dict(autorange='reversed'),showlegend=False,template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(graf,use_container_width=True)
        else:st.caption('Sem projeção validável para apresentar.')

    st.subheader('Evolução da apuração · observado × projetado')
    if demo:
        itens=[]
        for p in range(5,101,5):
            b,h=gerar_demo(p)
            n=b['BR']; pp=projetar_locais(b,h,peso,vol,intensidade)
            d=n['lula']+n['flavio']
            itens.append({'Progresso':100*n['secoes']/n['secoes_total'],
                          'Lula apurado':100*n['lula']/d if d else None,
                          'Flávio apurado':100*n['flavio']/d if d else None,
                          'Lula projetado':pp['lula_pct'],'Flávio projetado':pp['flavio_pct']})
        df_serie=pd.DataFrame(itens)
    elif not demo:
        salvar(nacional,rel if mostrar_projecao else None)
        df_log=serie()
        df_log=df_log[df_log['validos']>0].copy() if not df_log.empty else df_log
        if not df_log.empty:
            df_serie=pd.DataFrame({'Progresso':100*df_log['secoes']/df_log['secoes_total'].replace(0,float('nan')),
                 'Lula apurado':100*df_log['lula']/(df_log['lula']+df_log['flavio']).replace(0,float('nan')),
                 'Flávio apurado':100*df_log['flavio']/(df_log['lula']+df_log['flavio']).replace(0,float('nan')),
                 'Lula projetado':100*df_log['proj_lula']/(df_log['proj_lula']+df_log['proj_flavio']).replace(0,float('nan')),
                 'Flávio projetado':100*df_log['proj_flavio']/(df_log['proj_lula']+df_log['proj_flavio']).replace(0,float('nan'))})
        else:df_serie=pd.DataFrame()
    else:df_serie=pd.DataFrame()
    if not df_serie.empty:
        fig=go.Figure()
        for nome,cor,tracejado in [('Lula apurado',CORES['Lula'],'solid'),('Flávio apurado',CORES['Flávio'],'solid'),
                                    ('Lula projetado',CORES['Projeção Lula'],'dash'),('Flávio projetado',CORES['Projeção Flávio'],'dash')]:
            fig.add_trace(go.Scatter(x=df_serie['Progresso'],y=df_serie[nome],mode='lines+markers',name=nome,
                                     line=dict(color=cor,dash=tracejado,width=3),marker=dict(size=5),
                                     hovertemplate='%{x:.1f}% apurado · %{y:.2f}% votos válidos<extra>'+nome+'</extra>'))
        fig.update_layout(height=410,template='plotly_dark',legend=dict(orientation='h',y=1.13,x=0),
                          margin=dict(l=10,r=10,t=42,b=20),xaxis=dict(title='Seções totalizadas (%)',range=[0,101]),
                          yaxis=dict(title='Participação nos votos válidos (%)',range=[20,80]),
                          hovermode='x unified',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig,use_container_width=True)
        if demo:st.caption('Cada ponto é uma etapa fictícia. Não é trajetória observada de eleições reais.')
        else:st.caption('O histórico é registrado no banco SQLite local apenas enquanto a aplicação está aberta e coletando. Em hospedagem gratuita o armazenamento pode ser efêmero.')
    else:st.info('O gráfico temporal será preenchido quando chegarem novas parciais oficiais. O aplicativo não reconstrói snapshots passados que não foram coletados.')

    st.subheader('Detalhamento por unidade da federação')
    if rel['linhas']:
        df=pd.DataFrame(rel['linhas']).sort_values('Votos válidos projetados',ascending=False)
        df_exibir=df[['UF','Apuração (%)','Votos válidos apurados','Lula apurado','Flávio apurado',
                      'Lula histórico (%)','Lula projeção (%)','Lula projetado','Flávio projetado','Base 2026']].copy()
        if not mostrar_projecao:
            # Proibido insinuar projeção completa com bases insuficientes
            df_exibir=df_exibir[['UF','Apuração (%)','Votos válidos apurados','Lula apurado','Flávio apurado','Base 2026']]
        st.dataframe(df_exibir,hide_index=True,use_container_width=True,
                     column_config={'Apuração (%)':st.column_config.ProgressColumn('Seções apuradas (%)',min_value=0,max_value=100,format='%.1f%%'),
                                    'Lula histórico (%)':st.column_config.NumberColumn(format='%.2f%%'),
                                    'Lula projeção (%)':st.column_config.NumberColumn(format='%.2f%%')})
        st.download_button('Baixar tabela de UFs (CSV)',df_exibir.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                           file_name='apuracao_por_uf.csv',mime='text/csv')
    else:st.info('Nenhuma base territorial disponível nesta execução.')

    if not demo:
        with st.expander('Diagnóstico da coleta e critérios de segurança'):
            st.write('Arquivos recebidos:',len(brutos),'de 29 (BR, 27 UFs e exterior ZZ).')
            st.write('Histórico 2026 (1º turno):',bases_26,'de 28 localidades.')
            st.write('Falhas da consulta:',erros or 'Nenhuma')
            st.write('Apuração oficial e projeção são calculadas separadamente; números nacionais nunca são substituídos pela soma de UFs com horários diferentes.')
            st.write('A atualização automática ocorre aproximadamente a cada 60 segundos, enquanto a página está aberta. O botão abaixo força uma nova requisição.')
            if st.button('Consultar TSE novamente'):
                obter_tse.clear()
                st.rerun()

painel()

st.divider()
st.caption('Metodologia inicial: votos válidos, projeção estratificada por UF com peso histórico e suavização das parciais. Somente a leitura dos arquivos oficiais do TSE é resultado apurado; a projeção não é oficial. Configuração: eleição federal 6258; cargo 0001; âmbito nacional e 28 localidades.')
