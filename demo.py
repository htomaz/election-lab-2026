"""Dados totalmente fictícios e determinísticos, para testar a interface."""
from tse import UFS
import random


def gerar_demo(progresso=45):
    rng=random.Random(20261025)
    hist={}; parametros={}; total_uf={}
    for i,uf in enumerate(UFS):
        tam=int(100000+(i*734723 % 13000000))
        frac=min(.79,max(.21,.53+.21*(rng.random()-.5)*2))
        hist[uf]={(2026,1):{'lula':int(tam*frac*.77),'direita':int(tam*(1-frac)*.76),'validos':tam},
                  (2022,2):{'lula':int(tam*(frac+.013)),'direita':int(tam*(1-frac-.013)),'validos':int(tam*.96)}}
        parametros[uf]={'peso':tam,'share':frac+0.035*(rng.random()-.5),'atraso':rng.uniform(-.18,.18)}
    for uf in UFS:
        y=parametros[uf]
        pr=1.0 if progresso>=100 else max(0.,min(1.,progresso/100+y['atraso']))
        v=int(y['peso']*pr)
        # uma pequena distorção das primeiras urnas, deliberadamente sintética
        viés=(1-pr)*.055*(1 if (sum(map(ord,uf))%2) else -1)
        share=max(0.01,min(.99,y['share']+viés))
        lula=int(v*share)
        total_uf[uf]={'uf':uf,'lula':lula,'flavio':v-lula,'validos':v,
                      'secoes':int(1000*pr),'secoes_total':1000,
                      'geracao':'SIMULAÇÃO – não oficial'}
    nacional={'uf':'BR','lula':sum(r['lula'] for r in total_uf.values()),
              'flavio':sum(r['flavio'] for r in total_uf.values()),
              'validos':sum(r['validos'] for r in total_uf.values()),
              'secoes':sum(r['secoes'] for r in total_uf.values()),
              'secoes_total':28_000, 'geracao':'SIMULAÇÃO – não oficial'}
    return {'BR':nacional, **total_uf},hist
