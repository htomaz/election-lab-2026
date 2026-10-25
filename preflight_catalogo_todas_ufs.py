"""Audita TODOS os EA16 de 2026T1 sem consultar votos futuros.

Coleta 28 catálogos de zonas do pleito 3220, compara com as 6.292
zonas históricas do 1º turno e identifica exceções por UF/ZZ.
Não consulta segundo turno 3221; não substitui sua homologação.
"""
import json
import argparse
from collections import Counter

from coletor_zonal import baixar_catalogo
from modelo_zonas import carregar_zonas
from tse import UFS


def auditar(pleito=3220):
    if pleito not in (3220,3221):
        raise ValueError('Pleito permitido: somente 3220 ou 3221')
    catalogo=baixar_catalogo(pleito=pleito)
    refs=carregar_zonas()
    historico={k for k,h in refs.items() if (2026,1) in h}
    por_uf=[]
    for uf in UFS:
        atuais={k for k in catalogo if k[0]==uf}
        anteriores={k for k in historico if k[0]==uf}
        faltantes=anteriores-atuais
        extras=atuais-anteriores
        fra=len(anteriores & atuais)/max(1,len(anteriores))
        por_uf.append({'uf':uf,'zonas_ea16':len(atuais),
                       'zonas_historicas':len(anteriores),
                       'faltantes':len(faltantes),'novas':len(extras),
                       'cobertura_pct':round(100*fra,3),
                       'secoes_ea16':sum(catalogo[k]['secoes_cadastradas_ea16']
                                         for k in atuais),
                       'exemplos_faltantes':[list(k) for k in sorted(faltantes)[:3]]})
    print(json.dumps({'pleito':pleito,'linhas_historicas':len(historico),
                      'zonas_ea16':len(catalogo),'por_uf':por_uf},
                     indent=2,ensure_ascii=False))
    erros=[r for r in por_uf if r['cobertura_pct']<95 or r['secoes_ea16']==0]
    if erros:
        raise ValueError('Cobertura EA16 histórica insuficiente em: '+
                         str([x['uf'] for x in erros]))
    if len(catalogo)<6000:
        raise ValueError('Catálogo EA16 nacional aparentemente incompleto')
    return {'pleito':pleito,'zonas_ea16':len(catalogo),
            'zonas_historicas':len(historico),
            'ufs_conferidas':len(por_uf),'ufs_com_falha':len(erros)}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--pleito',type=int,choices=[3220,3221],default=3220)
    args=p.parse_args()
    print('RESULTADO:',auditar(args.pleito))
