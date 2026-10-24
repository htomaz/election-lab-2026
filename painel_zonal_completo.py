"""Interface do modelo completo por zona, município, UF e Brasil.

Mostra uma PRÉVIA histórica antes de receber o EA20 de 25/10.
Exige catálogo oficial de 6258 para rotular as observações como segunda rodada.
Snapshot pode vir do coletor local ou de upload realizado pelo operador.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import pandas as pd
import streamlit as st

from modelo_zonas import carregar_zonas
from importar_participacao import carregar_participacao
from coletor_zonal import coletar
from tse import resultado_disponivel, coletar as coletar_totalizacoes
from auditoria_snapshot_zonal import auditar_parciais
from motor_zonal_completo import executar, ler_snapshot
from municipios_tse import nome_municipio
from sensibilidade_zonal import faixa_sensibilidade
from proveniencia_tse import auditar_amostra
from backup_actions import recuperar as recuperar_actions
from tse import baixar_zona


@st.cache_data(show_spinner=False)
def _base_historica(caminho, mtime):
    return carregar_zonas(caminho)


@st.cache_data(show_spinner=False)
def _participacao_historica(caminho, mtime):
    return carregar_participacao(caminho)


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


def exibir_modelo_zonal_completo(root,nomes=None,peso_2026=.75,
                                ajuste_volume=1.,intensidade=.35):
    st.subheader('Apuração e projeção por zona eleitoral')
    st.caption('Parâmetros do modelo: histórico 2026 '+f'{peso_2026:.0%}'
               +' · intensidade de atualização '+f'{intensidade:.2f}'
               +' · fator de volume '+f'{ajuste_volume:.2f}'
               +'. Ajustáveis na barra lateral.')
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
    arquivo_p=root/'historico_participacao_zonas.csv'
    if arquivo_p.is_file():
        try:
            historico_participacao=_participacao_historica(
                str(arquivo_p),arquivo_p.stat().st_mtime_ns)
        except (OSError,ValueError) as exc:
            st.error(f'Histórico de comparecimento inválido: {exc}')
            return
    else:
        historico_participacao=None
        st.info('Ainda não foi importado o histórico por zona de abstenção, '
                'comparecimento, brancos e nulos. O modelo preserva o método '
                'anterior de volume de votos, sem estimar essas parcelas individualmente. '
                'Importe os arquivos oficiais detalhe_votacao_munzona de 2022 e 2026.')
    local_snapshot=root/'dados_zonais_6258.json'
    with st.expander('Backup e recuperação de snapshots zonais'):
        if local_snapshot.is_file():
            tamanho=local_snapshot.stat().st_size
            if tamanho<=25*1024*1024:
                st.download_button('Baixar snapshot local (JSON)',
                                   local_snapshot.read_bytes(),
                                   file_name='dados_zonais_6258.json',
                                   mime='application/json',key='baixar_json_zonal')
            else:
                st.warning('Snapshot local acima de 25 MB. Use backup do coletor.')
        token=os.environ.get('GITHUB_SNAPSHOT_TOKEN','')
        if not token:
            try:
                token=str(st.secrets.get('GITHUB_SNAPSHOT_TOKEN',''))
            except (FileNotFoundError,KeyError):
                token=''
        if token:
            if st.button('Recuperar último artifact validado do GitHub',
                         key='recuperar_backup_zonal'):
                try:
                    with st.spinner('Verificando SHA-256 e conciliando os arquivos...'):
                        resultado_backup=recuperar_actions(local_snapshot,token=token)
                    if resultado_backup['restaurado']:
                        st.success('Snapshot recuperado: '
                                   +str(resultado_backup['zonas_com_votos'])
                                   +' zonas com observações preservadas.')
                        st.rerun()
                    else:
                        st.info('Nenhum backup verificável encontrado.')
                except (ValueError,OSError,KeyError) as exc:
                    st.error('Backup rejeitado: '+str(exc))
        else:
            st.caption('Restauração automática requer GITHUB_SNAPSHOT_TOKEN '
                       'somente leitura em Settings > Secrets do Streamlit. '
                       'Sem token, baixe o artifact no GitHub Actions e '
                       'carregue o JSON abaixo.')
    recebido=st.file_uploader('Carregar snapshot oficial EA20 por zona (JSON)',
                             type=['json'],key='upload_snapshot_zonas')
    origem='Prévia histórica'
    if recebido is not None:
        if recebido.size>25*1024*1024:
            st.error('Snapshot acima de 25 MB: tamanho não permitido no painel.')
            return
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

    oficial = snap.get('catalogo_origem')=='EA16_TSE_3221'
    if recebido is not None:
        st.warning('Arquivo fornecido pelo operador. Metadados no JSON não '
                   'autenticam a origem do TSE nem a assinatura digital '
                   'do arquivo; conferir proveniência e integridade.')
    if not oficial:
        st.warning('PRÉVIA COM HISTÓRICO APENAS: nenhum voto do 2º turno foi consultado. '
                   'O catálogo de 2026T1 não prova a cobertura oficial de 2026T2. '
                   'Todos os números de projeção desta tela são experimentais.')
    else:
        st.info('Snapshot com metadados EA16/EA20 do pleito 3221. '
                'A presença desses metadados não autentica o JSON, '
                'especialmente se foi enviado por upload. As zonas podem '
                'representar gerações distintas; a projeção é experimental '
                'e não substitui o resultado oficial BR/UF.')
    try:
        resultado=executar(snap,base,nomes=nomes or {},
                          exigir_catalogo_nacional=False,
                          participacao=historico_participacao,
                          peso_2026=peso_2026,ajuste_volume=ajuste_volume,
                          intensidade=intensidade)
    except (ValueError,KeyError,TypeError) as exc:
        st.error('Projeção territorial bloqueada: '+str(exc))
        return
    br=resultado['brasil']
    st.caption('Origem: '+origem+' · Catálogo: '+str(br['zonas_total'])
               +' zonas · '+str(br['zonas_desatualizadas'])+' observações desatualizadas')
    st.caption('Sobreposição do cadastro com 2026T1: '
               f'{br["cobertura_catalogo_vs_2026t1_pct"]:.1f}%'
               '. É diagnóstico de cobertura, não autenticação da fonte.')
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
    hash_snapshot=hashlib.sha256(json.dumps(
        snap,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    if oficial and resultado_disponivel() and snap.get('observacoes'):
        with st.expander('Conferir proveniência de uma amostra EA20 no TSE'):
            st.caption('Verifica até cinco zonas consultando diretamente a '
                       'CDN oficial. Uma amostra não autentica todos os '
                       'resultados, e SHA-256 não substitui assinatura JWS.')
            if st.button('Confrontar 5 zonas com a fonte oficial',
                         key='checar_proveniencia_amostra'):
                with st.spinner('Conferindo origem, geração, contagens e hash...'):
                    prova=auditar_amostra(snap,baixar_zona,max_zonas=5)
                st.session_state['proveniencia_zonal_ultima']={
                    'hash_snapshot':hash_snapshot,'resultado':prova}
            atual=st.session_state.get('proveniencia_zonal_ultima')
            if atual and atual.get('hash_snapshot')==hash_snapshot:
                prova=atual['resultado']
                st.write(f"Zonas reconsultadas: {prova['consultadas']} · "
                         f"Coincidentes: {prova['confirmadas']} · "
                         f"Divergentes: {prova['divergentes']} · "
                         f"Novas gerações: {prova['atualizadas']} · "
                         f"Inconclusivas: {prova['inconclusivas']}")
                st.dataframe(pd.DataFrame(prova['detalhes']),
                             hide_index=True,use_container_width=True)
                if prova['divergentes']:
                    st.error('A fonte reconsultada diverge do snapshot. '
                             'Não interpretar esse arquivo como autenticado.')
                st.caption(prova['nota'])
    auditoria_anterior=st.session_state.get('auditoria_zonal_ultima')
    auditoria_bloqueou=bool(
        auditoria_anterior and
        auditoria_anterior.get('hash_snapshot')==hash_snapshot and
        auditoria_anterior.get('bloqueantes'))
    if oficial and resultado_disponivel():
        with st.expander('Conciliação independente com EA20 das UFs e Brasil'):
            st.caption('Consulta manual adicional ao TSE (29 agregados). '
                       'Os horários podem não ser síncronos; dados incompatíveis '
                       'suspendem a projeção desta leitura.')
            if st.button('Auditar agora a coleta por zonas vs UF/BR',
                         key='auditar_tse_zonas_ufs'):
                try:
                    with st.spinner('Consultando resultados estaduais e nacional...'):
                        totais,erros=coletar_totalizacoes()
                    if 'BR' not in totais:
                        st.error('Arquivo oficial BR indisponível; '
                                 'não é possível concluir auditoria.')
                    else:
                        audit=auditar_parciais(snap,totais)
                        st.session_state['auditoria_zonal_ultima']={
                            'hash_snapshot':hash_snapshot,
                            'bloqueantes':audit['bloqueantes'],
                            'nacional':audit['nacional']['status']
                        }
                        st.write('Brasil: '+audit['nacional']['status'])
                        st.dataframe(pd.DataFrame(audit['por_uf']),
                                     hide_index=True,use_container_width=True)
                        if audit['bloqueantes']:
                            auditoria_bloqueou=True
                            st.error('Divergências impeditivas em: '+
                                     ', '.join(audit['bloqueantes']))
                        else:
                            st.info('Nenhuma divergência impeditiva detectada '
                                    'nas consultas recebidas. Isso não implica '
                                    'sincronismo nem autenticação criptográfica.')
                        if erros:
                            st.caption('Erros/ausências da coleta agregada: '+
                                       str(erros)[:250])
                except (ValueError,TypeError,KeyError) as exc:
                    st.error('Falha na conciliação: '+str(exc))
    nacional_habilitado=bool((not oficial or br['catalogo_oficial_nacional'])
                            and not auditoria_bloqueou)
    if auditoria_bloqueou:
        st.error('Projeções agregadas suspensas nesta versão do snapshot: '
                 'auditoria EA20 apontou divergências entre zonas e UF/BR. '
                 'Consulte o diagnóstico e atualize os dados.')
    if oficial and not nacional_habilitado and not auditoria_bloqueou:
        st.warning('Cadastro EA16 parcial: os números abaixo representam ' 
                   'somente as localidades cadastradas, não todo o Brasil.')

    if auditoria_bloqueou:
        st.caption('Exibindo somente votos observados para diagnóstico; '
                   'todas as previsões estão suspensas neste snapshot.')
        brutos=pd.DataFrame([
            {'UF':r['uf'],'Município':r['nome_municipio'],
             'Zona':r['zona'],'Situação':r['status'],
             'Lula apurado':r['lula_apurado'],
             'Flávio apurado':r['flavio_apurado'],
             'Votos válidos':r['validos_apurados']}
            for r in resultado['linhas'] if r['validos_apurados']>0])
        if not brutos.empty:
            st.dataframe(brutos,hide_index=True,use_container_width=True)
        return
    if historico_participacao is not None:
        proporcao=br['cobertura_modelo_participacao_pct']
        st.caption(f'Cobertura do estimador comparecimento/brancos/nulos: '
                   f'{br["zonas_modeladas_participacao"]} de {br["zonas_total"]} zonas '
                   f'({proporcao:.1f}%). Zonas restantes usam a estimativa anterior '
                   'de votos válidos.')
        if proporcao<99.9:
            st.warning('Participação insuficiente para agregar comparecimento, '
                       'abstenção, brancos e nulos como totais nacionais. '
                       'Os valores abaixo abrangem apenas zonas com dados completos.')
        else:
            d1,d2,d3,d4=st.columns(4)
            d1.metric('Comparecimento final estimado',
                      _formatar_numero(br['comparecimento_estimado_participacao']))
            d2.metric('Abstenções finais estimadas',
                      _formatar_numero(br['abstencoes_estimadas_participacao']))
            d3.metric('Brancos finais estimados',
                      _formatar_numero(br['brancos_estimados_participacao']))
            d4.metric('Nulos finais estimados',
                      _formatar_numero(br['nulos_estimados_participacao']))
        st.caption('Participação e votos inválidos são estimativas exploratórias, '
                   'não resultados oficiais nem taxas individualmente observadas '
                   'dos eleitores que ainda não votaram.')

    # A previsão nacional é apresentada como resultado de um modelo, nunca
    # como parcial TSE ou como probabilidade calibrada de vitória.
    st.markdown('#### '+('Soma nacional estimada' if nacional_habilitado else 'Soma SOMENTE das UFs cadastradas'))
    if not auditoria_bloqueou:
        ca,cb=st.columns(2)
        ca.metric('Lula · votos finais estimados',_formatar_numero(br['lula_estimado']))
        cb.metric('Flávio · votos finais estimados',_formatar_numero(br['flavio_estimado']))
    st.caption('Valores exclusivamente modelados. '+('Não representam apuração oficial.' if nacional_habilitado else 'Cadastro incompleto: NÃO representam o Brasil.'))

    with st.expander(('Cenários nacionais' if nacional_habilitado else 'Cenários parciais das UFs')+' (não probabilísticos)'):
        st.caption('Choques independentes no comparecimento ainda não processado '
                   'e na participação de Lula entre votos válidos restantes. '
                   'Os votos oficiais já apurados nunca são alterados.')
        st.markdown('**Amplitude dos cenários**')
        dcompare=st.slider('Comparecimento ainda não observado (± p.p.)',
                           min_value=0.0,max_value=8.0,value=2.0,step=.5,
                           key='c_sens_comparecimento')
        dprefer=st.slider('Preferência de Lula nos votos restantes (± p.p.)',
                          min_value=0.0,max_value=8.0,value=3.0,step=.5,
                          key='c_sens_preferencia')
        banda=faixa_sensibilidade(resultado['linhas'],dcompare,dprefer)
        if banda['lula_min_pct'] is not None:
            st.write('Lula — faixa de estresse: '
                     f'{banda["lula_min_pct"]:.2f}% a {banda["lula_max_pct"]:.2f}%')
            st.write('Flávio — faixa de estresse: '
                     f'{banda["flavio_min_pct"]:.2f}% a {banda["flavio_max_pct"]:.2f}%')
        st.caption(banda['limite'])
        if banda['central']['zonas_sem_dados_participacao']:
            st.warning('Choques de comparecimento são calculados apenas nas '
                       f'{banda["central"]["zonas_com_dados_participacao"]} zonas '
                       'com histórico e eleitorado disponíveis. Outras zonas '
                       'mantêm o volume base; a faixa pode subestimar riscos.')

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
    with st.expander('Cenários para '+escolhida+' (não probabilísticos)'):
        apenas_uf=[x for x in resultado['linhas'] if x['uf']==escolhida]
        s_uf=faixa_sensibilidade(apenas_uf,dcompare,dprefer)
        if s_uf['lula_min_pct'] is not None:
            st.write('Lula: '+f'{s_uf["lula_min_pct"]:.2f}%'
                     +' a '+f'{s_uf["lula_max_pct"]:.2f}%')
            st.write('Flávio: '+f'{s_uf["flavio_min_pct"]:.2f}%'
                     +' a '+f'{s_uf["flavio_max_pct"]:.2f}%')
        st.caption(s_uf['limite'])
        st.caption(f'Zonas sem modelagem explícita de comparecimento: '
                   f'{s_uf["central"]["zonas_sem_dados_participacao"]}')
    dados_uf=resultado['ufs'][escolhida]
    with st.expander('Diagnóstico de representatividade das zonas observadas'):
        diag=resultado.get('diagnostico_representatividade_uf',{}).get(escolhida)
        if diag is None or diag['lula_hist_observadas_pct'] is None:
            st.info('Ainda não há zonas observadas com histórico comparável nesta UF.')
        else:
            st.write('Lula histórico nas zonas já observadas: '
                     f'{diag["lula_hist_observadas_pct"]:.2f}%')
            st.write('Lula histórico em todas as zonas da UF: '
                     f'{diag["lula_hist_total_pct"]:.2f}%')
            delta=(diag['lula_hist_observadas_pct']-
                   diag['lula_hist_total_pct'])
            st.write('Viés da composição histórica das zonas observadas: '
                     f'{delta:+.2f} p.p.')
            st.caption('Diferença de perfil histórico, não erro efetivo da '
                       'apuração nem evidência direta de mudança de voto.')

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
        'modelo_volume':'Modelo de volume',
        'comparecimento_final_estimado':'Comparecimento final estimado',
        'abstencoes_finais_estimadas':'Abstenções finais estimadas',
        'brancos_finais_estimados':'Brancos finais estimados',
        'nulos_finais_estimados':'Nulos finais estimados',
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
    with st.expander('Consolidação das localidades cadastradas'):
        st.dataframe(tab_uf,hide_index=True,use_container_width=True)
        st.download_button('Exportar consolidação por UF (CSV)',
                           tab_uf.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),
                           file_name='election_lab_ufs_derivadas_de_zonas.csv',
                           mime='text/csv',key='baixar_consolidacao_zonas')
    st.caption('Operação do coletor: python coletor_zonal.py --uf SP --limite 300 '
               'ou python coletor_zonal.py --todas --limite 10000. '
               'Ele somente consulta o 2º turno após o início oficial da divulgação.')
