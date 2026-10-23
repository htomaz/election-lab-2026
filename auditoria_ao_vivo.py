"""Conciliação conservadora de EA20 zonal com EA20 estadual.

Uma amostra de zonas pode ser COMPATÍVEL com a UF, mas não é a UF.
Arquivos de gerações distintas não são comparáveis como snapshots síncronos.
Nenhuma previsão deve ser apresentada como resultado oficial.
"""
from __future__ import annotations
from datetime import datetime


def _data_geracao(valor):
    if not valor:
        return None
    for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(str(valor).strip(), formato)
        except ValueError:
            pass
    return None


def validar_substituicao(anterior, atual):
    """Impede sobrescrever uma parcial recente por um arquivo mais antigo."""
    if anterior is None:
        return True, 'primeira leitura'
    velho = _data_geracao(anterior.get('geracao'))
    novo = _data_geracao(atual.get('geracao'))
    if velho is not None and (novo is None or novo < velho):
        return False, 'Arquivo de geração anterior ou sem horário'
    # Correções oficiais de votos podem ocorrer, mas a redução de seções
    # totalizadas demanda revisão manual antes de substituir a parcial.
    if int(atual.get('secoes', 0)) < int(anterior.get('secoes', 0)):
        return False, 'Quantidade de seções regrediu'
    return True, 'leitura atualizada'


def reconciliar_zonas(observadas, estadual, universo=None):
    """Confronta somas com o arquivo estadual, sem exigir igualdade da amostra.

    'reconciliado' só é usado quando TODA a população de zonas é conhecida,
    todas as seções estão totalizadas e votos e seções coincidem com a UF.
    A origem do universo deve ser verificada fora desta função (EA12 oficial).
    """
    campos = ('lula','flavio','validos','secoes')
    somas = {k:sum(int(z.get(k, 0)) for z in observadas.values()) for k in campos}
    resultado = {'status':'sem_dados','mensagem':'Sem parcial estadual oficial.',
                 'zonas_consultadas':len(observadas),'totais_amostra':somas,
                 'diferencas':None}
    if estadual is None:
        return resultado
    uf = {k:int(estadual.get(k,0)) for k in campos}
    resultado['diferencas']={k:uf[k]-somas[k] for k in campos}
    if not observadas:
        resultado.update(status='sem_amostra',
                         mensagem='UF recebida; nenhuma zona disponível para conciliar.')
        return resultado
    ts_uf = _data_geracao(estadual.get('geracao'))
    ts_z = [_data_geracao(z.get('geracao')) for z in observadas.values()]
    if ts_uf is None or any(t is None for t in ts_z):
        resultado.update(status='geracao_desconhecida',
                         mensagem='Sem horários comparáveis: não é possível conciliar snapshots.')
        return resultado
    if max(ts_z) > ts_uf:
        resultado.update(status='uf_defasada',
                         mensagem='Algumas zonas são mais recentes que a UF; aguardar atualização estadual.')
        return resultado
    if any(v < 0 for v in resultado['diferencas'].values()):
        resultado.update(status='inconsistente',
                         mensagem='Soma da amostra supera o total estadual já publicado.')
        return resultado
    completo = (universo is not None and set(observadas)==set(universo)
                and all(int(z.get('secoes_total',0))>0 and
                        int(z.get('secoes',0))==int(z.get('secoes_total',0))
                        for z in observadas.values())
                and all(v==0 for v in resultado['diferencas'].values())
                and int(estadual.get('secoes_total',0)) == uf['secoes'])
    if completo:
        resultado.update(status='reconciliado',
                         mensagem='Todas as zonas, seções e votos coincidem com a UF.')
    else:
        resultado.update(status='parcial_compativel',
                         mensagem='Amostra não supera a UF, mas NÃO equivale ao resultado estadual.')
    return resultado
