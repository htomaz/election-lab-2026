"""Election Lab 2026 v0.4: dashboard mobile, histórico TSE e projeção experimental."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from html import escape
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from diagnostico_zonas import diagnosticar_zonas
from auditoria_ao_vivo import reconciliar_brasil
from painel_zonas import exibir_painel_zonas
from demo import gerar_demo
from historicos_online import baixar_e_importar, URLS
from modelo import carregar_historico, projetar_locais
from registro import salvar, serie
from tse import coletar, UFS, resultado_disponivel

st.set_page_config(page_title='Election Lab 2026', page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
CORES = {'Lula':'#f06a70','Flávio':'#36b5eb','Lula projetado':'#ffad9b','Flávio projetado':'#7cd4ff'}
ROOT = Path(__file__).resolve().parent

st.markdown('''<style>
.block-container{padding-top:1rem;padding-bottom:3rem;max-width:1180px}
.hero{padding:18px 18px;border-radius:14px;background:linear-gradient(120deg,#172b43,#0c1728);border:1px solid #304763;margin-bottom:1rem}
.hero .eyebrow{color:#70e1ce;font-weight:650;font-size:11px;letter-spacing:2px}
.hero h1{margin:9px 0;font-size:clamp(1.45rem,4.5vw,2rem);line-height:1.25;color:#f6f9ff}
.hero .descr{color:#b8cce0;font-size:13px}
.stat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}
.stat{border:1px solid #2e4560;border-radius:12px;padding:12px 13px;background:#142338;min-width:0}
.stat .label{color:#c6d6e7;font-size:12px;line-height:1.4}
.stat .value{font-size:clamp(1.3rem,5.4vw,2rem);font-weight:650;line-height:1.5;color:#f6f8fb;font-variant-numeric:tabular-nums}
.stat .note{font-size:11px;color:#a8c0d7;overflow-wrap:anywhere}
.section-label{font-size:1.15rem;font-weight:700;margin:20px 0 6px}
@media(max-width:650px){
  .block-container{padding-left:0.75rem;padding-right:0.75rem}
  .hero{padding:16px}
  .stat{padding:10px}
  .stat .value{font-size:clamp(1.25rem,6vw,1.8rem)}
  [data-testid='stPlotlyChart']{overflow:hidden}
}
</style>''', unsafe_allow_html=True)

st.markdown('''<div class="hero"><div class="eyebrow">ELECTION LAB / BRASIL 2026</div>
<h1>Apuração & projeção presidencial</h1><div class="descr">Resultados oficiais separados de estimativas · 2º turno · 25/10/2026</div></div>''',unsafe_allow_html=True)

with st.sidebar:
    st.header('Configurações')
    modo = st.radio('Fonte de dados', ['Demonstração fictícia','TSE oficial · 2º turno'], index=0)
    if modo.startswith('Demonstração'):
        nivel = st.slider('Apuração simulada (%)', 1, 100, 43)
    else:
        nivel = 43
        st.caption('Consulta oficial disponível a partir de 25/10/2026, 17h, horário de Brasília.')
    st.divider()
    st.subheader('Parâmetros exploratórios')
    peso = st.slider('Peso do 1º turno 2026 no histórico', 0., 1., .75, .05)
    vol = st.slider('Volume esperado de votos válidos', .90, 1.10, 1., .01)
    intensidade = st.slider('Ajuste das parciais estaduais', 0., .8, .35, .05)
    st.caption('Estimativa experimental por UF, ainda sem calibração retrospectiva por zona.')
    st.markdown('[Fonte oficial do TSE](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)')


def fmt_pct(v):
    return f'{v:.2f}%'.replace('.', ',') if v is not None and pd.notna(v) else '—'


def fmt_int(v):
    return f'{int(round(v)):,}'.replace(',', '.')


def stat_card(label, value, note='', cor=None):
    color = f' style="color:{cor}"' if cor else ''
    return f'<div class="stat"><div class="label">{escape(str(label))}</div><div class="value"{color}>{escape(str(value))}</div><div class="note">{escape(str(note))}</div></div>'


def cards(items):
    st.markdown('<div class="stat-grid">'+''.join(stat_card(*item) for item in items)+'</div>',unsafe_allow_html=True)


@st.cache_data(ttl=55, show_spinner=False)
def obter_tse():
    return coletar()


@st.fragment(run_every='60s')
def painel():
    demo = modo.startswith('Demonstração')
    if demo:
        brutos, historico = gerar_demo(nivel)
        erros = {}
        st.warning('MODO DEMONSTRAÇÃO — números fictícios. Nenhum voto ou projeção desta tela representa resultado eleitoral real.')
    else:
        if not resultado_disponivel():
            st.info('A divulgação oficial do segundo turno ainda não começou. Os resultados serão consultados a partir de 25/10/2026, 17h (Brasília).')
            return
        with st.spinner('Consultando os arquivos oficiais do TSE...'):
            brutos, erros = obter_tse()
        historico = carregar_historico(ROOT/'historico_ufs.csv' if (ROOT/'historico_ufs.csv').exists() else ROOT/'data/historico_ufs.csv')
        if 'BR' not in brutos:
            st.error('O resultado oficial nacional ainda não foi obtido. Não substituímos dados ausentes por simulações.')
            with st.expander('Diagnóstico da coleta'):
                st.write(erros)
            return
        if not historico:
            st.warning('Histórico não encontrado. A apuração oficial pode ser exibida, mas a projeção permanecerá desativada. Use a aba **Históricos**.')
    nacional = brutos['BR']
    conciliacao_nacional = None if demo else reconciliar_brasil(brutos, UFS)
    rel = projetar_locais(brutos, historico, peso, vol, intensidade)
    cobertura = rel['completo'] and len(brutos)==29 and all(brutos.get(uf,{}).get('secoes_total',0)>0 for uf in UFS)
    bases26 = sum(1 for uf in UFS if (2026,1) in historico.get(uf,{}))
    mostrar = bool(cobertura and (demo or bases26==28) and (demo or nacional.get('validos',0)>0))
    if conciliacao_nacional and conciliacao_nacional['status']=='inconsistente':
        mostrar=False
        st.error('Diferença entre o arquivo BR e a soma das 28 localidades na mesma geração. '
                 'Projeções suspensas até nova verificação.')
    progresso = 100*nacional['secoes']/nacional['secoes_total'] if nacional['secoes_total'] else 0
    total2 = nacional['lula'] + nacional['flavio']
    lula_pct = 100*nacional['lula']/total2 if total2 else None
    flavio_pct = 100*nacional['flavio']/total2 if total2 else None
    st.progress(min(1.,max(0.,progresso/100)),text=f'{progresso:.2f}% das seções totalizadas'.replace('.',','))
    cards([
        ('Lula · parcial '+('simulada' if demo else 'oficial'),fmt_pct(lula_pct),fmt_int(nacional['lula'])+' votos',CORES['Lula']),
        ('Flávio · parcial '+('simulada' if demo else 'oficial'),fmt_pct(flavio_pct),fmt_int(nacional['flavio'])+' votos',CORES['Flávio']),
        ('Seções totalizadas',fmt_int(nacional['secoes']), 'de '+fmt_int(nacional['secoes_total'])),
        ('Votos válidos apurados',fmt_int(nacional['validos']), 'Arquivo BR · TSE' if not demo else 'Dados fictícios'),
    ])
    st.caption(f"Arquivo nacional: {nacional['geracao']} · Localidades recebidas: {max(0,len(brutos)-1)}/28")
    if conciliacao_nacional:
        st.caption('Auditoria nacional: '+conciliacao_nacional['mensagem'])
        if conciliacao_nacional['status']=='inconsistente':
            with st.expander('Diferenças BR menos soma das UFs'):
                st.json(conciliacao_nacional['diferencas'])

    st.markdown('<div class="section-label">Projeção nacional · modelo experimental</div>',unsafe_allow_html=True)
    if mostrar:
        cards([
            ('Lula · projetado',fmt_pct(rel['lula_pct']),fmt_int(rel['lula'])+' votos estimados',CORES['Lula projetado']),
            ('Flávio · projetado',fmt_pct(rel['flavio_pct']),fmt_int(rel['flavio'])+' votos estimados',CORES['Flávio projetado']),
        ])
        st.caption('Modelo v0.3: projeção por UF baseada em histórico territorial agregado e parciais locais. Não há backtest nem intervalo de confiança validado. Não é resultado oficial.')
    else:
        st.info(f'Projeção desativada: histórico 2026 disponível para {bases26}/28 localidades. É necessário histórico completo e arquivos oficiais das 28 localidades.')

    st.markdown('<div class="section-label">Evolução da apuração</div>',unsafe_allow_html=True)
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
    else:
        salvar(nacional, rel if mostrar else None)
        log=serie()
        log=log[log['validos']>0].copy() if not log.empty else log
        if not log.empty:
            den=(log['lula']+log['flavio']).replace(0,float('nan'))
            denp=(log['proj_lula']+log['proj_flavio']).replace(0,float('nan'))
            df_serie=pd.DataFrame({'Progresso':100*log['secoes']/log['secoes_total'].replace(0,float('nan')),
                'Lula apurado':100*log['lula']/den,'Flávio apurado':100*log['flavio']/den,
                'Lula projetado':100*log['proj_lula']/denp,'Flávio projetado':100*log['proj_flavio']/denp})
        else:
            df_serie=pd.DataFrame()
    if not df_serie.empty:
        fig=go.Figure()
        for nome, tracejado in [('Lula apurado','solid'),('Flávio apurado','solid'),('Lula projetado','dash'),('Flávio projetado','dash')]:
            fig.add_trace(go.Scatter(x=df_serie['Progresso'],y=df_serie[nome],mode='lines+markers',name=nome,
                line=dict(color=CORES[nome.split()[0]] if 'apurado' in nome else CORES[nome],dash=tracejado,width=2.5),
                marker=dict(size=4),hovertemplate='%{x:.1f}% apurado · %{y:.2f}% votos válidos<extra>'+nome+'</extra>'))
        fig.update_layout(height=365,template='plotly_dark',
            legend=dict(orientation='h',y=-.31,x=0,font=dict(size=10),itemwidth=30),
            margin=dict(l=5,r=5,t=5,b=85),
            xaxis=dict(title='Seções totalizadas (%)',range=[0,101]),
            yaxis=dict(title='Votos válidos (%)',range=[20,80]),
            hovermode='x unified',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False,'responsive':True})
        if demo:
            st.caption('Trajetórias fictícias apenas para testar o painel.')
        else:
            st.caption('A série oficial só registra consultas realizadas enquanto o aplicativo está ativo. O armazenamento gratuito pode ser temporário.')
    else:
        st.info('O gráfico será preenchido à medida que novas parciais forem coletadas.')

    with st.expander('Diagnóstico histórico por zona eleitoral (não é apuração ao vivo)'):
        caminho_zonas = ROOT/'historico_zonas.csv'
        if not caminho_zonas.exists():
            caminho_zonas = ROOT/'data/historico_zonas.csv'
        if caminho_zonas.exists():
            @st.cache_data(show_spinner=False)
            def ler_diagnostico(path, modificacao):
                return pd.DataFrame(diagnosticar_zonas(path))
            try:
                dz = ler_diagnostico(str(caminho_zonas), caminho_zonas.stat().st_mtime_ns)
                st.caption('Dispersão ponderada das preferências históricas entre zonas. '
                           'Sem parciais por zona em 2026, não há correção geográfica em tempo real.')
                st.dataframe(dz, hide_index=True, use_container_width=True)
            except (OSError, ValueError) as exc:
                st.error(f'Histórico territorial inválido: {exc}')
        else:
            st.info('Arquivo historico_zonas.csv não encontrado.')

    st.markdown('<div class="section-label">Detalhamento por UF</div>',unsafe_allow_html=True)
    if rel['linhas']:
        df=pd.DataFrame(rel['linhas']).sort_values('Votos válidos projetados',ascending=False)
        uf=st.selectbox('Selecione uma localidade',sorted(df['UF'].tolist()),index=sorted(df['UF'].tolist()).index('SP'))
        row=df[df['UF']==uf].iloc[0]
        cards([
            (f'{uf} · seções apuradas',fmt_pct(row['Apuração (%)']),'Percentual de seções'),
            (f'{uf} · votos apurados',fmt_int(row['Votos válidos apurados']),'Votos válidos'),
        ])
        if mostrar:
            cards([
                (f'{uf} · Lula projetado',fmt_pct(row['Lula projeção (%)']),'Modelo experimental',CORES['Lula projetado']),
                (f'{uf} · Flávio projetado',fmt_pct(100-row['Lula projeção (%)']),'Modelo experimental',CORES['Flávio projetado']),
            ])
        with st.expander('Ver tabela completa das 28 localidades'):
            colunas=['UF','Apuração (%)','Votos válidos apurados','Lula apurado','Flávio apurado','Base 2026']
            if mostrar:
                colunas += ['Lula histórico (%)','Lula projeção (%)','Lula projetado','Flávio projetado']
            tabela=df[colunas]
            st.dataframe(tabela,hide_index=True,use_container_width=True)
            st.download_button('Baixar tabela CSV',tabela.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                file_name='apuracao_por_uf.csv',mime='text/csv')
    else:
        st.info('Sem dados territoriais para detalhar.')
    exibir_painel_zonas(ROOT, peso, vol, intensidade, demonstracao=demo, estaduais=brutos)

    if not demo:
        with st.expander('Diagnóstico da coleta'):
            st.write(f'Localidades: {len(brutos)}/29 · Históricos 2026: {bases26}/28')
            st.write('Erros:',erros or 'Nenhum')
            if st.button('Consultar TSE novamente'):
                obter_tse.clear()
                st.rerun()


def status_historico():
    refs=carregar_historico(ROOT/'historico_ufs.csv' if (ROOT/'historico_ufs.csv').exists() else ROOT/'data/historico_ufs.csv')
    for ano,turno,rotulo in [(2022,2,'2022 · 2º turno'),(2026,1,'2026 · 1º turno')]:
        cobertura=sum(1 for uf in UFS if (ano,turno) in refs.get(uf,{}))
        st.write(f'**{rotulo}:** {cobertura}/28 localidades com histórico')
    return refs


@st.cache_data(show_spinner=False)
def ler_zonas(caminho,modificacao):
    return pd.read_csv(caminho,dtype={'uf':str,'municipio':str,'zona':str,'ano':int,'turno':int})


def historicos():
    st.subheader('Dados históricos oficiais')
    st.caption('Os arquivos originais são públicos e publicados pelo TSE. A importação é iniciada por você, sem necessidade de PC.')
    status_historico()
    st.info('Os históricos importados nesta hospedagem gratuita podem desaparecer quando o aplicativo reiniciar. Depois da importação, baixe os CSVs processados e envie-os ao GitHub para torná-los permanentes.')
    for ano,rotulo in [(2022,'2022 · 2º turno'),(2026,'2026 · 1º turno')]:
        with st.container(border=True):
            st.write(f'**Importar {rotulo}**')
            st.caption('O download pode ser grande e demorar vários minutos. Execute um ano de cada vez.')
            if st.button(f'Baixar e processar {ano} do TSE',key=f'importar_{ano}',type='primary'):
                bar=st.progress(0,text='Conectando ao TSE...')
                def progresso(recebidos,total):
                    if total:
                        pct=min(1.,recebidos/total)
                        bar.progress(pct,text=f'Baixando {recebidos//(1024*1024)} / {total//(1024*1024)} MB')
                    else:
                        bar.progress(0,text=f'Baixados {recebidos//(1024*1024)} MB...')
                try:
                    with st.spinner('Baixando e processando CSVs do TSE...'):
                        zonas=baixar_e_importar(ano,ROOT,progresso)
                    st.session_state['ultimo_historico']=f'{rotulo}: {zonas:,} combinações município/zona importadas.'
                    st.rerun()
                except Exception as e:
                    st.error(f'Importação não concluída: {type(e).__name__}: {str(e)[:350]}')
                    st.caption('Alternativa: tente novamente mais tarde ou utilize os arquivos ZIP oficiais no computador para gerar CSVs e envie-os ao GitHub.')
    if st.session_state.get('ultimo_historico'):
        st.success(st.session_state['ultimo_historico'])
    st.markdown('#### Salvar histórico de forma permanente')
    st.write('Após importar **ambos os anos**, baixe os dois arquivos abaixo e envie-os à **raiz** do repositório `htomaz/election-lab-2026` no GitHub.')
    for nome in ['historico_ufs.csv','historico_zonas.csv']:
        caminho=ROOT/nome
        if caminho.exists():
            tamanho=caminho.stat().st_size
            if tamanho <= 24*1024*1024:
                st.download_button(f'Baixar {nome} ({tamanho/1024/1024:.1f} MB)',
                    data=caminho.read_bytes(),file_name=nome,mime='text/csv',key=f'download_{nome}')
            else:
                st.warning(f'{nome} tem {tamanho/1024/1024:.1f} MB e pode exceder o limite de upload do GitHub pelo navegador.')
    st.divider()
    st.markdown('#### Consultar histórico por município e zona')
    zona_path=next((p for p in [ROOT/'historico_zonas.csv',ROOT/'data/historico_zonas.csv'] if p.exists()),None)
    if zona_path:
        try:
            z=ler_zonas(str(zona_path),zona_path.stat().st_mtime_ns)
            uf=st.selectbox('UF histórica',sorted(z['uf'].unique()),key='uf_historico')
            mun=st.selectbox('Código TSE do município',sorted(z.loc[z['uf']==uf,'municipio'].unique()),key='mun_historico')
            zona=st.selectbox('Zona eleitoral',sorted(z.loc[(z['uf']==uf)&(z['municipio']==mun),'zona'].unique()),key='zona_historico')
            subset=z[(z['uf']==uf)&(z['municipio']==mun)&(z['zona']==zona)].copy()
            subset['Lula (%) válidos']=100*subset['lula']/subset['validos'].replace(0,float('nan'))
            subset['Candidato 22 (%) válidos']=100*subset['direita']/subset['validos'].replace(0,float('nan'))
            st.dataframe(subset[['ano','turno','lula','direita','validos','Lula (%) válidos','Candidato 22 (%) válidos']],
                hide_index=True,use_container_width=True)
            st.caption('Em 2022, o número 22 corresponde a Jair Bolsonaro; em 2026, a Flávio Bolsonaro. Os percentuais de 2026 usam todos os votos válidos do primeiro turno como denominador.')
        except Exception as e:
            st.error(f'Falha na leitura do histórico territorial: {e}')
    else:
        st.caption('A consulta por zona aparecerá após importar um ZIP histórico ou enviar historico_zonas.csv ao repositório.')
    st.caption('Fonte: https://dadosabertos.tse.jus.br/dataset/resultados-2022 e https://dadosabertos.tse.jus.br/dataset/resultados-2026')


aba1,aba2=st.tabs(['📈 Painel','🗂️ Históricos'])
with aba1:
    painel()
with aba2:
    historicos()
st.divider()
st.caption('Election Lab 2026 v0.4 · Projeto independente. Resultado apurado = fonte TSE; projeções = estimativas experimentais, não oficiais.')
