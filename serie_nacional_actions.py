"""Histórico nacional oficial guardado junto ao snapshot zonal recuperável.

Apenas séries EA20 oficiais do segundo turno. Nunca inclui projeções.
"""
from __future__ import annotations
from datetime import datetime, timezone

LIMITE_REGISTROS=2000
CAMPOS=('geracao','capturado','secoes','secoes_total',
        'validos','lula','flavio')


def validar_item(item):
    if not isinstance(item,dict) or not set(CAMPOS).issubset(item):
        raise ValueError('Registro nacional sem campos obrigatórios')
    try:
        geracao=datetime.strptime(item['geracao'],'%d/%m/%Y %H:%M:%S')
        capturado=datetime.fromisoformat(item['capturado'])
        if capturado.tzinfo is None:
            raise ValueError('Timestamp de captura sem fuso')
        valores=[item[k] for k in ('secoes','secoes_total',
                                  'validos','lula','flavio')]
        if any(type(v) is not int or v<0 for v in valores):
            raise ValueError('Contagens nacionais inválidas')
        s,ts,v,l,f=valores
        if s>ts or l+f!=v or (v and not s):
            raise ValueError('Votos/seções nacionais inconsistentes')
    except (TypeError,ValueError,KeyError) as exc:
        raise ValueError('Registro nacional inválido') from exc
    return geracao


def incorporar(anteriores, novas):
    if not isinstance(anteriores,list) or not isinstance(novas,list):
        raise ValueError('Histórico nacional deve ser lista')
    if len(anteriores)+len(novas)>10000:
        raise ValueError('Histórico nacional fora do limite')
    por_geracao={}
    for item in anteriores+novas:
        instante=validar_item(item)
        chave=item['geracao']
        anterior=por_geracao.get(chave)
        if anterior is None or (
            item['secoes']>anterior['secoes'] or
            (item['secoes']==anterior['secoes'] and
             item['capturado']>anterior['capturado'])
        ):
            por_geracao[chave]=dict(item)
    ordenada=sorted(por_geracao.values(),
                    key=lambda item:datetime.strptime(
                        item['geracao'],'%d/%m/%Y %H:%M:%S'))
    # Geracoes futuras jamais podem retroceder nas secoes ja divulgadas.
    progresso=-1
    for item in ordenada:
        if item['secoes']<progresso:
            raise ValueError('Histórico nacional contém regressão de seções')
        progresso=item['secoes']
    return ordenada[-LIMITE_REGISTROS:]


def registrar_oficial(snapshot,nacional,agora=None):
    if not isinstance(snapshot,dict) or snapshot.get('eleicao')!=6258 or (
        snapshot.get('catalogo_origem')!='EA16_TSE_3221'
    ):
        raise ValueError('Snapshot não é o coletor EA16 do segundo turno')
    instante=agora or datetime.now(timezone.utc)
    if instante.tzinfo is None:
        raise ValueError('Captura sem fuso')
    item={'geracao':nacional['geracao'],
          'capturado':instante.isoformat(),
          **{k:nacional[k] for k in ('secoes','secoes_total',
                                    'validos','lula','flavio')}}
    snapshot['historico_br']=incorporar(snapshot.get('historico_br',[]),
                                       [item])
    return snapshot['historico_br']
