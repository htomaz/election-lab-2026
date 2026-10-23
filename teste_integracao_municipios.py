"""Consulta pontual ao cadastro oficial EA12 do TSE, sem alterar arquivos."""
import json
from pathlib import Path
from municipios_tse import obter_municipios, nome_municipio


def validar(historico='historico_zonas.csv'):
    nomes=obter_municipios()
    if not any('PAULO' in nome.upper() for (uf,codigo),nome in nomes.items()
               if (uf,codigo)==('SP','71072')):
        raise ValueError('Mapa EA12 não identifica São Paulo (SP/71072)')
    codigos=set()
    import csv
    with Path(historico).open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            codigos.add((r['uf'].upper(),r['municipio'].zfill(5)))
    ausentes=sorted(codigos-set(nomes))
    return {'status':'ea12_verificado','municipios_no_ea12':len(nomes),
            'municipios_distintos_no_historico':len(codigos),
            'codigos_historicos_sem_nome':len(ausentes),
            'exemplos_sem_nome':ausentes[:10],
            'exemplo_sp_71072':nome_municipio('SP','71072',nomes)}


if __name__=='__main__':
    print(json.dumps(validar(),ensure_ascii=False,indent=2))
