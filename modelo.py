"""Projeção experimental ponderada por UF, sem extrapolar uma parcial nacional ingênua.

Usa a participação Lula / (Lula + Flávio) do primeiro turno de 2026 e,
como referência secundária, Lula / (Lula + Bolsonaro) do segundo turno de 2022.
Não usa a identidade de Bolsonaro como equivalente a Flávio: é apenas um proxy
histórico sujeito a divergências relevantes.
"""
from __future__ import annotations
import csv
from pathlib import Path
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
    if validos <= 0 or (a and a['validos'] < a['lula'] + a['direita']):return None
    return {'prior':ratio,'volume':validos,'tem_2026':a is not None,'tem_2022':b is not None}



def _perfil_restante_comparavel(historicos_uf, perfil_uf, peso_2026):
    """Perfis históricos do conjunto APURADO e do conjunto REMANESCENTE.

    Somente perfis territoriais reconciliados devem ser utilizados. Cada
    período usa a participação nos votos dos DOIS candidatos, inclusive
    no histórico de 2026T1 (sem terceiros no denominador da preferência).
    Se faltar período/consistência, retorna None e mantém estimador legado.
    """
    if not isinstance(perfil_uf, dict):
        return None
    valores = []
    pesos = []
    for periodo, peso in [((2026, 1), peso_2026), ((2022, 2), 1-peso_2026)]:
        origem = historicos_uf.get(periodo)
        if not origem or origem['lula'] + origem['direita'] <= 0:
            continue
        # É obrigatório apresentar o MESMO universo territorial nos dois
        # períodos usados; não utilizar parcialmente uma base ausente.
        rec = perfil_uf.get(periodo)
        if not isinstance(rec, dict):
            return None
        try:
            lo, do = (int(rec[c]) for c in ('lula_apurado_hist', 'direita_apurado_hist'))
            lt, dt = (int(rec[c]) for c in ('lula_total_hist', 'direita_total_hist'))
        except (TypeError, KeyError, ValueError, OverflowError):
            return None
        if (min(lo, do, lt, dt) < 0 or lo > lt or do > dt or
            lt != origem['lula'] or dt != origem['direita']):
            return None
        obs, resto = lo+do, lt+dt-lo-do
        if obs <= 0 or resto <= 0:
            return None
        valores.append((lo/obs, (lt-lo)/resto))
        pesos.append(peso)
    if not valores or sum(pesos) <= 0:
        return None
    return (sum(w*v[0] for v,w in zip(valores,pesos))/sum(pesos),
            sum(w*v[1] for v,w in zip(valores,pesos))/sum(pesos))


def projetar_locais(localidades, historico, peso_2026=.75, ajuste_volume=1.,
                    intensidade=.35, composicao_historica=None):
    """Sem dados completos de todas as localidades, retorna projeção parcial com coverage.

    Para cada UF: votos já contados + votos remanescentes ponderados pelo prior da UF.
    Residual da parcial estadual é limitado e encolhido conforme progresso; não é
    um estimador calibrado por zona, e a heterogeneidade intraestadual persiste.
    """
    linhas=[]
    faltantes=[]
    composicao_historica = composicao_historica or {}
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
        # Com todas as seções totalizadas, o resultado observado prevalece.
        # Não projetar votos remanescentes quando a apuração local acabou.
        if total_secoes > 0 and secoes >= total_secoes:
            pred_total = obs_v
        else:
            pred_total = None
        if pred_total is None and p and obs_v:
            extrapolacao = obs_v / p
            # evitar extrapolação extrema nas primeiras seções
            peso_observado = .30*min(1.,p/.15)
            pred_total=max(obs_v, historico_validos*(1-peso_observado)+extrapolacao*peso_observado)
        elif pred_total is None:
            pred_total=max(obs_v, historico_validos)
        rem=max(0.,pred_total-obs_v)
        frac_atual=(obs_l/(obs_l+obs_f)) if (obs_l+obs_f) else None
        # Parcial local não é amostra aleatória; limitar variação transmitida.
        # Com dados geográficos reconciliados, separar a composição
        # histórica das localidades JÁ apuradas daquela AINDA não apuradas.
        # Não impor uma reversão artificial do viés: o swing é estimado
        # comparando o observado com o seu próprio histórico territorial.
        perfil = composicao_historica.get(uf)
        conciliado = (isinstance(perfil,dict) and
                      perfil.get('lula_atual') == obs_l and
                      perfil.get('flavio_atual') == obs_f)
        referencia_territorial = (_perfil_restante_comparavel(
            historico.get(uf, {}), perfil.get('periodos'), peso_2026)
            if conciliado else None)
        prioridade_obs = (referencia_territorial[0]
                         if referencia_territorial else ref['prior'])
        prioridade_rem = (referencia_territorial[1]
                         if referencia_territorial else ref['prior'])
        delta=0.0 if frac_atual is None else max(-.08,min(.08,frac_atual-prioridade_obs))
        ganho=min(1.,p/.25)*intensidade
        share_rem=max(.02,min(.98,prioridade_rem+ganho*delta))
        proj_l=obs_l+rem*share_rem
        proj_f=obs_f+rem*(1-share_rem)
        linhas.append({'UF':uf,'Apuração (%)':p*100,'Votos válidos apurados':obs_v,
                       'Lula apurado':obs_l,'Flávio apurado':obs_f,
                       'Lula projetado':proj_l,'Flávio projetado':proj_f,
                       'Votos válidos projetados':proj_l+proj_f,
                       'Lula projeção (%)':100*proj_l/(proj_l+proj_f) if proj_l+proj_f else None,
                       'Lula histórico (%)':100*ref['prior'],
                       'Perfil geográfico validado':referencia_territorial is not None,
                       'Histórico restante Lula (%)':100*prioridade_rem,
                       'Base 2026':ref['tem_2026'],'Base 2022':ref['tem_2022']})
    total_l=sum(x['Lula projetado'] for x in linhas)
    total_f=sum(x['Flávio projetado'] for x in linhas)
    return {'linhas':linhas,'faltantes':faltantes,'completo':len(linhas)==len(UFS),
            'lula':total_l,'flavio':total_f,
            'lula_pct':100*total_l/(total_l+total_f) if total_l+total_f else None,
            'flavio_pct':100*total_f/(total_l+total_f) if total_l+total_f else None,
            'somente_2022':[r['UF'] for r in linhas if not r['Base 2026']]}
