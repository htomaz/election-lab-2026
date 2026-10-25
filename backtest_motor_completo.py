"""Backtest temporal proxy do MOTOR ZONAL COMPLETO, sem vazamento.

Referência exclusivamente 2022T2; alvo: 2026T1, um turno de três+ candidatos.
Compara voto Lula / (Lula + candidato 22), não votos válidos Lula/Flávio no T2.
Divulgação simulada em zonas INTEIRAS; não reproduz a sequência de seções do TSE.
A ordem aleatória e os estresses são determinados sem observar os votos-alvo.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import csv
import json
import random
import statistics
import time
from pathlib import Path

from importar_participacao import carregar_participacao
from modelo import projetar_locais
from tse import UFS
from modelo_zonas import carregar_zonas
from motor_zonal_completo import executar, id_zona

ETAPAS=(5,10,20,30,50,70,90,100)
SEMENTES=range(5)
AGORA=1800000000.
CSV_SAIDA=Path('/tmp/backtest_motor_completo.csv')
RESUMO_SAIDA=Path('/tmp/resumo_motor_completo.json')


def preparar():
    ref=carregar_zonas()
    part=carregar_participacao()
    alvos={k:x[(2026,1)] for k,x in ref.items() if (2026,1) in x}
    # As únicas séries visíveis ao motor ANTES do alvo são de 2022.
    antigos={k:{(2022,2):x[(2022,2)]} for k,x in ref.items() if (2022,2) in x}
    antigos_p={k:{(2022,2):x[(2022,2)]}
               for k,x in part.items() if (2022,2) in x}
    dados_alvo_p={k:x[(2026,1)] for k,x in part.items() if (2026,1) in x}
    if len(alvos)!=6292 or len(antigos)<6200:
        raise ValueError('Base histórica incompleta')
    assert all(set(x)=={(2022,2)} for x in antigos.values())
    assert all(set(x)=={(2022,2)} for x in antigos_p.values())
    catalogo=[{'uf':k[0],'municipio':k[1],'zona':k[2]}
              for k in sorted(alvos)]
    completo={}
    for k,h in alvos.items():
        p=dados_alvo_p.get(k)
        item={'lula':h['lula'],'flavio':h['direita'],
              'validos':h['validos'],'secoes':1,'secoes_total':1,
              'capturado_em':AGORA,'fase':'o','turno':'2'}
        if (p and p['validos']==h['validos'] and
            0<=p['comparecimento']+p['abstencoes']<=p['aptos'] and
            p['comparecimento']>=p['validos']+p['brancos']+p['nulos']):
            item.update({'aptos':p['aptos'],
                         'aptos_processados':p['aptos'],
                         'aptos_instalados':p['aptos'],
                         'aptos_nao_instalados':0,
                         'comparecimento':p['comparecimento'],
                         'abstencoes':p['abstencoes'],
                         'brancos':p['brancos'],'nulos':p['nulos']})
        completo[k]=item
    return antigos,antigos_p,alvos,catalogo,completo


def ordenacoes(alvos,antigos):
    keys=sorted(alvos)
    for i in SEMENTES:
        order=keys.copy()
        random.Random(i).shuffle(order)
        yield f'aleatorio_{i}','aleatoria',order
    # Todos os rankings extremos abaixo dependem SÓ do histórico 2022.
    yield ('maiores_2022','stress_prior',
           sorted(keys,key=lambda k:-antigos.get(k,{(2022,2):{'validos':0}})
                  [(2022,2)]['validos']))
    yield ('pro_lula_2022','stress_prior',
           sorted(keys,key=lambda k:(
               -(lambda x:x['lula']/max(1,x['lula']+x['direita']))(
                 antigos[k][(2022,2)]) if k in antigos else 0,
               k)))


def executar_teste():
    antigos,antigos_p,alvos,catalogo,observaveis=preparar()
    alvo_l=sum(x['lula'] for x in alvos.values())
    alvo_f=sum(x['direita'] for x in alvos.values())
    verdade=100*alvo_l/(alvo_l+alvo_f)
    alvo_validos=sum(x['validos'] for x in alvos.values())
    rows=[]
    uf_hist=defaultdict(lambda: {(2022,2):{
        'lula':0,'direita':0,'validos':0}})
    zonas_total=defaultdict(int)
    for k in alvos:
        zonas_total[k[0]]+=1
    for k,reg in antigos.items():
        for campo in ('lula','direita','validos'):
            uf_hist[k[0]][(2022,2)][campo]+=reg[(2022,2)][campo]
    for nome,classe,order in ordenacoes(alvos,antigos):
        for pct in ETAPAS:
            n=round(len(order)*pct/100)
            snap={'versao':1,'eleicao':6258,
                  'catalogo_origem':'RETROSPECTIVO_NAO_OFICIAL',
                  'catalogo':catalogo,
                  'observacoes':{id_zona(k):observaveis[k] for k in order[:n]}}
            # Mesmo conjunto de zonas da rodada para todos os métodos.
            observadas_uf=defaultdict(lambda:{
                'lula':0,'flavio':0,'validos':0,'secoes':0})
            for k in order[:n]:
                h=alvos[k]
                a=observadas_uf[k[0]]
                a['lula']+=h['lula']
                a['flavio']+=h['direita']
                a['validos']+=h['validos']
                a['secoes']+=1
            parciais_uf={uf:{**observadas_uf[uf],
                            'secoes_total':zonas_total[uf]} for uf in UFS}
            t_uf=time.monotonic()
            agregado=projetar_locais(parciais_uf,uf_hist,
                                    peso_2026=0.,intensidade=.35)
            if not agregado['completo']:
                raise AssertionError('Baseline UF incompleto')
            if pct==100 and abs(agregado['lula_pct']-verdade)>.000001:
                raise AssertionError('Baseline UF não convergiu em 100%')
            erro_uf=agregado['lula_pct']-verdade
            rows.append({
                'cenario':nome,'tipo_cenario':classe,'etapa_pct':pct,
                'modelo':'agregado_por_uf','zonas_reveladas':n,
                'zonas_totais':len(alvos),
                'lula_previsto_pct':round(agregado['lula_pct'],5),
                'lula_alvo_pct':round(verdade,5),
                'erro_pp':round(erro_uf,5),
                'erro_abs_pp':round(abs(erro_uf),5),
                'votos_validos_previstos_sob_cobertura':None,
                'votos_validos_verdade_sob_cobertura':None,
                'erro_relativo_validos_pct':None,
                'cobertura_participacao_pct':None,
                'tempo_s':round(time.monotonic()-t_uf,3)})
            for modelo,participacao in (
                ('motor_zonal_sem_participacao',None),
                ('motor_zonal_com_participacao',antigos_p)):
                t0=time.monotonic()
                result=executar(snap,antigos,agora=AGORA,
                       exigir_catalogo_nacional=False,peso_2026=0.,
                       intensidade=.35,participacao=participacao)
                br=result['brasil']
                if br['zonas_concluidas']!=n or len(result['linhas'])!=len(alvos):
                    raise AssertionError('Cobertura de zonas incorreta')
                if abs(br['lula_estimado']-
                       sum(z['lula_estimado'] for z in result['ufs'].values()))>.01:
                    raise AssertionError('Agregação UF/BR divergiu')
                if abs(br['flavio_estimado']-
                       sum(z['flavio_estimado'] for z in result['municipios'].values()))>.01:
                    raise AssertionError('Agregação município/BR divergiu')
                if pct==100 and (abs(br['lula_estimado']-alvo_l)>.01 or
                                 abs(br['flavio_estimado']-alvo_f)>.01):
                    raise AssertionError('Não convergiu em 100%')
                m=br['lula_pct_estimado']
                erro=m-verdade
                validos_proj=sum(
                    x['participacao']['validos_finais_estimados']
                    for x in result['linhas'] if x['participacao'] is not None)
                validos_ref=sum(
                    alvos[(x['uf'],x['municipio'],x['zona'])]['validos']
                    for x in result['linhas'] if x['participacao'] is not None)
                rows.append({
                    'cenario':nome,'tipo_cenario':classe,'etapa_pct':pct,
                    'modelo':modelo,'zonas_reveladas':n,
                    'zonas_totais':len(alvos),
                    'lula_previsto_pct':round(m,5),
                    'lula_alvo_pct':round(verdade,5),
                    'erro_pp':round(erro,5),
                    'erro_abs_pp':round(abs(erro),5),
                    'votos_validos_previstos_sob_cobertura':round(validos_proj),
                    'votos_validos_verdade_sob_cobertura':validos_ref,
                    'erro_relativo_validos_pct':round(
                        100*(validos_proj-validos_ref)/validos_ref,5)
                        if validos_ref else None,
                    'cobertura_participacao_pct':
                        round(br['cobertura_modelo_participacao_pct'],3),
                    'tempo_s':round(time.monotonic()-t0,3)})
        print('Cenário concluído:',nome,flush=True)
    return rows,verdade,alvo_validos


def resumir(rows,verdade,alvo_validos):
    grupos=defaultdict(list)
    for r in rows:
        grupos[(r['tipo_cenario'],r['etapa_pct'],r['modelo'])].append(r)
    summary=[]
    for (classe,pct,modelo),arr in sorted(grupos.items()):
        errs=[x['erro_abs_pp'] for x in arr]
        verrors=[abs(x['erro_relativo_validos_pct']) for x in arr
                 if x['erro_relativo_validos_pct'] is not None]
        summary.append({'tipo_cenario':classe,'etapa_pct':pct,'modelo':modelo,
                        'n_cenarios':len(arr),'mae_pp':round(statistics.mean(errs),4),
                        'max_abs_pp':round(max(errs),4),
                        'mae_validos_pct':round(statistics.mean(verrors),4)
                        if verrors else None,
                        'cobertura_participacao_pct':
                            arr[0]['cobertura_participacao_pct'],
                        'tempo_max_s':max(x['tempo_s'] for x in arr)})
    report={'metodo':'motor_zonal_completo.py via executar()',
            'referencia':'2022 segundo turno (exclusiva)',
            'alvo':'2026 primeiro turno, Lula/(Lula+candidato22)',
            'target_pct':round(verdade,4),
            'validos_reais_2026T1':alvo_validos,
            'sem_vazamento':'Excluídos completamente votos e participação 2026T1 dos priors',
            'limitacao':'Zonas inteiras e ordens sintéticas; resultado de 2026T1 não simula segundo turno real.',
            'resultados':summary}
    CSV_SAIDA.parent.mkdir(parents=True,exist_ok=True)
    with CSV_SAIDA.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    RESUMO_SAIDA.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for r in summary:
        if r['tipo_cenario'] in ('aleatoria','stress_prior'):
            print('BACKTEST_MOTOR_COMPLETO',
                  json.dumps(r,ensure_ascii=False),flush=True)
    print('BACKTEST_MOTOR_INFO',json.dumps({
        'total_linhas':len(rows),'alvo_pct':report['target_pct'],
        'seeds_aleatorias':len(SEMENTES),'stresses':2,
        'modelos':3,'etapas':len(ETAPAS)},ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    rows,verdade,validos=executar_teste()
    resumir(rows,verdade,validos)
