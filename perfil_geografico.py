"""Perfil geográfico verificável para corrigir composição no modelo por UF.

SÓ autoriza a correção se zonas EA20 6258 já CONCLUÍDAS (não apenas
parcialmente apuradas) coincidirem exatamente com as somas oficiais da UF.
Assim, a preferência histórica dos locais não apurados não é inventada.
"""
from collections import defaultdict


def compor_perfis_conciliados(brutos_uf, snapshot, historico_zonas):
    if (not isinstance(snapshot, dict) or snapshot.get('versao') != 1 or
        snapshot.get('eleicao') != 6258 or
        snapshot.get('catalogo_origem') != 'EA16_TSE_3221'):
        return {}
    catalogo = snapshot.get('catalogo')
    obs = snapshot.get('observacoes')
    if not isinstance(catalogo, list) or not isinstance(obs, dict):
        return {}
    # As listas oficiais têm ~6.292 zonas. Não aprovar um catálogo reduzido
    # que se identifica indevidamente como "EA16".
    catalogo_ids=set()
    for item in catalogo:
        try:
            ident=(str(item['uf']).upper(), str(item['municipio']).zfill(5),
                   str(item['zona']).zfill(4))
        except (KeyError, TypeError, AttributeError):
            return {}
        if ident in catalogo_ids:
            return {}
        catalogo_ids.add(ident)
    if not 6000 <= len(catalogo_ids) <= 10000:
        return {}

    agrupados=defaultdict(lambda:{'lula':0,'flavio':0,'validos':0,
                                   'chaves':set(),'aceitavel':True})
    for identificador, dado in obs.items():
        try:
            chave=tuple(identificador.split('|'))
            if len(chave)!=3 or chave not in catalogo_ids or not isinstance(dado,dict):
                return {}
            uf=chave[0]
            if (dado.get('fase','o')!='o' or
                str(dado.get('turno',2))!='2'):
                agrupados[uf]['aceitavel']=False
                continue
            s=int(dado['secoes']); total=int(dado['secoes_total'])
            l=int(dado['lula']); f=int(dado['flavio']); v=int(dado['validos'])
            if (min(s,total,l,f,v)<0 or total<=0 or s>total or l+f>v):
                agrupados[uf]['aceitavel']=False
                continue
            # Sem seção a seção histórica, não assumir que as seções
            # restantes da MESMA zona têm o mesmo perfil das apuradas.
            if s!=total:
                agrupados[uf]['aceitavel']=False
                continue
            g=agrupados[uf]
            g['lula']+=l;g['flavio']+=f;g['validos']+=v
            g['chaves'].add(chave)
        except (TypeError,ValueError,KeyError,AttributeError):
            return {}

    resultado={}
    totais_hist=defaultdict(lambda:defaultdict(lambda:{'lula':0,'direita':0}))
    for chave,periodos in historico_zonas.items():
        for periodo,x in periodos.items():
            if periodo not in ((2022,2),(2026,1)):
                continue
            totais_hist[chave[0]][periodo]['lula']+=x['lula']
            totais_hist[chave[0]][periodo]['direita']+=x['direita']

    for uf,g in agrupados.items():
        atual=brutos_uf.get(uf)
        if (not g['aceitavel'] or not g['chaves'] or not isinstance(atual,dict) or
            g['lula']!=atual.get('lula') or g['flavio']!=atual.get('flavio') or
            g['validos']!=atual.get('validos')):
            continue
        periodos={}
        for periodo in ((2022,2),(2026,1)):
            total_hist=totais_hist[uf].get(periodo)
            if not total_hist:
                break
            somas={'lula_apurado_hist':0,'direita_apurado_hist':0,
                   'lula_total_hist':total_hist['lula'],
                   'direita_total_hist':total_hist['direita']}
            for chave in g['chaves']:
                base=historico_zonas.get(chave,{}).get(periodo)
                if base:
                    somas['lula_apurado_hist']+=base['lula']
                    somas['direita_apurado_hist']+=base['direita']
            periodos[periodo]=somas
        # O helper no modelo valida totais, cobertura e períodos.
        if periodos:
            resultado[uf]={'lula_atual':g['lula'],
                           'flavio_atual':g['flavio'],
                           'periodos':periodos}
    return resultado
