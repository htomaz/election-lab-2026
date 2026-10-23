"""Diagnóstico territorial dos históricos; não representa backtest do 2º turno."""
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path


def diagnosticar_zonas(caminho='historico_zonas.csv'):
    """Quantifica heterogeneidade e cobertura, sem inferir ordem de apuração."""
    agregados = defaultdict(lambda: {'zonas': 0, 'municipios': set(),
                                     'pares': 0, 'lula': 0, 'validos': 0,
                                     'soma_quadrados': 0.0})
    vistos = set()
    with Path(caminho).open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        obrigatorias = {'uf','municipio','zona','ano','turno','lula','direita','validos'}
        if not obrigatorias.issubset(reader.fieldnames or []):
            raise ValueError('Colunas obrigatórias ausentes')
        for r in reader:
            key = (r['uf'],r['municipio'],r['zona'],r['ano'],r['turno'])
            if key in vistos:
                raise ValueError(f'Zona duplicada: {key}')
            vistos.add(key)
            l, d, v = (int(r[k]) for k in ('lula','direita','validos'))
            if min(l,d,v) < 0 or l+d > v:
                raise ValueError(f'Votos inválidos: {key}')
            par = l+d
            k = (r['uf'],r['ano'],r['turno'])
            a = agregados[k]
            a['zonas'] += 1
            a['municipios'].add(r['municipio'])
            a['pares'] += par
            a['lula'] += l
            a['validos'] += v
            if par:
                a['soma_quadrados'] += l*l/par
    saida = []
    for (uf,ano,turno), a in sorted(agregados.items()):
        p = a['lula']/a['pares'] if a['pares'] else None
        # Variância ponderada pelo volume Lula+direita em cada zona.
        variancia = (a['soma_quadrados']/a['pares'] - p*p) if p is not None else None
        saida.append({'uf':uf,'ano':int(ano),'turno':int(turno),
                      'municipios':len(a['municipios']),'zonas':a['zonas'],
                      'validos':a['validos'],'participacao_lula_duelo':p,
                      'desvio_padrao_zonas_pp':100*max(0,variancia)**0.5 if variancia is not None else None})
    return saida


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--zonas',default='historico_zonas.csv')
    p.add_argument('--saida',default='diagnostico_zonas.csv')
    args=p.parse_args()
    linhas=diagnosticar_zonas(args.zonas)
    with open(args.saida,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    print(f'{len(linhas)} registros territoriais auditados; saída: {args.saida}')
