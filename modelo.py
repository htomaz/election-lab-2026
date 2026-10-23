"""Projeção experimental ponderada por UF, sem extrapolar uma parcial nacional ingênua.

Usa a participação Lula / (Lula + Flávio) do primeiro turno de 2026 e,
como referência secundária, Lula / (Lula + Bolsonaro) do segundo turno de 2022.
Não usa a identidade de Bolsonaro como equivalente a Flávio: é apenas um proxy
histórico sujeito a divergências relevantes.
"""
from __future__ import annotations
import csv
from pathlib import Path
from math import sqrt
from tse import UFS

COLS = ['uf','ano','turno','lula','direita','validos']


def carregar_historico(caminho=None):
    if caminho is None:
        caminho = next((p for p in (Path('historico_ufs.csv'), Path('data/historico_ufs.csv')) if p.exists()), Path('historico_ufs.csv'))
    refs = {}
    if not Path(caminho).exists():
        return refs
    with open(caminho, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            try:
                uf,ano,turno=row['uf'].upper(),int(row['ano']),int(row['turno'])
                if uf not in UFS: continue
                refs.setdefault(uf,{})[(ano,turno)] = {
                    'lula':int(row['lula']), 'direita':int(row['direita']),
                    'validos':int(row['validos'])}
            except (KeyError,ValueError,TypeError):
                continue
    return refs


def base_uf(uf, refs, peso_2026=0.75):
    d=refs.get(uf,{})
    a=d.get((2026,1))
    b=d.get((2022,2))
    ratio_a = a['lula']/(a['lula']+a['direita']) if a and a['lula']+a['direita']>0 else None
    ratio_b = b['lula']/(b['lula']+b['direita']) if b and b['lula']+b['direita']>0 else None
    if ratio_a is None and ratio_b is None: return None
    if ratio_a is not None and ratio_b is not None:
        ratio=peso_2026*ratio_a+(1-peso_2026)*ratio_b
    else: ratio=ratio_a if ratio_a is not None else ratio_b
    validos=(a or b)['validos']
    if validos <= 0:return None
    return {'prior':ratio,'volume':validos,'tem_2026':a is not None,'tem_2022':b is not None}


def projetar_locais(localidades, historico, peso_2026=.75, ajuste_volume=1., intensidade=.35):
    """Sem dados completos de todas as localidades, retorna projeção parcial com coverage.

    Para cada UF: votos já contados + votos remanescentes ponderados pelo prior da UF.
    Residual da parcial estadual é limitado e encolhido conforme progresso; não é
    um estimador calibrado por zona, e a heterogeneidade intraestadual persiste.
    """
    linhas=[]
    faltantes=[]
    for uf in UFS:
        ref = base_uf(uf,historico,peso_2026)
        if ref is None:
            faltantes.append(uf)
            continue
        x = localidades.get(uf, {})
        obs_l=max(0,int(x.get('lula',0)))
        obs_f=max(0,int(x.get('flavio',0)))
        obs_v=max(0,int(x.get('validos',obs_l+obs_f)))
        secoes=int(x.get('secoes',0))
        total_secoes=int(x.get('secoes_total',0))
        p=secoes/total_secoes if total_secoes else 0.0
        p=min(1.,max(0.,p))
        historico_validos=ref['volume']*ajuste_volume
        if p and obs_v:
            extrapolacao = obs_v / p
            # evitar extrapolação extrema nas primeiras seções
            peso_observado = .30*min(1.,p/.15)
            pred_total=max(obs_v, historico_validos*(1-peso_observado)+extrapolacao*peso_observado)
        else:
            pred_total=historico_validos
        rem=max(0.,pred_total-obs_v)
        frac_atual=(obs_l/(obs_l+obs_f)) if (obs_l+obs_f) else None
        # Parcial local não é amostra aleatória; limitar variação transmitida.
        delta=0.0 if frac_atual is None else max(-.08,min(.08,frac_atual-ref['prior']))
        ganho=min(1.,p/.25)*intensidade
        share_rem=max(.02,min(.98,ref['prior']+ganho*delta))
        proj_l=obs_l+rem*share_rem
        proj_f=obs_f+rem*(1-share_rem)
        linhas.append({'UF':uf,'Apuração (%)':p*100,'Votos válidos apurados':obs_v,
                       'Lula apurado':obs_l,'Flávio apurado':obs_f,
                       'Lula projetado':proj_l,'Flávio projetado':proj_f,
                       'Votos válidos projetados':proj_l+proj_f,
                       'Lula projeção (%)':100*proj_l/(proj_l+proj_f) if proj_l+proj_f else None,
                       'Lula histórico (%)':100*ref['prior'],
                       'Base 2026':ref['tem_2026'],'Base 2022':ref['tem_2022']})
    total_l=sum(x['Lula projetado'] for x in linhas)
    total_f=sum(x['Flávio projetado'] for x in linhas)
    return {'linhas':linhas,'faltantes':faltantes,'completo':len(linhas)==len(UFS),
            'lula':total_l,'flavio':total_f,
            'lula_pct':100*total_l/(total_l+total_f) if total_l+total_f else None,
            'flavio_pct':100*total_f/(total_l+total_f) if total_l+total_f else None,
            'somente_2022':[r['UF'] for r in linhas if not r['Base 2026']]}
