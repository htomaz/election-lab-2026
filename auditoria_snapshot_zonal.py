"""Auditoria independente de snapshots zonais frente ao TSE por UF/BR.

Nenhuma soma assincrônica de zonas pode substituir o resultado BR.
Os códigos de UF/município/zona devem existir no catálogo observado.
"""
from __future__ import annotations
from collections import defaultdict

from auditoria_ao_vivo import reconciliar_brasil,reconciliar_zonas
from motor_zonal_completo import chave_zona
from tse import UFS


def auditar_parciais(snapshot,oficiais):
    zonas=defaultdict(dict)
    ids_catalogo=defaultdict(set)
    for c in snapshot.get('catalogo',[]):
        k=chave_zona(c['uf'],c['municipio'],c['zona'])
        ids_catalogo[k[0]].add(k)
    for ident,row in snapshot.get('observacoes',{}).items():
        k=chave_zona(*ident.split('|'))
        if k not in ids_catalogo[k[0]]:
            raise ValueError('Zona não consta no catálogo EA16: '+ident)
        zonas[k[0]][k]=row
    resultado=[]
    for uf in sorted(ids_catalogo):
        ref=oficiais.get(uf)
        r=reconciliar_zonas(zonas[uf],ref,ids_catalogo[uf])
        resultado.append({'UF':uf,'status':r['status'],
                          'mensagem':r['mensagem'],
                          'zonas_consultadas':len(zonas[uf]),
                          'zonas_cadastradas':len(ids_catalogo[uf]),
                          'diferenca_lula':None if r['diferencas'] is None else
                              r['diferencas']['lula'],
                          'diferenca_flavio':None if r['diferencas'] is None else
                              r['diferencas']['flavio'],
                          'diferenca_validos':None if r['diferencas'] is None else
                              r['diferencas']['validos']})
    br=reconciliar_brasil(oficiais,UFS)
    bloqueantes=[x['UF'] for x in resultado if x['status']=='inconsistente']
    if br['status']=='inconsistente':
        bloqueantes.append('BR')
    return {'por_uf':resultado,'nacional':br,
            'bloqueantes':bloqueantes,
            'pode_divulgar_projecao':not bloqueantes,
            'nota':('Snapshots podem ter gerações diferentes. Compatibilidade '
                    'de amostra zonal com UF NÃO prova reconciliação nacional.')}
