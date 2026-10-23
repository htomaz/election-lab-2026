"""Pseudo-backtest territorial: 2022T2 -> 2026T1 (duelo Lula x candidato 22).

NAO valida o segundo turno de 2026. Revela zonas, nao secoes reais.
As ordenacoes pro-candidato usam resultado final e sao cenarios adversariais,
nao estrategias que estariam disponiveis antes da apuracao.
"""
from __future__ import annotations
import argparse
import csv
import random
from collections import defaultdict
from modelo import projetar_locais
from tse import UFS

CENARIOS = ('aleatorio_0','aleatorio_1','aleatorio_2','pro_lula','pro_direita','maiores')
PROGRESSOS = (5,10,20,30,50,70,90,100)


def executar(caminho):
    grupos = defaultdict(dict)
    with open(caminho, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            uf = r['uf']
            if uf not in UFS:
                continue
            k = (int(r['ano']),int(r['turno']))
            key = (uf,r['municipio'],r['zona'])
            if key in grupos[k]:
                raise ValueError(f'Chave duplicada: {key} {k}')
            grupos[k][key] = {c:int(r[c]) for c in ('lula','direita','validos')}
    antigos = grupos[(2022,2)]
    novos = grupos[(2026,1)]
    if not antigos or not novos:
        raise ValueError('Faltam dados 2022T2 ou 2026T1')
    ref = defaultdict(lambda: {(2022,2): {'lula':0,'direita':0,'validos':0}})
    for (uf,_,_), v in antigos.items():
        for c in ('lula','direita','validos'):
            ref[uf][(2022,2)][c] += v[c]
    linhas = [(k,v) for k,v in novos.items()]
    totais_zonas = defaultdict(int)
    for (uf,_,_),_ in linhas:
        totais_zonas[uf] += 1
    soma_l = sum(v['lula'] for _,v in linhas)
    soma_d = sum(v['direita'] for _,v in linhas)
    alvo = 100*soma_l/(soma_l+soma_d)
    saida=[]
    for cenario in CENARIOS:
        ordenadas = linhas.copy()
        if cenario.startswith('aleatorio_'):
            random.Random(int(cenario[-1])).shuffle(ordenadas)
        elif cenario == 'maiores':
            ordenadas.sort(key=lambda item:item[1]['validos'],reverse=True)
        else:
            ordenadas.sort(
                key=lambda item:item[1]['lula']/max(1,item[1]['lula']+item[1]['direita']),
                reverse=cenario=='pro_lula'
            )
        for pct in PROGRESSOS:
            n=max(1,round(len(ordenadas)*pct/100))
            parcial=defaultdict(lambda:{'lula':0,'flavio':0,'validos':0,'secoes':0})
            for (uf,_,_),v in ordenadas[:n]:
                p=parcial[uf]
                p['lula']+=v['lula']
                p['flavio']+=v['direita']
                p['validos']+=v['validos']
                p['secoes']+=1
            locais={}
            for uf in UFS:
                p=parcial[uf]
                locais[uf]={**p,'secoes_total':totais_zonas[uf]}
            rel=projetar_locais(locais,ref,peso_2026=0,ajuste_volume=1,intensidade=.35)
            if not rel['completo']:
                raise ValueError(f'Cobertura incompleta: {rel["faltantes"]}')
            estimado=rel['lula_pct']
            saida.append({'cenario':cenario,'zonas_reveladas_pct':pct,
                          'estimativa_lula_pct':round(estimado,3),
                          'real_lula_pct':round(alvo,3),
                          'erro_pp':round(estimado-alvo,3),
                          'erro_absoluto_pp':round(abs(estimado-alvo),3)})
    return saida


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--zonas',default='historico_zonas.csv')
    p.add_argument('--saida',default='backtest_election_lab.csv')
    args=p.parse_args()
    linhas=executar(args.zonas)
    with open(args.saida,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    print(f'{len(linhas)} simulacoes gravadas em {args.saida}')
