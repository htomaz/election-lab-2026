"""Pré-voo TSE: confirma IDs do pleito na configuração oficial EA11.

Não lê votos nem faz inferências sobre resultado eleitoral.
Nunca adivinha códigos por conveniência: se 3221/6258 não constar
no ele-c.json, coleta REAL de 2º turno permanece bloqueada.
"""
from __future__ import annotations
import argparse
import json
import requests

URL="https://resultados.tse.jus.br/oficial/comum/config/ele-c.json"
PLEITO_2026_T1="3220"
PLEITO_2026_T2="3221"
ELEICAO_PRESIDENCIAL_T1="6257"
ELEICAO_PRESIDENCIAL_T2="6258"


def verificar_config(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('pl'),list):
        raise ValueError('EA11 sem lista oficial de pleitos')
    info={}
    for pleito in payload['pl']:
        cod=str(pleito.get('cd',''))
        if cod not in (PLEITO_2026_T1,PLEITO_2026_T2):
            continue
        if pleito.get('c')!='ele2026':
            raise ValueError(f'Pleito {cod} não é do ciclo 2026')
        por_id={str(x.get('cd')):x for x in pleito.get('e',[])}
        info[cod]=por_id
    t1=info.get(PLEITO_2026_T1,{}).get(ELEICAO_PRESIDENCIAL_T1)
    if not t1 or str(t1.get('cdt2'))!=ELEICAO_PRESIDENCIAL_T2 or (
        str(t1.get('t'))!='1' or str(t1.get('tp'))!='8'
    ):
        raise ValueError('EA11 não confirma a eleição federal 6257→6258')
    t2=info.get(PLEITO_2026_T2,{}).get(ELEICAO_PRESIDENCIAL_T2)
    if t2 is None:
        return {'status':'pleito_3221_nao_publicado',
                'pleito_1turno_confirmado':True,
                'pleito_2turno_confirmado':False,
                'geracao':f"{payload.get('dg','')} {payload.get('hg','')}".strip()}
    if str(t2.get('t'))!='2' or str(t2.get('tp'))!='8':
        raise ValueError('EA11 não confirma 6258 como eleição federal 2º turno')
    cargos={
        str(c.get('cd')) for ab in t2.get('abr',[])
        for c in ab.get('cp',[])
    }
    if '1' not in cargos:
        raise ValueError('EA11 não contém cargo Presidente na eleição 6258')
    return {'status':'pleito_3221_confirmado',
            'pleito_1turno_confirmado':True,
            'pleito_2turno_confirmado':True,
            'geracao':f"{payload.get('dg','')} {payload.get('hg','')}".strip()}


def consultar_config(http_get=None):
    pegar=http_get or requests.get
    r=pegar(URL,timeout=(5,20),headers={
        'User-Agent':'ElectionLab2026/0.7 (preflight EA11 TSE)'})
    r.raise_for_status()
    return verificar_config(r.json())


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--exigir-segundo-turno',action='store_true')
    args=p.parse_args()
    r=consultar_config()
    print(json.dumps(r,ensure_ascii=False,indent=2))
    if args.exigir_segundo_turno and not r['pleito_2turno_confirmado']:
        p.exit(3,'Pleito 3221/eleição 6258 não confirmados em EA11.\n')
