"""Interface do modelo completo por zona, município, UF e Brasil.

Mostra uma PRÉVIA histórica antes de receber o EA20 de 25/10.
Exige catálogo oficial de 6258 para rotular as observações como segunda rodada.
Snapshot pode vir do coletor local ou de upload realizado pelo operador.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import streamlit as st

from modelo_zonas import carregar_zonas
from coletor_zonal import coletar
from tse import resultado_disponivel
from motor_zonal_completo import executar, ler_snapshot
from municipios_tse import nome_municipio


@st.cache_data(show_spinner=False)
def _base_historica(caminho, mtime):
    return carregar_zonas(caminho)


@st.cache_data(show_spinner=False)
def _executar_snapshot(serializado, caminho, mtime, nomes):
    snap=json.loads(serializado)
    hist=_base_historica(caminho,mtime)
    oficial = snap.get('catalogo_origem')=='EA16_TSE_3221'
    return executar(snap,hist,nomes=nomes,exigir_catalogo_nacional=oficial)


def _preview_historica(hist):
    catalogo=[]
    for (uf,municipio,zona),anos in sorted(hist.items()):
        if (2026,1) in anos:
            catalogo.append({'uf':uf,'municipio':municipio,'zona':zona})
    return {'versao':1,'eleicao':6258,
            'catalogo_origem':'historico_2026T1_PREVIA',
            'catalogo':catalogo,'observacoes':{}}


def _formatar_numero(x):
    return f'{float(x):,.0f}'.replace(',','.')


def exibir_modelo_zonal_completo(root,nomes=None):
    st.subheader('Apuração e projeção por zona eleitoral')
    st.caption('Cada combinação município/zona é uma unidade do modelo. '
               'O motor soma observações oficiais e votos ainda estimados e '
               'agrega as zonas por município, UF e Brasil.')
    root=Path(root)
    caminho=root/'historico_zonas.csv'
    if not caminho.is_file():
        caminho=root/'data/historico_zonas.csv'
    if not caminho.is_file():
        st.error('Histórico por zonas não encontrado.')
        return
    base=_base_historica(str(caminho),caminho.stat().st_mtime_ns)
    recebido=st.file_uploader('Carregar snapshot oficial EA20 por zona (JSON)',
                             type=['json'],key='upload_snapshot_zonas')
    origem='Prévia histórica'
    if recebido is not None:
        try:
            snap=json.loads(recebido.getvalue().decode('utf-8'))
        except (UnicodeError,ValueError) as exc:
            st.error(f'Snapshot inválido: {exc}')
            return
        origem='Arquivo enviado'
    elif (root/'dados_zonais_6258.json').is_file():
        try:
            snap=ler_snapshot(root/'dados_zonais_6258.json')
        except (OSError,ValueError) as exc:
            st.error(f'Falha ao abrir o coletor zonal: {exc}')
            return
        origem='Coleta oficial salva'
    else:
        snap=_preview_historica(base)

    oficial = snap.get('catalogo_origem')=='EA12_TSE_6258'
    if not oficial:
        st.warning('PRÉVIA COM HISTÓRICO APENAS: nenhum voto do 2º turno foi consultado. '
                   'O catálogo de 2026T1 não prova a cobertura oficial de 2026T2. '
                   'Todos os números de projeção desta tela são experimentais.')
    else:
        st.info('Snapshot oficial EA16/EA20. Os arquivos zonais podem representar '
                'momentos distintos, por isso a projeção é experimental e '
                'não substitui o resultado oficial BR/UF.')
    try:
        resultado=executar(snap,base,nomes=nomes or {},
                          exigir_catalogo_nacional=oficial)
    except (ValueError,KeyError,TypeError) as exc:
        st.error('Projeção territorial bloqueada: '+str(exc))
        return
    br=resultado['brasil']
    st.caption('Origem: '+origem+' · Catálogo: '+str(br['zonas_total'])
               +' zonas · '+str(br['zonas_desatualizadas'])+' observações desatualizadas')
    a,b,c,d=st.columns(4)
    a.metric('Zonas cadastradas',_formatar_numero(br['zonas_total']))
    b.metric('Com observação recente',_formatar_numero(br['zonas_consultadas']))
    c.metric('Zonas totalmente apuradas',_formatar_numero(br['zonas_concluidas']))
    d.metric('Cobertura de consultas',f"{br['cobertura_zonas_pct']:.1f}%".replace('.',','))
    if br['zonas_consultadas'] == 0:
        st.warning('Ainda não existem votos atuais no snapshot. '
                   'Exibindo apenas a estimativa inicial histórica.')
    elif br['cobertura_zonas_pct'] < 80:
        st.warning('Cobertura zonal incompleta. O valor estimado para as demais '
                   'localidades ainda depende predominantemente do histórico.')
    if oficial and len({r['uf'] for r in snap.get('catalogo',[])})!=28:
        st.error('Cadastro oficial incompleto; não publicar projeção nacional.')
        return

    # A previsão nacional é apresentada como resultado de um modelo, nunca
    # como parcial TSE ou como probabilidade calibrada de vitória.
    st.markdown('#### Soma das estimativas zonais')
    ca,cb=st.columns(2)
    ca.metric('Lula · votos finais estimados',_formatar_numero(br['lula_estimado']))
    cb.metric('Flávio · votos finais estimados',_formatar_numero(br['flavio_estimado']))
    st.caption('Valores exclusivamente modelados. A parcial nacional oficial deve '
               'ser consultada separadamente na aba Painel.')

    # Somente uma UF por vez para não abrir milhares de linhas no celular.
    ufs=sorted(resultado['ufs'])
    if not ufs:
        st.warning('Sem localidades calculadas.')
        return
    escolhida=st.selectbox('UF',ufs,index=ufs.index('SP') if 'SP' in ufs else 0,
                           key='uf_zonal_completo')
    if resultado_disponivel():
        if st.button('Consultar até 100 zonas oficiais desta UF agora',
                     disabled=recebido is not None,key='coletar_uf_todas_zonas'):
            try:
                with st.spinner('Coletando zonas com limite de 12 consultas/segundo...'):
                    resumo=coletar(root/'dados_zonais_6258.json',
                                  uf=escolhida,limite=100,taxa=12.,concorrencia=8)
                st.success(str(resumo['atualizadas'])+' zonas atualizadas. '
                           'Total de snapshots: '+str(resumo['zonas_com_snapshot']))
                if resumo['interrompido']:
                    st.error('Coleta interrompida por bloqueio/URL inválida; '
                             'não continuar até verificar o TSE.')
                else:
                    st.rerun()
            except Exception as exc:
                st.error(f'Consulta zonal interrompida: {type(exc).__name__}: {str(exc)[:220]}')
    else:
        st.caption('Coleta oficial de zonas desativada antes de 25/10/2026 às 17h.')
    dados_uf=resultado['ufs'][escolhida]
    st.caption(
        'UF: '+str(dados_uf['zonas_consultadas'])+' / '+str(dados_uf['zonas_total'])
        +' município/zonas consultados; '+
        str(dados_uf['zonas_concluidas'])+' concluídos.')
    mun_codigos=sorted({r['municipio'] for r in resultado['linhas'] if r['uf']==escolhida},
                      key=lambda cd: nome_municipio(escolhida,cd,nomes or {}).casefold())
    opcao=st.selectbox('Município', ['TODOS']+mun_codigos,
                      format_func=lambda cd: ('Todos os municípios' if cd=='TODOS'
                                              else nome_municipio(escolhida,cd,nomes or {})),
                      key='municipio_zonal_completo')
    linhas=[r for r in resultado['linhas'] if r['uf']==escolhida
            and (opcao=='TODOS' or r['municipio']==opcao)]
    colunas={
        'nome_municipio':'Município','zona':'Zona',
        'status':'Situação','secoes':'Seções apuradas',
        'secoes_total':'Seções totais (consultadas)',
        'validos_apurados':'Votos válidos apurados',
        'lula_apurado':'Lula apurado','flavio_apurado':'Flávio apurado',
        'lula_restante_estimado':'Lula restante estimado',
        'flavio_restante_estimado':'Flávio restante estimado',
        'lula_projetado':'Lula final estimado',
        'flavio_projetado':'Flávio final estimado',
        'lula_projetado_pct':'Lula (%) estimado',
        'historico_disponivel':'Histórico disponível',
    }
    quadro=pd.DataFrame([{nome:r.get(c) for c,nome in colunas.items()} for r in linhas])
    if not quadro.empty:
        quadro=quadro.sort_values(['Município','Zona'])
        st.dataframe(quadro,hide_index=True,use_container_width=True,height=420)
        st.download_button('Exportar detalhamento zonal (CSV)',
                           quadro.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                           file_name=f'election_lab_zonas_{escolhida}.csv',
                           mime='text/csv',key='baixar_projecoes_zonas')

    tab_uf=pd.DataFrame([{'UF':uf,**v} for uf,v in sorted(resultado['ufs'].items())])
    with st.expander('Consolidação das 28 localidades'):
        st.dataframe(tab_uf,hide_index=True,use_container_width=True)
        st.download_button('Exportar consolidação por UF (CSV)',
                           tab_uf.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                           file_name='election_lab_ufs_derivadas_de_zonas.csv',
                           mime='text/csv',key='baixar_consolidacao_zonas')
    st.caption('Operação do coletor: python coletor_zonal.py --uf SP --limite 300 '
               'ou python coletor_zonal.py --todas --limite 10000. '
               'Ele somente consulta o 2º turno após o início oficial da divulgação.')
