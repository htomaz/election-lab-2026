"""Auditoria operacional da coleta zonal em relação aos EA20 BR e UF.

Uma amostra compatível NÃO é uma totalização sincronizada. O arquivo JSON
gerado é diagnóstico e jamais substitui um EA20 oficial autenticado.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from auditoria_snapshot_zonal import auditar_parciais
from coletor_zonal import carregar_arquivo
from tse import coletar as coletar_ufs


def avaliar(snapshot, estaduais, erros=None):
    resultado=auditar_parciais(snapshot, estaduais)
    faltantes=[uf for uf in ['BR','AC','AL','AP','AM','BA','CE','DF',
        'ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI',
        'RJ','RN','RS','RO','RR','SC','SP','SE','TO','ZZ']
        if uf not in estaduais]
    bloqueantes=resultado['bloqueantes']
    status=('divergente' if bloqueantes else
            'inconclusivo' if faltantes else
            'reconciliado' if (resultado['nacional']['status']=='reconciliado'
                and all(x['status']=='reconciliado' for x in resultado['por_uf']))
            else 'parcial_compativel_nao_sincrono')
    return {'status':status,'faltantes':faltantes,
            'erros_coleta_agregada':erros or {},'auditoria':resultado,
            'nota':'Compatibilidade não autentica votos e não prova sincronismo.'}


def executar(arquivo,saida):
    snap=carregar_arquivo(arquivo)
    oficiais,erros=coletar_ufs()
    relatorio=avaliar(snap,oficiais,erros)
    Path(saida).write_text(json.dumps(relatorio,ensure_ascii=False,
                        indent=2),encoding='utf-8')
    if relatorio['status'] in ('divergente','inconclusivo'):
        raise ValueError('Coleta zonal não conciliável: '+
                         relatorio['status'])
    return relatorio


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot',default='dados_zonais_6258.json')
    p.add_argument('--saida',default='auditoria_ufbr.json')
    a=p.parse_args()
    r=executar(a.snapshot,a.saida)
    print(json.dumps({'status':r['status'],
                      'nacional':r['auditoria']['nacional']['status']},
                     ensure_ascii=False,indent=2))
