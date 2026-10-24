"""Estimativa territorial exploratória: histórico por município e zona.

As zonas não consultadas NÃO são consideradas apuradas. Dados de 2026T1 são
utilizados apenas como histórico na previsão de 2026T2. Não substitui o EA20
nacional por soma de consultas parciais a zonas.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv
from modelo_participacao import estimar_volume_zona


def carregar_zonas(caminho='historico_zonas.csv'):
    dados = defaultdict(dict)
    with Path(caminho).open(newline='', encoding='utf-8-sig') as f:
        leitor = csv.DictReader(f)
        campos = {'uf','municipio','zona','ano','turno','lula','direita','validos'}
        if not campos.issubset(leitor.fieldnames or []):
            raise ValueError('Colunas insuficientes no histórico por zona')
        for r in leitor:
            chave = (r['uf'].upper(), r['municipio'].zfill(5), r['zona'].zfill(4))
            periodo = (int(r['ano']),int(r['turno']))
            if periodo not in ((2022,2),(2026,1)) or periodo in dados[chave]:
                raise ValueError(f'Período inválido ou chave duplicada: {chave} {periodo}')
            valores = {c:int(r[c]) for c in ('lula','direita','validos')}
            if min(valores.values()) < 0 or valores['lula']+valores['direita'] > valores['validos']:
                raise ValueError(f'Votação inválida: {chave} {periodo}')
            dados[chave][periodo] = valores
    return dict(dados)


def prior_zona(registro,peso):
    a,b=registro.get((2026,1)),registro.get((2022,2))
    def proporcao(x):
        return x['lula']/(x['lula']+x['direita']) if x and x['lula']+x['direita'] else None
    pa,pb=proporcao(a),proporcao(b)
    if pa is None and pb is None:return None
    p=peso*pa+(1-peso)*pb if pa is not None and pb is not None else (pa if pa is not None else pb)
    return p,(a or b)['validos']


def projetar_zonas(observadas,historicos,peso_2026=.75,ajuste_volume=1.,
                  intensidade=.35,universo=None,participacao=None):
    """observadas: {(UF, mun5, zona4): {'lula','flavio','validos','secoes','secoes_total'}}.

    Universo, quando fornecido, é um cadastro de zonas da eleição-alvo sem
    votos futuros. Para o backtest, permite excluir zonas extintas de 2022.
    """
    if not 0<=peso_2026<=1 or ajuste_volume<=0 or not 0<=intensidade<=1:
        raise ValueError('Parâmetros inválidos')
    refs={k:p for k,r in historicos.items() if (p:=prior_zona(r,peso_2026)) is not None and p[1]>0}
    nuf=defaultdict(float);vuf=defaultdict(float);countuf=defaultdict(int)
    for (uf,_,_),(p,v) in refs.items():
        nuf[uf]+=p*v;vuf[uf]+=v;countuf[uf]+=1
    ufp={uf:nuf[uf]/v for uf,v in vuf.items() if v}
    chaves=(set(universo) if universo is not None else set(refs)) | set(observadas)
    linhas=[];estad=defaultdict(lambda:{'observados':0.,'residuo':0.,'esperados':0.})
    for chave in sorted(chaves):
        uf=chave[0]
        # Zonas novas: peso médio histórico estadual, sem inventar votos.
        p,volume=refs.get(chave,(ufp.get(uf,.5),vuf.get(uf,0)/max(1,countuf[uf])))
        x=observadas.get(chave,{})
        l,d=max(0,int(x.get('lula',0))),max(0,int(x.get('flavio',0)))
        v=int(x.get('validos',l+d))
        s,ts=int(x.get('secoes',0)),int(x.get('secoes_total',0))
        if v<l+d or s<0 or ts<0 or (ts and s>ts):
            raise ValueError(f'Parcial inconsistente: {chave}')
        progress=s/ts if ts else 0
        esperado=volume*ajuste_volume
        if ts and s==ts:total=v
        elif progress and v:
            peso=.30*min(1.,progress/.15)
            total=max(v,(1-peso)*esperado+peso*v/progress)
        else:total=max(v,esperado)
        # Estimador por eleitorado, comparecimento e validade prevalece quando
        # existe histórico zonal auditado e EA20 suficientemente detalhado.
        detalhe = None
        if participacao:
            detalhe=estimar_volume_zona(participacao.get(chave,{}),x,
                                        peso_2026=peso_2026,
                                        intensidade=intensidade,
                                        ajuste_eleitorado=ajuste_volume)
            if detalhe is not None:
                total=max(v,detalhe['validos_finais_estimados'])
        faltante=max(0.,total-v)
        par=l+d
        if par and chave in refs:
            residuo=max(-.15,min(.15,l/par-p))
            estad[uf]['observados']+=par
            estad[uf]['residuo']+=par*residuo
        estad[uf]['esperados']+=volume
        linhas.append((chave,p,volume,l,d,v,faltante,progress,ts,detalhe))
    swing={}
    for uf,x in estad.items():
        cobertura=min(1.,x['observados']/max(1.,x['esperados']))
        confianca=min(.75,.10+.90*cobertura)
        swing[uf]=intensidade*confianca*x['residuo']/max(1.,x['observados'])
    por_uf=defaultdict(lambda:{'lula':0.,'flavio':0.,'apurados':0,
                                 'projetados':0.,'zonas_observadas':0,'zonas_total':0})
    saida=[]
    for chave,p,volume,l,d,v,faltante,progress,ts,detalhe in linhas:
        uf=chave[0];frac=max(.01,min(.99,p+swing.get(uf,0)))
        pl=l+faltante*frac;pf=d+faltante*(1-frac)
        a=por_uf[uf];a['lula']+=pl;a['flavio']+=pf;a['apurados']+=v
        a['projetados']+=pl+pf;a['zonas_total']+=1
        if chave in observadas:a['zonas_observadas']+=1
        saida.append({'uf':uf,'municipio':chave[1],'zona':chave[2],
                      'lula_apurado':l,'flavio_apurado':d,'validos_apurados':v,
                      'secoes':int(round(progress*ts)),'secoes_total':ts,
                      'lula_projetado':pl,'flavio_projetado':pf,
                      'validos_projetados':pl+pf,'lula_historico_pct':100*p,
                      'lula_projetado_pct':100*pl/(pl+pf) if pl+pf else None,
                      'historico_disponivel':chave in refs,
                      'modelo_volume':('participacao' if detalhe else 'validos_historicos'),
                      'participacao':detalhe,
                      'validos_restantes_estimados':faltante,
                      'abstencoes_finais_estimadas':(
                          detalhe['abstencoes_finais_estimadas'] if detalhe else None),
                      'brancos_finais_estimados':(
                          detalhe['brancos_finais_estimados'] if detalhe else None),
                      'nulos_finais_estimados':(
                          detalhe['nulos_finais_estimados'] if detalhe else None),
                      'comparecimento_final_estimado':(
                          detalhe['comparecimento_final_estimado'] if detalhe else None)})
    nl=sum(x['lula'] for x in por_uf.values())
    nf=sum(x['flavio'] for x in por_uf.values())
    return {'linhas':saida,'por_uf':dict(por_uf),'lula':nl,'flavio':nf,
            'lula_pct':100*nl/(nl+nf) if nl+nf else None,
            'flavio_pct':100*nf/(nl+nf) if nl+nf else None,
            'swing_estadual':swing}
