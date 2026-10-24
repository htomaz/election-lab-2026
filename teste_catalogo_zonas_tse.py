"""Validação real do formato EA12 2026T1 para preparar a coleta de 2026T2.

Não coleta resultados do 2º turno antes de 25/10.
Testa se o catálogo municipal/zonas publicado permite construir URLs EA20.
"""
import csv
import json
from pathlib import Path
import requests
from coletor_zonal import catalogar_ea12


URL='https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json'


def executar(historico='historico_zonas.csv'):
    resposta=requests.get(URL,timeout=(5,25),
                          headers={'User-Agent':'ElectionLab2026/0.6 (EA12 TSE preflight)'})
    resposta.raise_for_status()
    catalogo=catalogar_ea12(resposta.json())
    with Path(historico).open(newline='',encoding='utf-8-sig') as f:
        esperado={(r['uf'],r['municipio'],r['zona'])
                  for r in csv.DictReader(f)
                  if r['ano']=='2026' and r['turno']=='1'}
    ausentes=esperado-set(catalogo)
    inesperadas=set(catalogo)-esperado
    if len(catalogo)<6000:
        raise ValueError('Catálogo EA12 de zonas parece parcial')
    if len(ausentes)>10:
        raise ValueError(f'{len(ausentes)} zonas históricas faltam no EA12 2026T1')
    return {'status':'catalogo_EA12_primeiro_turno_verificado',
            'zonas_ea12':len(catalogo),
            'zonas_hist_2026t1':len(esperado),
            'zonas_ausentes':len(ausentes),
            'zonas_novas':len(inesperadas),
            'exemplos_ausentes':[list(k) for k in sorted(ausentes)[:6]]}


if __name__=='__main__':
    print(json.dumps(executar(),ensure_ascii=False,indent=2))
