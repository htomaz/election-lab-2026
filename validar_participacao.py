"""Auditoria de cobertura e votos das bases históricas zonais TSE."""
from __future__ import annotations
from collections import defaultdict
from modelo_zonas import carregar_zonas
from importar_participacao import carregar_participacao

ESPERADOS={
    (2022,1): {'zonas':6283,'aptos':156454011,'comparecimento':123682372,
               'abstencoes':32770982,'brancos':1964779,'nulos':3487874,
               'validos':118229719},
    (2022,2): {'zonas':6283,'aptos':156454011,'comparecimento':124252796,
               'abstencoes':32200558,'brancos':1769678,'nulos':3930765,
               'validos':118552353},
    (2026,1): {'zonas':6292,'aptos':158745502,'comparecimento':125275835,
               'abstencoes':33469244,'brancos':2300798,'nulos':3669003,
               'validos':119300788}
}

def auditar(zonas='historico_zonas.csv',
            participacao='historico_participacao_zonas.csv'):
    his=carregar_zonas(zonas)
    part=carregar_participacao(participacao)
    rel={}
    divergentes=[]
    for ano_turno,exp in ESPERADOS.items():
        soma=defaultdict(int)
        # A base de votos por candidato guarda 2022T2/2026T1. Para
        # 2022T1, o catálogo territorial comparável é o de 2022T2.
        periodo_voto = (2022,2) if ano_turno == (2022,1) else ano_turno
        chaves_vot={k for k,d in his.items() if periodo_voto in d}
        chaves_part={k for k,d in part.items() if ano_turno in d}
        if chaves_vot!=chaves_part:
            raise ValueError(f'{ano_turno}: divergência de cobertura: '
                             f'faltam {len(chaves_vot-chaves_part)} zonas de participação, '
                             f'sobram {len(chaves_part-chaves_vot)}')
        for k in chaves_vot:
            p=part[k][ano_turno]
            if ano_turno in ((2022,2),(2026,1)):
                v=his[k][ano_turno]
                if v['validos'] != p['validos']:
                    divergentes.append((k,ano_turno,v['validos'],p['validos']))
            for campo in ('aptos','comparecimento','abstencoes',
                          'brancos','nulos','validos'):
                soma[campo]+=p[campo]
        soma['zonas']=len(chaves_vot)
        for campo,valor in exp.items():
            if soma[campo]!=valor:
                raise ValueError(f'{ano_turno} {campo}: {soma[campo]} vs {valor}')
        rel[str(ano_turno)]=dict(soma)
    if divergentes:
        raise ValueError(f'{len(divergentes)} divergências de votos válidos '
                         f'entre arquivos independentes: {divergentes[:5]}')
    return rel

if __name__=='__main__':
    import json
    print(json.dumps(auditar(),ensure_ascii=False,indent=2))
