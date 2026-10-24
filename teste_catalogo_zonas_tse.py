"""Teste real do catálogo EA16 de seções e zonas do TSE (2026T1).

O EA12 contém nomes de municípios; para enumerar zonas usar EA16.
Realiza UMA consulta oficial à UF AC, evitando varrer o país no teste CI.
"""
import csv
import json
from pathlib import Path
import requests

from coletor_zonal import catalogar_ea16

URL='https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3220/config/ac/ac-p003220-cs.json'


def executar(historico='historico_zonas.csv'):
    resp=requests.get(URL,timeout=(5,30),
                      headers={'User-Agent':'ElectionLab2026/0.6 (EA16 preflight)'})
    resp.raise_for_status()
    catalogo=catalogar_ea16(resp.json(),uf='AC')
    with Path(historico).open(newline='',encoding='utf-8-sig') as f:
        esperado={(r['uf'],r['municipio'],r['zona'])
                  for r in csv.DictReader(f)
                  if r['ano']=='2026' and r['turno']=='1' and r['uf']=='AC'}
    faltantes=esperado-set(catalogo)
    extras=set(catalogo)-esperado
    if len(catalogo)<20:
        raise ValueError('Catálogo EA16 da UF AC parece parcial')
    if faltantes:
        raise ValueError(f'Faltam zonas históricas AC no EA16: {sorted(faltantes)}')
    if not all('secoes_cadastradas_ea16' in r for r in catalogo.values()):
        raise ValueError('EA16 não forneceu as seções da zona')
    return {'status':'catalogo_EA16_2026T1_verificado',
            'uf':'AC','zonas_ea16':len(catalogo),'zonas_historicas':len(esperado),
            'zonas_extras':len(extras),'secoes_ea16':sum(
                x['secoes_cadastradas_ea16'] for x in catalogo.values())}


if __name__=='__main__':
    print(json.dumps(executar(),ensure_ascii=False,indent=2))
