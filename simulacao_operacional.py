"""Simulação pré-apuração: estresse operacional do motor com 6.292 zonas.

DADOS SINTÉTICOS: os votos de 2026T1 são apenas matéria-prima para
construir um alvo fictício. Isto NÃO é backtest preditivo de 2026T2
e NÃO consulta votos reais do segundo turno.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv
import json
import random
import resource
import time

from modelo_zonas import carregar_zonas
from importar_participacao import carregar_participacao
from motor_zonal_completo import executar, id_zona

STAGES=(0,5,25,50,100)
TEMPO=1_800_000_000


def simular(historico='historico_zonas.csv',
            participacao='historico_participacao_zonas.csv'):
    refs=carregar_zonas(historico)
    taxas=carregar_participacao(participacao)
    keys=[k for k,v in refs.items() if (2026,1) in v]
    if len(keys)!=6292:
        raise ValueError(f'Esperadas 6.292 zonas do 2026T1: {len(keys)}')
    ordem=keys.copy()
    random.Random(42).shuffle(ordem)
    catalogo=[{'uf':k[0],'municipio':k[1],'zona':k[2],
               'secoes_cadastradas_ea16':1} for k in keys]
    verdade={'lula':0,'flavio':0,'validos':0,'comparecimento':0,
             'abstencoes':0,'brancos':0,'nulos':0}
    # Não usar o voto válido inteiro como voto dos dois candidatos no 1º
    # turno real; converter o confronto Lula/22 apenas para construir um
    # segundo turno SIMULADO com dois candidatos e total válido conservado.
    urnas={}
    for k in keys:
        h=refs[k][(2026,1)]
        x=taxas[k][(2026,1)]
        par=h['lula']+h['direita']
        total=h['validos']
        l=round(total*h['lula']/par) if par else round(total/2)
        f=total-l
        urnas[k]={'lula':l,'flavio':f,'validos':total,
                  'aptos':x['aptos'],'aptos_processados':x['aptos'],
                  'comparecimento':x['comparecimento'],
                  'abstencoes':x['abstencoes'],
                  'brancos':x['brancos'],'nulos':x['nulos'],
                  'secoes':1,'secoes_total':1,'capturado_em':TEMPO}
        for nome,valor in [('lula',l),('flavio',f),('validos',total),
                           ('comparecimento',x['comparecimento']),
                           ('abstencoes',x['abstencoes']),
                           ('brancos',x['brancos']),('nulos',x['nulos'])]:
            verdade[nome]+=valor
    res=[]
    for percentual in STAGES:
        t0=time.monotonic()
        n=round(len(keys)*percentual/100)
        observado={id_zona(k):urnas[k] for k in ordem[:n]}
        snapshot={'versao':1,'eleicao':6258,
                  'catalogo_origem':'SIMULACAO_HISTORICA_NAO_OFICIAL',
                  'catalogo':catalogo,'observacoes':observado}
        saida=executar(snapshot,refs,participacao=taxas,agora=TEMPO,
                       exigir_catalogo_nacional=False)
        br=saida['brasil']
        if len(saida['linhas'])!=len(keys):
            raise AssertionError('Perdeu zonas do catálogo')
        if br['zonas_concluidas']!=n:
            raise AssertionError(f'Concluídas {br["zonas_concluidas"]} != {n}')
        if any(r['lula_projetado']+1e-7<r['lula_apurado'] or
               r['flavio_projetado']+1e-7<r['flavio_apurado']
               for r in saida['linhas']):
            raise AssertionError('Voto apurado foi reduzido na previsão')
        if abs(br['lula_estimado']-
               sum(v['lula_estimado'] for v in saida['ufs'].values()))>1e-4:
            raise AssertionError('UF não fecha no BR')
        if abs(br['flavio_estimado']-
               sum(v['flavio_estimado'] for v in saida['municipios'].values()))>1e-4:
            raise AssertionError('Municípios não fecham no BR')
        if percentual==100:
            for nome,chave in (
                ('lula','lula_estimado'),('flavio','flavio_estimado'),
                ('comparecimento','comparecimento_estimado_participacao'),
                ('abstencoes','abstencoes_estimadas_participacao'),
                ('brancos','brancos_estimados_participacao'),
                ('nulos','nulos_estimados_participacao')
            ):
                if abs(br[chave]-verdade[nome])>.0001:
                    raise AssertionError(f'{nome}: final não coincide '
                                         f'{br[chave]} != {verdade[nome]}')
            if not br['apuracao_integral_zonas']:
                raise AssertionError('100% da apuração não reconhecido')
        elapsed=time.monotonic()-t0
        res.append({'cenario':'aleatorio_42',
                    'progresso_zonas_pct':percentual,
                    'observadas':n,'zonas_total':len(keys),
                    'segundos':round(elapsed,3),
                    'pico_rss_mb':round(resource.getrusage(
                        resource.RUSAGE_SELF).ru_maxrss/1024,1),
                    'lula_pct_estimado':br['lula_pct_estimado'],
                    'flavio_pct_estimado':br['flavio_pct_estimado'],
                    'abstencoes_estimadas':br['abstencoes_estimadas_participacao'],
                    'zonas_participacao':br['zonas_modeladas_participacao']})
        if elapsed>20:
            raise AssertionError('Motor zonal acima de 20s neste ambiente')
    return res


if __name__=='__main__':
    rows=simular()
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    with Path('/tmp/simulacao_operacional_zonas.csv').open(
        'w',newline='',encoding='utf-8'
    ) as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
