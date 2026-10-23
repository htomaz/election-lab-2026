"""Painel experimental por zona: EA20 oficial em amostra pequena, com histórico.

Nunca substitui resultados nacionais/UF por somatório de uma amostra consultada.
A atualização ocorre apenas enquanto a sessão Streamlit estiver ativa.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time
import pandas as pd
import streamlit as st

from auditoria_ao_vivo import reconciliar_zonas, validar_substituicao
from modelo_zonas import carregar_zonas, projetar_zonas
from municipios_tse import nome_municipio
from tse import UFS, baixar_zona, resultado_disponivel

AMOSTRA_MAX = 48
POR_RODADA = 8
VALIDADE_SEGUNDOS = 720


@st.cache_data(show_spinner=False)
def _historico(caminho, mtime):
    return carregar_zonas(caminho)


def exibir_painel_zonas(root, peso, volume, intensidade, demonstracao=False,
                       estaduais=None, nomes_municipios=None):
    st.markdown('### Monitor territorial por zona · experimental')
    st.caption('EA20 por zona, histórico TSE de 2022/2026 e projeção local. '
               'A cobertura por zonas consultadas NÃO equivale ao percentual de seções totalizadas.')
    arquivo=Path(root)/'historico_zonas.csv'
    if not arquivo.exists(): arquivo=Path(root)/'data/historico_zonas.csv'
    if not arquivo.exists():
        st.warning('Histórico por zona não encontrado.')
        return
    try:
        historico=_historico(str(arquivo),arquivo.stat().st_mtime_ns)
    except (OSError, ValueError) as exc:
        st.error(f'Erro no histórico de zonas: {exc}')
        return
    ufs=sorted(UFS)
    selecionada=st.selectbox('UF para acompanhamento zonal',ufs,
                            index=ufs.index('SP'),key='uf_monitor_zonal')
    # A lista de 2026T1 determina a população geográfica de comparação.
    universo={k for k,v in historico.items() if k[0]==selecionada and (2026,1) in v}
    if not universo:
        st.warning('Nenhuma zona cadastrada para essa UF.')
        return
    amostra=sorted(universo,
                   key=lambda k:historico[k][(2026,1)]['validos'],reverse=True)[:AMOSTRA_MAX]
    votos_amostra=sum(historico[k][(2026,1)]['validos'] for k in amostra)
    votos_uf=sum(historico[k][(2026,1)]['validos'] for k in universo)
    st.caption(f'Amostra intencional das {len(amostra)} maiores combinações município/zona de {len(universo)} '
               f'(participação no volume histórico de votos válidos da UF: '
               f'{100*votos_amostra/max(1,votos_uf):.1f}%). '
               'Não é uma amostra aleatória nem cobre toda a UF.')

    if 'snapshots_zonais' not in st.session_state:
        st.session_state['snapshots_zonais']={}
    if 'cursor_zonal' not in st.session_state:
        st.session_state['cursor_zonal']={}
    snapshots=st.session_state['snapshots_zonais']
    cursores=st.session_state['cursor_zonal']
    suspendidos=st.session_state.setdefault('suspensao_zonal',set())
    habilitar=st.toggle('Ativar consultas oficiais da amostra zonal',value=False,
                        key='coleta_zonal_habilitada',disabled=demonstracao or not resultado_disponivel())
    ativos=bool(habilitar and not demonstracao and resultado_disponivel())

    if ativos and selecionada not in suspendidos:
        cursor=cursores.get(selecionada,0)
        lote=[amostra[(cursor+i)%len(amostra)] for i in range(min(POR_RODADA,len(amostra)))]
        cursores[selecionada]=(cursor+len(lote))%len(amostra)
        with ThreadPoolExecutor(max_workers=3) as ex:
            futuros={ex.submit(baixar_zona,*k):k for k in lote}
            erros=[]
            for futuro in as_completed(futuros):
                key=futuros[futuro]
                try:
                    dados,erro=futuro.result()
                except Exception as exc:
                    dados,erro=None,str(exc)[:120]
                if erro:
                    erros.append(erro)
                    if '404' in erro or '403' in erro or '429' in erro:
                        suspendidos.add(selecionada)
                elif dados:
                    anterior=snapshots.get(key,{}).get('dados')
                    aceitar,motivo=validar_substituicao(anterior,dados)
                    if aceitar and int(dados.get('secoes_total',0))>0:
                        snapshots[key]={'capturado':time.time(),'dados':dados}
                    elif not aceitar:
                        erros.append(motivo)
        if erros:
            st.warning('Algumas zonas não puderam ser consultadas: '
                       + '; '.join(sorted(set(erros))[:2]))
    elif ativos:
        st.warning('Consulta zonal automática suspensa após erro HTTP. '
                   'Verifique a configuração do TSE antes de reativar.')
        if st.button('Reativar uma tentativa de coleta zonal'):
            suspendidos.discard(selecionada)
            st.rerun()

    agora=time.time()
    observadas={}
    for k,item in snapshots.items():
        if k[0]!=selecionada or k not in universo:
            continue
        if agora-item['capturado']>VALIDADE_SEGUNDOS:
            continue
        observadas[k]=item['dados']
    if not resultado_disponivel():
        st.info('A coleta oficial por zona começará somente com a apuração '
                'de 25/10/2026, a partir das 17h (Brasília).')
    elif not habilitar:
        st.info('Consultas zonais desativadas nesta sessão. Ative acima para '
                'acompanhamento sob demanda, respeitando a limitação do TSE.')
    elif not observadas:
        st.info('Nenhuma parcial zonal válida coletada ainda; a estimativa a seguir '
                'utiliza apenas o histórico.')

    # A amostra deve respeitar o teto estadual na mesma geração dos dados.
    # Como o cadastro histórico não confirma o universo oficial do 2º turno,
    # jamais marcar esta amostra como conciliação integral.
    diagnostico=reconciliar_zonas(observadas,(estaduais or {}).get(selecionada))
    if ativos:
        st.caption('Conciliação com a parcial estadual: '+diagnostico['mensagem'])
        if diagnostico['status']=='inconsistente':
            st.error('Parciais zonais e estadual inconsistentes; projeção zonal suspensa.')
            st.json(diagnostico['diferencas'])
            return
        if observadas and diagnostico['status']!='parcial_compativel':
            st.warning('Não há snapshot estadual comparável: projeção zonal suspensa, '
                       'mantendo apenas as parciais oficiais por UF.')
            return

    # Projeção histórica da UF inteira; zona desconhecida NÃO equivale a zero apurado.
    modelo=projetar_zonas(observadas,{k:v for k,v in historico.items() if k[0]==selecionada},
                          peso_2026=peso,ajuste_volume=volume,intensidade=intensidade,
                          universo=universo)
    parcial=modelo['por_uf'].get(selecionada)
    if not parcial:return
    obs_validos=sum(x['validos'] for x in observadas.values())
    cobertura=100*len(observadas)/len(universo)
    a,b,c=st.columns(3)
    a.metric('Município/zonas consultados',f'{len(observadas)} / {len(universo)}')
    b.metric('Votos válidos nas consultas',f'{obs_validos:,}'.replace(',','.'))
    proporcao=100*parcial['lula']/max(1.,parcial['lula']+parcial['flavio'])
    c.metric('Lula · projeção zonal da UF',f'{proporcao:.2f}%'.replace('.',','))
    if cobertura < 80:
        st.warning(f'Cobertura territorial de consultas: {cobertura:.1f}% das combinações município/zona. '
                   'A projeção zonal é preliminar, dominada pelo histórico, '
                   'e NÃO deve substituir a projeção oficial/estadual.')
    else:
        st.caption('Mesmo com ampla cobertura de consultas, arquivos coletados '
                   'em instantes distintos podem não reconciliar com o total estadual.')
    tab=pd.DataFrame([r for r in modelo['linhas']
                      if (r['uf'],r['municipio'],r['zona']) in amostra])
    if not tab.empty:
        tab=tab[['municipio','zona','secoes','secoes_total','lula_apurado',
                 'flavio_apurado','validos_apurados','lula_historico_pct',
                 'lula_projetado_pct','validos_projetados']]
        tab.insert(0,'Município',
                   tab['municipio'].map(lambda codigo:
                       nome_municipio(selecionada,codigo,nomes_municipios or {})))
        tab=tab.rename(columns={'municipio':'Código TSE','zona':'Zona eleitoral'})
        tab=tab.sort_values(['Município','Zona eleitoral'],kind='stable')
        apresentacao=tab.drop(columns=['Código TSE'])
        st.dataframe(apresentacao,hide_index=True,use_container_width=True)
        st.download_button('Exportar tabela zonal (CSV)',
                           tab.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                           file_name=f'zonas_{selecionada.lower()}_election_lab.csv',
                           mime='text/csv',key='baixar_zonas_monitor')
    st.caption('As consultas cobrem apenas as maiores zonas selecionadas, com até '
               f'{POR_RODADA} requisições por atualização do painel; cache válido por '
               f'{VALIDADE_SEGUNDOS//60} minutos. Dados e projeções não auditados '
               'contra a totalização estadual enquanto a cobertura for incompleta.')
