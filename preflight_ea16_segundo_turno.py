"""Consulta SEGURA de 1 EA16 do segundo turno (somente catálogo, sem votos).

Se o TSE ainda não disponibilizou o EA16 pleito 3221, registra a
indisponibilidade; não tenta gerar 27 URLs adicionais e evita 404 em série.
"""
from __future__ import annotations

import json
import requests
from coletor_zonal import baixar_catalogo
from modelo_zonas import carregar_zonas


def executar():
    uf='AC'
    try:
        catalogo=baixar_catalogo(abrangencias=[uf],pleito=3221)
    except requests.HTTPError as exc:
        codigo=exc.response.status_code if exc.response is not None else None
        if codigo in (404,403,429):
            return {'status':'ea16_3221_ainda_indisponivel',
                    'uf_testada':uf,'http_status':codigo,
                    'zonas':0,'nota':'Não tentar URLs adicionais até confirmação'}
        raise
    historico=carregar_zonas()
    esperado={k for k,v in historico.items()
              if k[0]==uf and (2026,1) in v}
    encontrado=set(catalogo)
    cobertura=100*len(esperado & encontrado)/max(1,len(esperado))
    if cobertura<95 or not any(
        x['secoes_cadastradas_ea16']>0 for x in catalogo.values()
    ):
        raise ValueError('Catálogo EA16 3221 não passou na conferência AC')
    return {'status':'ea16_3221_confere_primeiro_turno_na_uf',
            'uf_testada':uf,'zonas':len(catalogo),
            'cobertura_historica_pct':round(cobertura,2)}


if __name__=='__main__':
    print(json.dumps(executar(),ensure_ascii=False,indent=2))
