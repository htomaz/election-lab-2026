"""Camada opcional de volume eleitoral por zona: aptos -> comparecimento -> votos.

NÃO presume que comparecimento observado nas seções contabilizadas represente
todas as seções da zona. Ajustes são conservadores e sem calibração externa.
A distribuição partidária de eleitores que mudam o comparecimento não é
identificável a partir destes agregados, exigindo cenários de sensibilidade.
"""
from __future__ import annotations
from math import isfinite

PERIODOS = ((2026,1),(2022,2))


def limitar(x, inf, sup):
    return max(inf,min(sup,x))


def _taxas(row):
    if not row:
        return None
    aptos, c, v = [int(row[k]) for k in ('aptos','comparecimento','validos')]
    b,n=[int(row[k]) for k in ('brancos','nulos')]
    if aptos<=0 or c<0 or c>aptos or v<0 or v>c or b<0 or n<0 or v+b+n>c:
        return None
    # Em regiões pequenas é possível uma zona ter 0 comparecimento.
    return {'turnout':c/aptos,
            'valid':v/c if c else 0.,
            'blank':b/c if c else 0.,
            'null':n/c if c else 0.,
            'aptos':aptos}


def referencia_historica(registro,peso_2026=.75):
    """Retorna taxas historicamente comparáveis, não eleitores absolutos."""
    if not 0<=peso_2026<=1:
        raise ValueError('Peso histórico inválido')
    a=_taxas(registro.get((2026,1))) if registro else None
    b=_taxas(registro.get((2022,2))) if registro else None
    if a is None and b is None:
        return None
    if a is not None and b is not None:
        primeiro_22=_taxas(registro.get((2022,1)))
        taxas={}
        for k in ('turnout','valid','blank','null'):
            taxa26=a[k]
            if primeiro_22 is not None:
                # Mudança entre turnos de 2022 ajuda a estimar uma
                # diferença de comparecimento do 1º para o 2º turno.
                # Não transportar integralmente o desvio histórico.
                max_delta = .12 if k=='turnout' else (.08 if k=='valid' else .04)
                transicao=limitar(b[k]-primeiro_22[k],-max_delta,max_delta)
                taxa26=limitar(taxa26+.5*transicao,0.,1.)
            taxas[k]=limitar(peso_2026*taxa26+(1-peso_2026)*b[k],0.,1.)
        soma=taxas['valid']+taxas['blank']+taxas['null']
        if soma>1:
            taxa_invalidos=taxas['blank']+taxas['null']
            if taxa_invalidos:
                fator=max(0.,1-taxas['valid'])/taxa_invalidos
                taxas['blank']*=fator
                taxas['null']*=fator
        return taxas | {
            'aptos':a['aptos'],
            'origem':('2026T1 + 2022T2 + transição 2022T1→T2'
                      if primeiro_22 is not None else '2026T1 + 2022T2')}
    escolhido=a or b
    return {k:escolhido[k] for k in ('turnout','valid','blank','null','aptos')} | {
        'origem':'2026T1' if a else '2022T2'}


def estimar_volume_zona(registro,observado=None,peso_2026=.75,
                        intensidade=.35,ajuste_eleitorado=1.,
                        ajuste_taxas_uf=None):
    """Estima volume final preservando parciais oficiais sem contá-las duas vezes.

    Em tempo real, observa e.te, e.est, e.c, e.a, v.vv, v.vb, v.tvn.
    Sem e.est quando existem votos, recusa extrapolação baseada em participação
    para evitar falsa atribuição dos eleitores ainda não processados.
    """
    prior=referencia_historica(registro,peso_2026)
    if prior is None:
        return None
    if not 0<=intensidade<=1 or not .5<=ajuste_eleitorado<=1.5:
        raise ValueError('Parâmetros de comparecimento inválidos')
    x=observado or {}
    votos_obs=int(x.get('validos',0))
    l=int(x.get('lula',0)); d=int(x.get('flavio',0))
    if votos_obs<l+d:
        raise ValueError('Votos do candidato superam votos válidos')
    aptos_atual=x.get('aptos')
    aptos=float(aptos_atual if aptos_atual is not None else prior['aptos']*ajuste_eleitorado)
    if aptos<0 or not isfinite(aptos):
        raise ValueError('Eleitorado total inválido')
    total_secoes=int(x.get('secoes_total',0))
    secoes=int(x.get('secoes',0))
    processados=x.get('aptos_processados')
    comparecimento=x.get('comparecimento')
    abstencoes=x.get('abstencoes')
    brancos=x.get('brancos')
    nulos=x.get('nulos')
    if any(z is not None and float(z)<0 for z in
           (processados,comparecimento,abstencoes,brancos,nulos)):
        raise ValueError('Valores de abstenção ou votos negativos')
    if (secoes<0 or total_secoes<0 or
        total_secoes>0 and secoes>total_secoes):
        raise ValueError('Progresso de seções inválido')
    if (processados is None or comparecimento is None or abstencoes is None or
        brancos is None or nulos is None):
        if votos_obs or secoes:
            return None
        # Atribui zero observado em zonas ainda não consultadas.
        processados=comparecimento=abstencoes=brancos=nulos=0
    processados=float(processados)
    comparecimento=float(comparecimento)
    abstencoes=float(abstencoes)
    brancos=float(brancos)
    nulos=float(nulos)
    if (comparecimento+abstencoes>processados+1 or
        votos_obs+brancos+nulos>comparecimento+1 or
        processados>aptos+1):
        raise ValueError('Eleitorado e votos observados incompatíveis')
    # Não estimar participação adicional em zona concluída.
    if total_secoes>0 and secoes==total_secoes:
        faltantes=0.
    else:
        faltantes=max(0.,aptos-processados)
    cobertura=limitar(processados/max(1.,aptos),0.,1.)
    # Em uma parcial territorial enviesada, jamais transmitir todo o
    # desvio de turnout ou válidos: fatores limitados a 35% padrão.
    ganho=intensidade*min(1.,cobertura/.25)
    # Ajuste agregado apenas com zonas OFICIALMENTE observadas da mesma
    # UF. É limitado/encolhido antes de chegar aqui; não transfere
    # automaticamente uma zona atípica para o restante do estado.
    a_uf=ajuste_taxas_uf or {}
    taxa_t=limitar(prior['turnout']+a_uf.get('turnout',0.),0.,1.)
    taxa_v=limitar(prior['valid']+a_uf.get('valid',0.),0.,1.)
    taxa_b=limitar(prior['blank']+a_uf.get('blank',0.),0.,1.)
    taxa_n=limitar(prior['null']+a_uf.get('null',0.),0.,1.)
    if processados>0:
        turnout_obs=comparecimento/processados
        taxa_t=limitar(prior['turnout']+
                       ganho*limitar(turnout_obs-taxa_t,-.12,.12),0.,1.)
    if comparecimento>0:
        valid_obs=votos_obs/comparecimento
        taxa_v=limitar(prior['valid']+
                       ganho*limitar(valid_obs-taxa_v,-.08,.08),0.,1.)
        taxa_b=limitar(prior['blank']+
                       ganho*limitar(brancos/comparecimento-taxa_b,-.06,.06),0.,1.)
        taxa_n=limitar(prior['null']+
                       ganho*limitar(nulos/comparecimento-taxa_n,-.06,.06),0.,1.)
    # Distribuição mutuamente exclusiva: nenhuma categoria pode exceder
    # os presentes previstos.
    if taxa_v+taxa_b+taxa_n>1:
        total_invalidos=taxa_b+taxa_n
        limite_invalidos=max(0.,1-taxa_v)
        taxa_b=limite_invalidos*taxa_b/max(1e-10,total_invalidos)
        taxa_n=limite_invalidos*taxa_n/max(1e-10,total_invalidos)
    comp_rest=faltantes*taxa_t
    validos_rest=comp_rest*taxa_v
    branco_rest=comp_rest*taxa_b
    nulo_rest=comp_rest*taxa_n
    inval_outros=comp_rest-validos_rest-branco_rest-nulo_rest
    observado_outros=max(0.,comparecimento-votos_obs-brancos-nulos)
    return {
        'fonte_volume':'aptos_x_comparecimento_x_validade',
        'prior_origem':prior['origem'],
        'aptos_estimados':aptos,
        'aptos_processados':processados,
        'aptos_restantes':faltantes,
        'taxa_comparecimento_historica':prior['turnout'],
        'taxa_comparecimento_estimada_restante':taxa_t,
        'taxa_validos_historica':prior['valid'],
        'taxa_validos_estimada_restante':taxa_v,
        'comparecimento_observado':comparecimento,
        'abstencoes_observadas':abstencoes,
        'brancos_observados':brancos,
        'nulos_observados':nulos,
        'comparecimento_final_estimado':comparecimento+comp_rest,
        'abstencoes_finais_estimadas':abstencoes+faltantes*(1-taxa_t),
        'brancos_finais_estimados':brancos+branco_rest,
        'nulos_finais_estimados':nulos+nulo_rest,
        'outros_invalidos_finais_estimados':observado_outros+max(0.,inval_outros),
        'validos_finais_estimados':votos_obs+validos_rest,
        'validos_restantes_estimados':validos_rest,
        'ganho_taxas':ganho,
        'ajuste_uf_incorporado':{k:float(a_uf.get(k,0.)) for k in
                                ('turnout','valid','blank','null')},
    }


def cenarios_eleitores_marginais(estimativa_volume,p_lula=.5,
                                comparticipacao=(.3,.5,.7)):
    """Sensibilidade, NÃO identifica preferência dos novos comparecentes.

    Assume mudança na taxa de comparecimento em relação ao prior e
    aplica cenários à parcela marginal dos votos ainda não observados.
    """
    if not 0<=p_lula<=1:
        raise ValueError('Participação de Lula inválida')
    aptos_f=estimativa_volume['aptos_restantes']
    dt=(estimativa_volume['taxa_comparecimento_estimada_restante']-
        estimativa_volume['taxa_comparecimento_historica'])
    extra=aptos_f*dt*estimativa_volume['taxa_validos_estimada_restante']
    return [{'lula_entre_marginais':q,
             'mudanca_validos_por_comparecimento':extra,
             'efeito_lula_vs_distribuicao_base':extra*(q-p_lula),
             'efeito_flavio_vs_distribuicao_base':-extra*(q-p_lula)}
            for q in comparticipacao if 0<=q<=1]
