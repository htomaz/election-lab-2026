"""Teste de integração EA20 (rede) isolado; não é teste unitário.

Uso antes de 25/10: python teste_integracao_tse.py --turno 1
Uso após início 2T: python teste_integracao_tse.py --turno 2

Se TSE estiver inacessível, termina com falha; NUNCA simula sucesso.
Só consulta UMA zona (SP/71072/0001); no turno 2, consulta também a UF.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import requests
from auditoria_ao_vivo import reconciliar_zonas
from tse import normalizar_ea20, url_resultado_zona, url_resultado


ZONA=('SP','71072','0001')


def _obter(url):
    resposta=requests.get(url,timeout=(5,12),headers={
        'User-Agent':'ElectionLab2026/0.5 (validacao pontual EA20)'
    })
    resposta.raise_for_status()
    return resposta.json()


def _esperado(caminho):
    with Path(caminho).open(newline='',encoding='utf-8-sig') as arquivo:
        for r in csv.DictReader(arquivo):
            if (r['uf'],r['municipio'],r['zona'],r['ano'],r['turno']) == (*ZONA,'2026','1'):
                return {c:int(r[c]) for c in ('lula','direita','validos')}
    raise ValueError('Zona de referência não encontrada no histórico 2026T1')


def validar(turno, zonas='historico_zonas.csv'):
    eleicao=6257 if turno==1 else 6258
    url=url_resultado_zona(*ZONA,eleicao=eleicao)
    z=normalizar_ea20(_obter(url),ZONA[0],
                      abrangencia_esperada='zona',exigir_metadados=True,
                      eleicao_esperada=eleicao,turno_esperado=turno)
    if z['validos']<=0 or z['secoes']<=0 or z['secoes_total']<=0:
        raise ValueError('EA20 ainda sem apuração válida')
    if turno==1:
        h=_esperado(zonas)
        observados={'lula':z['lula'],'direita':z['flavio'],'validos':z['validos']}
        if observados!=h:
            raise ValueError(f'Zona histórica não confere com EA20 oficial: '
                             f'EA20={observados}; histórico={h}')
        return {'turno':1,'status':'confere','url':url,'zona':observados,
                'secoes':z['secoes'],'geracao':z['geracao']}
    uf=normalizar_ea20(_obter(url_resultado('SP',eleicao=eleicao)),'SP')
    diag=reconciliar_zonas({ZONA:z},uf)
    if diag['status']=='inconsistente':
        raise ValueError(f'Zona excede UF no mesmo snapshot: {diag}')
    if diag['status']!='parcial_compativel':
        return {'turno':2,'status':'indeterminado','motivo':diag['mensagem'],
                'geracao':z['geracao'],'url':url}
    return {'turno':2,'status':'parcial_compativel','url':url,
            'geracao':z['geracao'],'uf_geracao':uf['geracao'],
            'votos_validos_zona':z['validos'],'votos_validos_uf':uf['validos']}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--turno',type=int,choices=[1,2],default=1)
    parser.add_argument('--zonas',default='historico_zonas.csv')
    args=parser.parse_args()
    try:
        print(json.dumps(validar(args.turno,args.zonas),ensure_ascii=False,indent=2))
    except (requests.RequestException,ValueError,KeyError) as exc:
        parser.exit(2,f'INTEGRAÇÃO NÃO VALIDADA: {type(exc).__name__}: {exc}\n')
