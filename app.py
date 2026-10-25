"""Election Lab 2026 v0.5: dashboard mobile, histórico TSE e projeção experimental."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import os
import subprocess
from html import escape
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import plotly.graph_objects as go
import streamlit as st
from diagnostico_zonas import diagnosticar_zonas
from auditoria_ao_vivo import reconciliar_brasil
from municipios_tse import obter_municipios, nome_municipio, ordenar_municipios
from painel_zonas import exibir_painel_zonas
from painel_zonal_completo import exibir_modelo_zonal_completo
from demo import gerar_demo
from historicos_online import baixar_e_importar, URLS
from modelo import carregar_historico, projetar_locais
from modelo_zonas import carregar_zonas
from perfil_geografico import compor_perfis_conciliados
from registro import salvar, serie, exportar_csv, restaurar_csv
from recuperacao_nacional import recuperar_serie_de_snapshot
from curva_continuidade import limpar_pontos, construir_continuacao
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
    testar_correcao_geografica = st.checkbox(
        'Testar correção geográfica de composição (experimental)',
        value=False,
        help='Só utiliza zonas totalmente concluídas que reconciliam exatamente '
             'com a parcial oficial da respectiva UF. Sem dados consistentes, '
             'o modelo anterior permanece. Não houve calibração para 2T2026.')
    st.markdown('[Fonte oficial do TSE](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados)')


@st.cache_data(ttl=86400, show_spinner=False)
def carregar_nomes_municipais():
    """Uma consulta à configuração de municípios do TSE por dia, compartilhada no app."""
    return obter_municipios(ROOT/'municipios_2026.csv')


def nomes_municipais_seguros():
    try:
        return carregar_nomes_municipais(), None
    except (OSError, ValueError, requests.RequestException) as exc:
        return {}, f'{type(exc).__name__}: {str(exc)[:130]}'


def fmt_pct(v):
    return f'{v:.2f}%'.replace('.', ',') if v is not None and pd.notna(v) else '—'


def fmt_int(v):
    return f'{int(round(v)):,}'.replace(',', '.')


def stat_card(label, value, note='', cor=None):
    color = f' style="color:{cor}"' if cor else ''
    return f'<div class="stat"><div class="label">{escape(str(label))}</div><div class="value"{color}>{escape(str(value))}</div><div class="note">{escape(str(note))}</div></div>'


def cards(items):
    st.markdown('<div class="stat-grid">'+''.join(stat_card(*item) for item in items)+'</div>',unsafe_allow_html=True)



@st.cache_data(show_spinner=False)
def carregar_curvas_medias_fixas():
    """100 pontos fixos, por percentual de votos (não de seções).

    Cada média é a combinação 50/50 dos ritmos de 2022 T2 e 2026 T1,
    condicionada ao desfecho hipotético Lula 49,02% / Flávio 50,98%.
    """
    caminho = ROOT/'data/curvas_medias_apuracao_2022T2_2026T1.csv'
    df = pd.read_csv(caminho, sep=';', decimal=',')
    esperado = ['votos_apurados_pct', 'media_lula_pct', 'media_flavio_pct']
    if list(df.columns) != esperado or len(df) != 100:
        raise ValueError('Curvas médias: arquivo inválido ou incompleto')
    if df['votos_apurados_pct'].tolist() != list(range(1, 101)):
        raise ValueError('Curvas médias: estágios de 1 a 100% inválidos')
    if not ((df['media_lula_pct'] + df['media_flavio_pct'] - 100).abs() < 0.00011).all():
        raise ValueError('Curvas médias: Lula + Flávio não somam 100%')
    return df


def exibir_grafico_com_referencias(df_serie, demo=False, final_modelo=None):
    """Evolução observada (cheia) e projeção conectada (tracejada).

    Todas as linhas usam o mesmo eixo: % dos votos Lula+Flávio em relação
    ao volume total final estimado PELO MODELO NO MOMENTO DA CONSULTA.
    """
    fig = go.Figure()

    observados = []
    if not df_serie.empty:
        for _, linha in df_serie.iterrows():
            observados.append((
                linha.get('Progresso'),
                linha.get('Lula apurado'),
                linha.get('Capturado'),
            ))
    observados = limpar_pontos(observados)

    series_grafico = []
    if observados:
        # Duas linhas grossas e contínuas SOMENTE até a última parcial.
        x_real = [p[0] for p in observados]
        lula_real = [p[1] for p in observados]
        flavio_real = [100. - p[1] for p in observados]
        for titulo, valores, cor in [
            ('Lula · apurado real', lula_real, '#e64354'),
            ('Flávio · apurado real', flavio_real, '#2696f0'),
        ]:
            fig.add_trace(go.Scatter(
                x=x_real, y=valores, mode='lines+markers', name=titulo,
                line=dict(color=cor, width=4.5),
                marker=dict(size=5),
                hovertemplate='%{x:.1f}% dos votos · %{y:.2f}%'
                              '<extra>'+titulo+'</extra>',
            ))
            series_grafico.extend(valores)

        # A continuação parte EXATAMENTE da última parcial observada,
        # acompanha sua inclinação recente e converge ao resultado do modelo.
        futura = construir_continuacao(observados, final_modelo)
        if futura:
            x_fut = [p[0] for p in futura]
            for titulo, valores, cor in [
                ('Lula · continuação projetada', [p[1] for p in futura], '#e64354'),
                ('Flávio · continuação projetada', [100. - p[1] for p in futura], '#2696f0'),
            ]:
                fig.add_trace(go.Scatter(
                    x=x_fut, y=valores, mode='lines', name=titulo,
                    line=dict(color=cor, width=4, dash='dash'),
                    hovertemplate='%{x:.1f}% dos votos · %{y:.2f}%'
                                  '<extra>'+titulo+' · modelo experimental</extra>',
                ))
                series_grafico.extend(valores)

    # Zoom vertical baseado EXCLUSIVAMENTE nas curvas oficiais e projetadas.
    # Evita que o cenário de pesquisas, não exibido, afaste as linhas.
    if series_grafico:
        minimo, maximo = min(series_grafico), max(series_grafico)
        margem = max(.18, (maximo-minimo)*.035)
        faixa_y = [max(0., minimo-margem), min(100., maximo+margem)]
    else:
        faixa_y = [45., 55.]
    fig.update_layout(
        height=655, template='plotly_dark',
        legend=dict(orientation='h', y=1.02, yanchor='bottom', x=0,
                    font=dict(size=10), itemwidth=30),
        margin=dict(l=5, r=5, t=95, b=70),
        xaxis=dict(title='Votos apurados / total final estimado (%)',
                   range=[0,101], tick0=0, dtick=10, showspikes=False),
        yaxis=dict(title='Participação Lula + Flávio (%)',
                   range=faixa_y,
                   ticksuffix='%', tickformat='.1f', showspikes=False),
        hovermode='closest', hoverdistance=20,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    if 'revisao_grafico_evolucao' not in st.session_state:
        st.session_state['revisao_grafico_evolucao'] = 0
    if st.button('✕ Fechar detalhes do gráfico', key='fechar_hover_evolucao'):
        st.session_state['revisao_grafico_evolucao'] += 1
    st.plotly_chart(fig, width="stretch",
                    key=f"evolucao_apuracao_{st.session_state['revisao_grafico_evolucao']}",
                    config={'displayModeBar':False, 'responsive':True})
    st.caption('Linhas grossas contínuas = votos observados; grossas tracejadas = '
               'continuação a partir da última parcial até o resultado projetado '
               'pelo modelo atual. A tendência inicial usa a evolução recente '
               'das parciais no tempo; o trajeto intermediário é uma simulação.')
    if not observados:
        st.caption('Aguardando parcial posicionável no eixo de votos e projeção '
                   'de volume final validada; aguardando dados para traçar as curvas.')
    elif not construir_continuacao(observados, final_modelo):
        if observados[-1][0] < 100. - 1e-8:
            st.caption('Continuação indisponível enquanto o modelo não apresentar '
                       'um resultado final válido; o observado não é extrapolado.')
    if demo:
        st.caption('Modo demonstração: parciais e projeção são fictícias.')





@st.cache_data(show_spinner=False)
def _ler_referencias_zonais_seguras(caminho, modificacao):
    return carregar_zonas(caminho)


@st.cache_data(show_spinner=False)
def _ler_snapshot_geografico_seguro(caminho, modificacao):
    with open(caminho, encoding='utf-8') as arq:
        return json.load(arq)


def composicao_zonal_uf_somente_quando_conciliada(brutos):
    """Edição opcional: snapshots EA20 6258 não substituem dados oficiais UF.

    Sem catálogo EA16 e SOMA EXATA dos votos de zonas concluídas à parcial
    UF do mesmo pleito, nunca há ajuste de seleção no gráfico nacional.
    """
    zonas=next((p for p in [ROOT/'historico_zonas.csv',
                            ROOT/'data/historico_zonas.csv'] if p.is_file()),None)
    snap=ROOT/'dados_zonais_6258.json'
    if zonas is None or not snap.is_file():
        return {}
    try:
        referencias=_ler_referencias_zonais_seguras(str(zonas),zonas.stat().st_mtime_ns)
        snapshot=_ler_snapshot_geografico_seguro(str(snap),snap.stat().st_mtime_ns)
        return compor_perfis_conciliados(brutos,snapshot,referencias)
    except (OSError,ValueError,KeyError,TypeError,UnicodeError):
        # Sem sinal de cobertura geográfica comprovada, permanece o modelo
        # original por UF. Não ocultar nem alterar os votos oficiais.
        return {}


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
            st.markdown('<div class="section-label">Evolução da apuração</div>',unsafe_allow_html=True)
            exibir_grafico_com_referencias(pd.DataFrame())
            return
        with st.spinner('Consultando os arquivos oficiais do TSE...'):
            brutos, erros = obter_tse()
        historico = carregar_historico(ROOT/'historico_ufs.csv' if (ROOT/'historico_ufs.csv').exists() else ROOT/'data/historico_ufs.csv')
        if 'BR' not in brutos:
            st.error('O resultado oficial nacional ainda não foi obtido. Não substituímos dados ausentes por simulações.')
            with st.expander('Diagnóstico da coleta'):
                st.write(erros)
            st.markdown('<div class="section-label">Evolução da apuração · referência fixa</div>',unsafe_allow_html=True)
            exibir_grafico_com_referencias(pd.DataFrame())
            return
        if not historico:
            st.warning('Histórico não encontrado. A apuração oficial pode ser exibida, mas a projeção permanecerá desativada. Use a aba **Históricos**.')
    nacional = brutos['BR']
    conciliacao_nacional = None if demo else reconciliar_brasil(brutos, UFS)
    perfis_geograficos = (
        composicao_zonal_uf_somente_quando_conciliada(brutos)
        if (not demo and testar_correcao_geografica) else {})
    rel = projetar_locais(brutos, historico, peso, vol, intensidade,
                         composicao_historica=perfis_geograficos)
    cobertura = rel['completo'] and len(brutos)==29 and all(brutos.get(uf,{}).get('secoes_total',0)>0 for uf in UFS)
    bases26 = sum(1 for uf in UFS if (2026,1) in historico.get(uf,{}))
    mostrar = bool(cobertura and (demo or bases26==28) and (demo or nacional.get('validos',0)>0))
    ufs_correcao_geografica = [
        linha['UF'] for linha in rel['linhas']
        if linha.get('Perfil geográfico validado')]
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
        # Diferenças absolutas entre os dois candidatos, sempre calculadas
        # a partir do mesmo resultado projetado (nunca da parcial oficial).
        lider = ('Flávio' if rel['flavio'] > rel['lula'] else
                 'Lula' if rel['lula'] > rel['flavio'] else 'Empate')
        diferenca_votos = abs(int(rel['flavio']) - int(rel['lula']))
        total_projetado = int(rel['lula']) + int(rel['flavio'])
        diferenca_pp = (100. * diferenca_votos / total_projetado
                        if total_projetado else 0.)
        cards([
            ('Diferença projetada · pontos percentuais',
             fmt_pct(diferenca_pp).replace('%', ' p.p.'),
             'Vantagem de ' + lider if lider != 'Empate' else 'Empate projetado'),
            ('Diferença projetada · votos',
             fmt_int(diferenca_votos),
             'Vantagem de ' + lider if lider != 'Empate' else 'Empate projetado'),
        ])
        st.caption('Modelo experimental por UF: estimativas finais com ' 
                   'históricos de 2022 e 2026. A composição das localidades '
                   'ainda não apuradas só é corrigida quando snapshots zonais '
                   'oficiais concluídos coincidem exatamente com totais UF; '
                   'não implica calibração estatística validada.')
        if not demo and testar_correcao_geografica:
            st.caption('Correção geográfica experimental confirmada: '
                       + (', '.join(sorted(ufs_correcao_geografica))
                          if ufs_correcao_geografica else 'nenhuma UF — '
                          'modelo anterior preservado'))
    else:
        st.info(f'Projeção desativada: histórico 2026 disponível para {bases26}/28 localidades. É necessário histórico completo e arquivos oficiais das 28 localidades.')

    st.markdown('<div class="section-label">Evolução da apuração</div>',unsafe_allow_html=True)
    if demo:
        itens=[]
        total_atual_modelo = rel['lula'] + rel['flavio'] if mostrar else 0
        # O modo demonstração mostra somente parciais até o estágio selecionado.
        for p in sorted(set([*range(5, nivel+1, 5), nivel])):
            b,h=gerar_demo(p)
            n=b['BR']; pp=projetar_locais(b,h,peso,vol,intensidade)
            d=n['lula']+n['flavio']
            itens.append({'Progresso':min(100., 100*d/total_atual_modelo) if total_atual_modelo>0 else None,
                          'Lula apurado':100*n['lula']/d if d else None,
                          'Flávio apurado':100*n['flavio']/d if d else None,
                          'Capturado':None})
        df_serie=pd.DataFrame(itens)
    else:
        # O SQLite do Streamlit gratuito é efêmero. Se reiniciar vazio,
        # reconstituir primeiro os snapshots BR já validados que estiverem
        # presentes no backup local. Não consulta ou mistura fontes externas.
        recuperacao = None
        if serie().empty:
            recuperacao = recuperar_serie_de_snapshot(ROOT/'dados_zonais_6258.json')
        salvar(nacional, rel if mostrar else None)
        with st.expander('Backup e recuperação da série nacional'):
            if recuperacao and recuperacao.get('restaurado'):
                st.success('Série nacional recuperada do snapshot oficial validado: '
                           + str(recuperacao.get('linhas_recebidas',0)) + ' gerações.')

            backup=exportar_csv()
            if backup:
                st.download_button('Baixar histórico de apuração/projeções (CSV)',
                                   data=backup.encode('utf-8-sig'),
                                   file_name='election_lab_serie_2026.csv',
                                   mime='text/csv',key='backup_nacional')
            else:
                st.caption('Ainda não há gerações nacionais registradas.')
            enviado=st.file_uploader('Importar backup CSV anterior',
                                     type=['csv'],key='restaurar_serie')
            if enviado is not None and st.button(
                    'Restaurar série a partir deste arquivo',
                    key='confirmar_restaurar_serie'):
                try:
                    res=restaurar_csv(enviado.getvalue())
                    st.success(f"Histórico reconciliado: {res['linhas_recebidas']} linhas "
                               "recebidas, sem regredir gerações existentes.")
                    st.rerun()
                except (ValueError,OSError,UnicodeError) as exc:
                    st.error(f'Backup rejeitado: {exc}')
            st.caption('Backups manuais são importantes: os arquivos internos '
                       'do Streamlit gratuito podem desaparecer após reinício.')
        log=serie()
        log=log[log['validos']>0].copy() if not log.empty else log
        if not log.empty:
            den=(log['lula']+log['flavio']).replace(0,float('nan'))
            # Um denominador ÚNICO (estimativa atual do modelo) para todos
            # os registros evita retrocessos artificiais por mudanças de base.
            volume_modelo = rel['lula'] + rel['flavio'] if mostrar else 0
            df_serie=pd.DataFrame({'Progresso':(100*den/volume_modelo).clip(lower=0, upper=100)
                                   if volume_modelo>0 else float('nan'),
                'Lula apurado':100*log['lula']/den,
                'Flávio apurado':100*log['flavio']/den,
                'Capturado':log['capturado']})
        else:
            df_serie=pd.DataFrame()
    exibir_grafico_com_referencias(
        df_serie, demo=demo, final_modelo=rel['lula_pct'] if mostrar else None)
    if not demo:
        st.caption('A série oficial registra apenas consultas coletadas. '
                   'O armazenamento do Streamlit gratuito pode ser temporário.')

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
                st.dataframe(dz, hide_index=True, width="stretch")
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
            st.dataframe(tabela,hide_index=True,width="stretch")
            st.download_button('Baixar tabela CSV',tabela.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                file_name='apuracao_por_uf.csv',mime='text/csv')
    else:
        st.info('Sem dados territoriais para detalhar.')
    nomes_municipios, erro_nomes = nomes_municipais_seguros()
    if erro_nomes:
        st.info('Cadastro de municípios do TSE indisponível nesta consulta: '
                'alguns nomes podem aparecer acompanhados do código.')
    exibir_painel_zonas(ROOT, peso, vol, intensidade, demonstracao=demo,
                        estaduais=brutos, nomes_municipios=nomes_municipios)

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
            nomes_municipios, erro_nomes = nomes_municipais_seguros()
            if erro_nomes:
                st.info('Não foi possível consultar o cadastro oficial de nomes dos municípios. '
                        'O código eleitoral será exibido apenas onde faltar o nome.')
            codigos=ordenar_municipios(uf,z.loc[z['uf']==uf,'municipio'].unique(),
                                       nomes_municipios)
            mun=st.selectbox('Município',codigos,
                             format_func=lambda codigo: nome_municipio(uf,codigo,nomes_municipios),
                             key='mun_historico')
            zona=st.selectbox('Zona eleitoral',sorted(z.loc[(z['uf']==uf)&(z['municipio']==mun),'zona'].unique()),key='zona_historico')
            subset=z[(z['uf']==uf)&(z['municipio']==mun)&(z['zona']==zona)].copy()
            subset['Lula (%) válidos']=100*subset['lula']/subset['validos'].replace(0,float('nan'))
            subset['Candidato 22 (%) válidos']=100*subset['direita']/subset['validos'].replace(0,float('nan'))
            st.dataframe(subset[['ano','turno','lula','direita','validos','Lula (%) válidos','Candidato 22 (%) válidos']],
                hide_index=True,width="stretch")
            st.caption('Em 2022, o número 22 corresponde a Jair Bolsonaro; em 2026, a Flávio Bolsonaro. Os percentuais de 2026 usam todos os votos válidos do primeiro turno como denominador.')
        except Exception as e:
            st.error(f'Falha na leitura do histórico territorial: {e}')
    else:
        st.caption('A consulta por zona aparecerá após importar um ZIP histórico ou enviar historico_zonas.csv ao repositório.')
    st.caption('Fonte: https://dadosabertos.tse.jus.br/dataset/resultados-2022 e https://dadosabertos.tse.jus.br/dataset/resultados-2026')


REGIOES_UFS = {
    'Norte': ('AC','AP','AM','PA','RO','RR','TO'),
    'Nordeste': ('AL','BA','CE','MA','PB','PE','PI','RN','SE'),
    'Centro-Oeste': ('DF','GO','MT','MS'),
    'Sudeste': ('ES','MG','RJ','SP'),
    'Sul': ('PR','RS','SC'),
}


def tabela_apuracao_compacta(linhas):
    """Tabela HTML compacta, sem projeções e sem rolagem horizontal."""
    celulas = ''.join(
        '<tr><td>'+escape(str(uf))+'</td><td>'+escape(pct)+'</td>'
        '<td>'+escape(secoes)+'</td><td>'+escape(lula)+'</td>'
        '<td>'+escape(flavio)+'</td><td>'+escape(abst)+'</td></tr>'
        for uf,pct,secoes,lula,flavio,abst in linhas)
    st.markdown("""<style>
    .ufs-compactas{width:100%;overflow:hidden}
    .ufs-compactas table{width:100%;border-collapse:collapse;table-layout:auto;
      font-size:clamp(8px,2.25vw,11px);font-variant-numeric:tabular-nums;line-height:1.1}
    .ufs-compactas th,.ufs-compactas td{padding:4px 2px;text-align:right;
      white-space:nowrap;border-bottom:1px solid #263346}
    .ufs-compactas th:first-child,.ufs-compactas td:first-child{text-align:left;font-weight:700}
    .ufs-compactas th{color:#dce7f5;border-bottom:1px solid #64748b}
    .ufs-compactas .lula{color:#f06a70}
    .ufs-compactas .flavio{color:#36b5eb}
    @media(max-width:400px){.ufs-compactas th,.ufs-compactas td{padding:3px 1px}}
    </style>""",unsafe_allow_html=True)
    st.markdown(
        '<div class="ufs-compactas"><table><thead><tr>'
        '<th>UF</th><th>Urnas</th><th>Seções</th>'
        '<th class="lula">Lula</th><th class="flavio">Flávio</th>'
        '<th>Abst.</th></tr></thead><tbody>'+celulas+
        '</tbody></table></div>',unsafe_allow_html=True)


def formatar_linha_apuracao(nome, d):
    if d is None:
        return (nome, '—', '—', '—', '—', '—')
    secoes, total = int(d['secoes']), int(d['secoes_total'])
    pct = f'{100*secoes/total:.1f}'.replace('.', ',')+'%' if total else '—'
    abst = d.get('abstencoes')
    # A abstenção é exclusivamente a contagem das seções já totalizadas.
    abst_fmt = fmt_int(int(abst)) if abst is not None else '—'
    return (nome, pct, fmt_int(secoes)+'/'+fmt_int(total) if total else '—',
            fmt_int(int(d['lula'])),fmt_int(int(d['flavio'])),abst_fmt)


def painel_estados_compacto():
    """Apuração oficial por UF e por região, com abstenções observadas."""
    st.markdown('#### Apuração por estado e região')
    if modo.startswith('Demonstração'):
        st.info('Selecione **TSE oficial · 2º turno** na barra lateral para ver as parciais reais.')
        return
    if not resultado_disponivel():
        st.info('Aguardando divulgação oficial.')
        return
    dados, erros = obter_tse()
    if not dados:
        st.warning('Nenhuma parcial estadual disponível nesta consulta.')
        return

    # Agregação regional exclusivamente por soma de valores oficiais das UFs.
    # Não agregar campos de eleitorado ausentes como zero.
    linhas_regiao = []
    for nome, ufs in REGIOES_UFS.items():
        blocos = [dados.get(uf) for uf in ufs]
        if any(d is None for d in blocos):
            linhas_regiao.append(formatar_linha_apuracao(nome, None))
            continue
        campos = ('secoes','secoes_total','lula','flavio')
        soma = {c:sum(int(d[c]) for d in blocos) for c in campos}
        absts = [d.get('abstencoes') for d in blocos]
        soma['abstencoes'] = (sum(int(v) for v in absts)
                              if all(v is not None for v in absts) else None)
        linhas_regiao.append(formatar_linha_apuracao(nome,soma))

    st.markdown('**Regiões e respectivos estados**')
    # Cada total regional aparece imediatamente antes das suas UFs.
    # Os totais oficiais são somas de seções/votos, nunca projeções.
    for (nome, ufs), linha_regiao in zip(REGIOES_UFS.items(), linhas_regiao):
        st.markdown('**'+nome+'**')
        tabela_apuracao_compacta([linha_regiao] + [
            formatar_linha_apuracao(uf, dados.get(uf)) for uf in ufs
        ])
    st.markdown('#### Ranking de seções ainda não apuradas')
    st.caption('Estados ordenados do maior para o menor número absoluto de '
               'seções restantes. Apenas dados oficiais por UF.')
    pendentes = []
    ausentes = []
    for uf in sorted(u for u in UFS if u != 'ZZ'):
        d = dados.get(uf)
        if not d or d.get('secoes') is None or d.get('secoes_total') is None:
            ausentes.append(uf)
            continue
        total, apuradas = int(d['secoes_total']), int(d['secoes'])
        if total <= 0 or apuradas < 0 or apuradas > total:
            ausentes.append(uf)
            continue
        faltam = total - apuradas
        pendentes.append((uf, faltam, 100.*faltam/total, apuradas, total))
    pendentes.sort(key=lambda linha: (-linha[1], linha[0]))
    celulas_pendentes = ''.join(
        '<tr><td>'+escape(uf)+'</td>'
        '<td>'+fmt_int(faltam)+'</td>'
        '<td>'+f'{pct:.1f}'.replace('.', ',')+'%</td>'
        '<td>'+fmt_int(apuradas)+'</td>'
        '<td>'+fmt_int(total)+'</td></tr>'
        for uf,faltam,pct,apuradas,total in pendentes)
    st.markdown(
        '<div class="ufs-compactas"><table><thead><tr>'
        '<th>UF</th><th>Faltam</th><th>% falta</th>'
        '<th>Apuradas</th><th>Total</th></tr></thead><tbody>'
        +celulas_pendentes+'</tbody></table></div>',
        unsafe_allow_html=True)
    st.markdown('#### Votos estimados restantes por estado')
    st.caption('Barras horizontais: votos válidos que o modelo estima ainda '
               'faltar apurar. Percentual ao lado: seções restantes oficiais.')
    historico_uf = carregar_historico(
        ROOT/'historico_ufs.csv' if (ROOT/'historico_ufs.csv').exists()
        else ROOT/'data/historico_ufs.csv')
    composicao = (composicao_zonal_uf_somente_quando_conciliada(dados)
                  if testar_correcao_geografica else None)
    previsao_ufs = projetar_locais(dados, historico_uf, peso, vol,
                                  intensidade, composicao_historica=composicao)
    barras = []
    for item in previsao_ufs['linhas']:
        uf = item['UF']
        d = dados.get(uf)
        if not d:
            continue
        total, apuradas = int(d.get('secoes_total',0)), int(d.get('secoes',0))
        if total <= 0 or not 0 <= apuradas <= total:
            continue
        restante = max(0, round(float(item['Votos válidos projetados'])
                                -float(item['Votos válidos apurados'])))
        barras.append((uf,restante,100*(total-apuradas)/total))
    barras.sort(key=lambda x:(-x[1],x[0]))
    if barras:
        maximo = max(1,max(x[1] for x in barras))
        # HTML mantém os 27 estados em altura pequena, ideal para screenshot.
        linhas_barras = ''.join(
            '<div class="faltam-linha"><b>'+escape(uf)+'</b>'
            '<div class="faltam-trilho"><div class="faltam-barra" '
            'style="width:'+f'{100*votos/maximo:.2f}'+'%"></div></div>'
            '<span>'+escape(fmt_int(votos))+'</span>'
            '<em>'+f'{pct:.1f}'.replace('.',',')+'%</em></div>'
            for uf,votos,pct in barras)
        st.markdown("""<style>
        .faltam-linha{display:grid;grid-template-columns:25px minmax(30px,1fr)
            83px 47px;align-items:center;gap:5px;min-height:18px;
            font-size:clamp(9px,2.5vw,11px);font-variant-numeric:tabular-nums}
        .faltam-linha b{font-weight:700}
        .faltam-linha span,.faltam-linha em{text-align:right;font-style:normal}
        .faltam-trilho{height:9px;border-radius:3px;background:#263346;overflow:hidden}
        .faltam-barra{height:100%;background:#70b6e9}
        </style>""",unsafe_allow_html=True)
        st.markdown('<div class="faltam-linha"><b>UF</b><b>Votos restantes</b>'
                    '<b style="text-align:right">Votos</b>'
                    '<b style="text-align:right">% urnas</b></div>'
                    +linhas_barras,unsafe_allow_html=True)
        st.caption('Votos restantes = votos válidos finais estimados pelo '
                   'modelo por UF menos votos válidos já apurados. '
                   'Estimativa experimental, não dado oficial. '
                   'A porcentagem de urnas restantes é oficial '
                   '(seções não totalizadas / seções totais). '
                   'Ordenação: maior volume estimado de votos restantes.')
    else:
        st.info('Sem histórico ou dados estaduais suficientes para estimar '
                'os votos restantes.')
    st.markdown('#### Destino estimado dos votos restantes')
    st.caption('Vermelho: Lula · Azul: Flávio. Barras representam a divisão '
               'dos votos válidos ainda não apurados, segundo o modelo.')
    destinos = []
    for item in previsao_ufs['linhas']:
        uf = item['UF']
        if uf == 'ZZ' or uf not in dados:
            continue
        d = dados[uf]
        total_s = int(d.get('secoes_total',0))
        apuradas_s = int(d.get('secoes',0))
        if total_s <= 0 or not 0 <= apuradas_s <= total_s:
            continue
        lula_rest = max(0.,float(item['Lula projetado'])-float(item['Lula apurado']))
        flavio_rest = max(0.,float(item['Flávio projetado'])-float(item['Flávio apurado']))
        validos_rest = lula_rest+flavio_rest
        if validos_rest <= 0 and apuradas_s < total_s:
            continue
        # Estimativa separada de abstenções: extrapolação da taxa observada
        # entre eleitores das seções totalizadas para o eleitorado pendente.
        # Não tratar abstenção como voto válido.
        aptos = d.get('aptos')
        processados = d.get('aptos_processados')
        comparecimento = d.get('comparecimento')
        abst_obs = d.get('abstencoes')
        abst_rest = None
        taxa_abst = None
        if (aptos is not None and processados is not None and
            comparecimento is not None and abst_obs is not None):
            aptos, processados = int(aptos), int(processados)
            comparecimento, abst_obs = int(comparecimento), int(abst_obs)
            base = comparecimento+abst_obs
            if base > 0 and aptos >= processados >= 0:
                taxa_abst = abst_obs/base
                abst_rest = round((aptos-processados)*taxa_abst)
        destinos.append((uf,lula_rest,flavio_rest,validos_rest,
                         taxa_abst,abst_rest))
    destinos.sort(key=lambda x:(-x[3],x[0]))
    if destinos:
        linhas_destino = []
        for uf,lula_rest,flavio_rest,validos_rest,taxa_abst,abst_rest in destinos:
            lula_pct = 100*lula_rest/validos_rest if validos_rest else 0
            flavio_pct = 100*flavio_rest/validos_rest if validos_rest else 0
            abst_texto = ('~'+fmt_int(abst_rest) if abst_rest is not None else '—')
            linhas_destino.append(
                '<div class="destino-linha"><b>'+escape(uf)+'</b>'
                '<div class="destino-trilho">'
                '<div class="destino-lula" style="width:'+f'{lula_pct:.2f}'+'%"></div>'
                '<div class="destino-flavio" style="width:'+f'{flavio_pct:.2f}'+'%"></div>'
                '</div><span>'+f'{lula_pct:.1f}'.replace('.',',')+'% / '
                +f'{flavio_pct:.1f}'.replace('.',',')+'%</span>'
                '<em>'+escape(abst_texto)+'</em></div>')
        st.markdown("""<style>
        .destino-linha{display:grid;grid-template-columns:25px minmax(50px,1fr)
            99px 76px;align-items:center;gap:4px;min-height:18px;
            font-size:clamp(9px,2.35vw,11px);font-variant-numeric:tabular-nums}
        .destino-linha span,.destino-linha em{text-align:right;font-style:normal}
        .destino-trilho{display:flex;height:10px;overflow:hidden;
            border-radius:3px;background:#263346}
        .destino-lula{background:#f06a70;height:100%}
        .destino-flavio{background:#36b5eb;height:100%}
        </style>""",unsafe_allow_html=True)
        st.markdown('<div class="destino-linha"><b>UF</b><b>Válidos restantes</b>'
                    '<b style="text-align:right">L / F</b>'
                    '<b style="text-align:right">Abst. est.</b></div>'
                    +''.join(linhas_destino),unsafe_allow_html=True)
        soma_l = sum(x[1] for x in destinos)
        soma_f = sum(x[2] for x in destinos)
        soma_v = soma_l+soma_f
        absts = [x[5] for x in destinos]
        abst_completa = len(destinos)==27 and all(x is not None for x in absts)
        st.markdown('**Consolidado dos votos válidos restantes · 27 UFs**'
                    if len(destinos)==27 else
                    '**Consolidado parcial dos votos válidos restantes · '
                    +str(len(destinos))+' UFs**')
        if soma_v > 0:
            st.markdown(
                '<div class="destino-trilho" style="height:19px">'
                '<div class="destino-lula" style="width:'
                +f'{100*soma_l/soma_v:.2f}'+'%"></div>'
                '<div class="destino-flavio" style="width:'
                +f'{100*soma_f/soma_v:.2f}'+'%"></div></div>',
                unsafe_allow_html=True)
            st.markdown(
                '🔴 **Lula:** '+fmt_int(round(soma_l))+' votos · '+
                f'{100*soma_l/soma_v:.2f}'.replace('.',',')+'% dos válidos restantes'
                '  |  🔵 **Flávio:** '+fmt_int(round(soma_f))+' votos · '+
                f'{100*soma_f/soma_v:.2f}'.replace('.',',')+'% dos válidos restantes')
            st.caption('Total de votos válidos restantes estimados: '+
                       fmt_int(round(soma_v))+'. Abstenções adicionais estimadas: '+
                       (fmt_int(sum(absts)) if abst_completa else
                        'N/D (cobertura incompleta)')+'.')
        st.caption('A proporção Lula/Flávio é calculada sobre os votos válidos '
                   'restantes, não sobre o eleitorado. Abst. est. é uma '
                   'extrapolação da taxa de ausência já observada ao eleitorado '
                   'não totalizado, apresentada separadamente. Brancos e nulos '
                   'não estão incluídos. Todas as projeções são experimentais.')
    else:
        st.info('Sem dados suficientes para distribuir os votos restantes.')

    if ausentes:
        st.caption('Sem dados válidos para o ranking: '+', '.join(ausentes)+'.')
    st.caption('Critério: seções restantes = total de seções − seções '
               'totalizadas. Não confundir com votos ainda não apurados.')

    st.caption('Urnas = % de seções totalizadas; Seções = apuradas/total. '
               'Lula e Flávio = votos oficiais; Abst. = eleitores ausentes '
               'nas seções totalizadas (quantidade, não taxa). '
               'Regiões = soma das UFs; valores ausentes aparecem como —. '
               'Exterior (ZZ) excluído. Horários estaduais podem diferir.')
    st.caption('Referência de atualização nacional: '+
               str(dados.get('BR',{}).get('geracao','não informada')))


aba1,aba2,aba3,aba4=st.tabs(['📈 Painel','🗺️ Estados','🧭 Zonas','🗂️ Históricos'])
with aba1:
    painel()
with aba2:
    painel_estados_compacto()
with aba3:
    nomes_municipios, erro_nomes = nomes_municipais_seguros()
    if erro_nomes:
        st.info('Cadastro municipal não carregado nesta sessão; '
                'os códigos TSE serão exibidos apenas onde o nome estiver ausente.')
    exibir_modelo_zonal_completo(ROOT, nomes=nomes_municipios,
                                peso_2026=peso,ajuste_volume=vol,
                                intensidade=intensidade)
with aba4:
    historicos()
st.divider()
def commit_publicado():
    # Mostra a versão realmente executada para comparar com o manifesto
    # release-candidate.json. Não depende de senha/token nem faz requests.
    sha=os.environ.get('STREAMLIT_GIT_COMMIT_SHA') or os.environ.get('GITHUB_SHA')
    if not sha:
        try:
            sha=subprocess.check_output(['git','rev-parse','HEAD'],
                                        cwd=ROOT,text=True,
                                        stderr=subprocess.DEVNULL,
                                        timeout=3).strip()
        except (OSError,subprocess.SubprocessError):
            sha=None
    return sha[:12] if sha else 'não identificado'


st.caption('Election Lab 2026 · commit '+commit_publicado()
           +' · Projeto independente. Resultado apurado = fonte TSE; '
           'projeções = estimativas experimentais, não oficiais.')
