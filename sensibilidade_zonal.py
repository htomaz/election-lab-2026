"""Faixas de sensibilidade, não intervalos estatísticos de confiança.

Votos apurados são fixos. Para o eleitorado ainda não processado,
testa +/- mudança no comparecimento e +/- mudança na preferência
bilateral por candidato dos votos restantes. Não simula vantagem
política específica de eleitores que passam a comparecer.
"""
from __future__ import annotations
from math import isfinite


def projetar_cenario(linhas, desvio_comparecimento_pp=0.,
                     desvio_lula_pp=0.):
    if not (-10<=desvio_comparecimento_pp<=10 and
            -15<=desvio_lula_pp<=15):
        raise ValueError('Cenário fora dos limites conservadores')
    totais={'lula':0.,'flavio':0.,'validos':0.,
            'zonas_sem_dados_participacao':0,
            'zonas_com_dados_participacao':0}
    for r in linhas:
        l=float(r['lula_apurado'])
        f=float(r['flavio_apurado'])
        v=float(r['validos_apurados'])
        faltante=max(0.,float(r['validos_restantes_estimados']))
        if any(not isfinite(z) or z<0 for z in (l,f,v,faltante)) or l+f>v:
            raise ValueError('Votos negativos ou inconsistentes na zona')
        parte=r.get('participacao')
        if parte is not None:
            totais['zonas_com_dados_participacao']+=1
            aptos_rest=float(parte['aptos_restantes'])
            validade=float(parte['taxa_validos_estimada_restante'])
            comp=float(parte['taxa_comparecimento_estimada_restante'])
            t=max(0.,min(1.,comp+desvio_comparecimento_pp/100))
            # Recalcula volume somente sobre eleitorado NÃO processado.
            faltante=aptos_rest*t*validade
        else:
            totais['zonas_sem_dados_participacao']+=1
        rem_l=float(r['lula_projetado'])-l
        rem_f=float(r['flavio_projetado'])-f
        total_base=max(0.,rem_l+rem_f)
        peso_l=rem_l/total_base if total_base else .5
        peso_l=max(0.,min(1.,peso_l+desvio_lula_pp/100))
        totais['lula']+=l+faltante*peso_l
        totais['flavio']+=f+faltante*(1-peso_l)
        totais['validos']+=l+f+faltante
    den=totais['lula']+totais['flavio']
    totais['lula_pct']=100*totais['lula']/den if den else None
    totais['flavio_pct']=100*totais['flavio']/den if den else None
    totais['tipo']='cenário de estresse; não intervalo de confiança'
    return totais


def faixa_sensibilidade(linhas, choque_comparecimento_pp=2.,
                         choque_preferencia_pp=3.):
    if not 0<=choque_comparecimento_pp<=10 or not 0<=choque_preferencia_pp<=15:
        raise ValueError('Choques de estresse inválidos')
    central=projetar_cenario(linhas,0,0)
    cenarios=[]
    for c in (-choque_comparecimento_pp,0,choque_comparecimento_pp):
        for p in (-choque_preferencia_pp,0,choque_preferencia_pp):
            cenarios.append({'choque_comparecimento_pp':c,
                             'choque_preferencia_pp':p,
                             **projetar_cenario(linhas,c,p)})
    validos=[x for x in cenarios if x['lula_pct'] is not None]
    return {
        'central':central,'cenarios':cenarios,
        'lula_min_pct':min((x['lula_pct'] for x in validos),default=None),
        'lula_max_pct':max((x['lula_pct'] for x in validos),default=None),
        'flavio_min_pct':min((x['flavio_pct'] for x in validos),default=None),
        'flavio_max_pct':max((x['flavio_pct'] for x in validos),default=None),
        'limite':('Faixa ilustrativa de nove combinações de choques, '
                  'não é intervalo probabilístico nem estimativa de '
                  'probabilidade de vitória.')
    }
