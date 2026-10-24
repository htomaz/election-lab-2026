"""Estimativa territorial exploratória: histórico por município e zona.

As zonas não consultadas NÃO são consideradas apuradas. Dados de 2026T1 são
utilizados apenas como histórico na previsão de 2026T2. Não substitui o EA20
nacional por soma de consultas parciais a zonas.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv
from modelo_participacao import estimar_volume_zona, referencia_historica


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



def calibrar_taxas_uf_observadas(observadas, participacao, peso_2026=.75,
                               intensidade=.35):
    """Encolhe desvios de taxas com dados de zonas efetivamente observadas.

    Usa apenas EA20 revelado e histórico de cada zona. Nenhum voto
    futuro entra no ajuste. Não é calibração retrospectiva de parâmetros.
    """
    from collections import defaultdict
    from math import sqrt
    limites={'turnout':.12,'valid':.08,'blank':.06,'null':.06}
    grupos=defaultdict(lambda:{k:[0.,0.] for k in limites})
    for chave,x in observadas.items():
        prior=referencia_historica(participacao.get(chave,{}),peso_2026)
        if not prior:
            continue
        campos=('aptos_processados','comparecimento','validos','brancos','nulos')
        if any(x.get(k) is None for k in campos):
            continue
        ap=int(x['aptos_processados'])
        comp=int(x['comparecimento'])
        s=int(x.get('secoes',0));ts=int(x.get('secoes_total',0))
        if ap<=0 or comp<=0 or ts<=0 or s<=0 or s>ts:
            continue
        if comp>ap or int(x['validos'])+int(x['brancos'])+int(x['nulos'])>comp:
            continue
        maturidade=sqrt(s/ts)
        atuais={'turnout':comp/ap,'valid':int(x['validos'])/comp,
                'blank':int(x['brancos'])/comp,'null':int(x['nulos'])/comp}
        for k in limites:
            peso=(ap if k=='turnout' else comp)*maturidade
            dif=max(-limites[k],min(limites[k],atuais[k]-prior[k]))
            grupos[chave[0]][k][0]+=peso*dif
            grupos[chave[0]][k][1]+=peso
    saida={}
    for uf,tipos in grupos.items():
        saida[uf]={}
        for k,(num,den) in tipos.items():
            # shrinkage por equivalente a 100 mil pessoas processadas.
            confianca=min(.65,den/(den+100000)) if den>0 else 0.
            saida[uf][k]=intensidade*confianca*num/max(1.,den)
    return saida

def projetar_zonas(observadas,historicos,peso_2026=.75,ajuste_volume=1.,
                  intensidade=.35,universo=None,participacao=None,
                  peso_correcao_municipal=.25):
    """observadas: {(UF, mun5, zona4): {'lula','flavio','validos','secoes','secoes_total'}}.

    Universo, quando fornecido, é um cadastro de zonas da eleição-alvo sem
    votos futuros. Para o backtest, permite excluir zonas extintas de 2022.
    """
    if (not 0<=peso_2026<=1 or ajuste_volume<=0 or
        not 0<=intensidade<=1 or not 0<=peso_correcao_municipal<=1):
        raise ValueError('Parâmetros inválidos')
    taxas_uf=(calibrar_taxas_uf_observadas(
        observadas,participacao,peso_2026,intensidade)
        if participacao else {})
    refs={k:p for k,r in historicos.items() if (p:=prior_zona(r,peso_2026)) is not None and p[1]>0}
    nuf=defaultdict(float);vuf=defaultdict(float);countuf=defaultdict(int)
    for (uf,_,_),(p,v) in refs.items():
        nuf[uf]+=p*v;vuf[uf]+=v;countuf[uf]+=1
    ufp={uf:nuf[uf]/v for uf,v in vuf.items() if v}
    chaves=(set(universo) if universo is not None else set(refs)) | set(observadas)
    linhas=[]
    estad=defaultdict(lambda:{'observados':0.,'residuo':0.,'esperados':0.})
    mun=defaultdict(lambda:{'observados':0.,'residuo':0.,'esperados':0.})
    diagnostico_uf=defaultdict(lambda:{'historico_lula_obs':0.,'hist_obs_volume':0.,
                                      'historico_lula_total':0.,'hist_total_volume':0.})
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
                                        ajuste_eleitorado=ajuste_volume,
                                        ajuste_taxas_uf=taxas_uf.get(uf))
            if detalhe is not None:
                total=max(v,detalhe['validos_finais_estimados'])
        faltante=max(0.,total-v)
        par=l+d
        # O desvio precisa ser condicionado ao perfil histórico exato da
        # zona observada. A parcial de uma zona tem menor confiabilidade
        # que sua totalização; maturidade é a fração de seções processadas.
        # Isso não substitui histórico SEÇÃO a SEÇÃO, que ainda não existe.
        diagnostico_uf[uf]['historico_lula_total']+=p*volume
        diagnostico_uf[uf]['hist_total_volume']+=volume
        if par and chave in refs:
            maturidade=(progress**.5 if progress else 0.)
            residuo=max(-.15,min(.15,l/par-p))
            peso_efetivo=par*maturidade
            estad[uf]['observados']+=peso_efetivo
            estad[uf]['residuo']+=peso_efetivo*residuo
            mun[chave[:2]]['observados']+=peso_efetivo
            mun[chave[:2]]['residuo']+=peso_efetivo*residuo
            diagnostico_uf[uf]['historico_lula_obs']+=p*volume
            diagnostico_uf[uf]['hist_obs_volume']+=volume
        estad[uf]['esperados']+=volume
        mun[chave[:2]]['esperados']+=volume
        linhas.append((chave,p,volume,l,d,v,faltante,progress,ts,detalhe))
    swing={}
    for uf,x in estad.items():
        cobertura=min(1.,x['observados']/max(1.,x['esperados']))
        confianca=min(.75,.10+.90*cobertura)
        swing[uf]=intensidade*confianca*x['residuo']/max(1.,x['observados'])
    swing_municipal={}
    for chave_m,x in mun.items():
        # Municípios com poucas zonas observadas não impõem a todo o
        # município um desvio forte. Limite de 50% no ganho de confiança.
        cobertura=min(1.,x['observados']/max(1.,x['esperados']))
        confianca=min(.5,.10+.7*cobertura)
        swing_municipal[chave_m]=intensidade*confianca*(
            x['residuo']/max(1.,x['observados']))
    por_uf=defaultdict(lambda:{'lula':0.,'flavio':0.,'apurados':0,
                                 'projetados':0.,'zonas_observadas':0,'zonas_total':0})
    saida=[]
    for chave,p,volume,l,d,v,faltante,progress,ts,detalhe in linhas:
        uf=chave[0]
        # O componente local é complementar e regularizado: nunca
        # substituir integralmente o ajuste estadual pela parcial de
        # um único município com poucas seções.
        peso_m=peso_correcao_municipal if mun[chave[:2]]['observados'] else 0.
        delta=(1-peso_m)*swing.get(uf,0.)+peso_m*swing_municipal.get(chave[:2],0.)
        frac=max(.01,min(.99,p+delta))
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
            'swing_estadual':swing,
            'swing_municipal':swing_municipal,
            'ajuste_comparecimento_uf':taxas_uf,
            'diagnostico_representatividade_uf':{
                uf:{
                    'lula_hist_observadas_pct':100*info['historico_lula_obs']/
                        info['hist_obs_volume'] if info['hist_obs_volume'] else None,
                    'lula_hist_total_pct':100*info['historico_lula_total']/
                        info['hist_total_volume'] if info['hist_total_volume'] else None,
                    'frac_zonas_referenciadas':info['hist_obs_volume']/
                        info['hist_total_volume'] if info['hist_total_volume'] else 0.,
                } for uf,info in diagnostico_uf.items()}}
