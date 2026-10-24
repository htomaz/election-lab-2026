"""Motor nacional por município/zona eleitoral — projeções EXPLORATÓRIAS.

Cada zona do catálogo oficial recebe uma linha, mesmo sem votos observados.
Parciais do EA20 são imutáveis; somente o volume ainda não apurado é estimado.
O resultado nacional é a soma das zonas, não a extrapolação da parcial BR.
O catálogo EA12 da eleição 6258 deve ser validado antes de homologação.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import math

from modelo_zonas import carregar_zonas, projetar_zonas
from municipios_tse import nome_municipio, normalizar_codigo
from tse import UFS

VERSAO = 1
ELEICAO = 6258
MAX_IDADE_SEGUNDOS = 900


def chave_zona(uf, municipio, zona):
    uf = str(uf).upper().strip()
    if uf not in UFS:
        raise ValueError(f'UF inválida: {uf}')
    municipio = normalizar_codigo(municipio)
    codigo_zona = str(zona).strip()
    if not codigo_zona.isdigit() or len(codigo_zona) > 4:
        raise ValueError(f'Zona eleitoral inválida: {zona}')
    return uf, municipio, codigo_zona.zfill(4)


def id_zona(chave):
    return '|'.join(chave)


def ler_snapshot(caminho):
    with Path(caminho).open(encoding='utf-8') as f:
        return json.load(f)


def executar(snapshot, historico, nomes=None, agora=None,
             idade_max=MAX_IDADE_SEGUNDOS, exigir_catalogo_nacional=True,
             peso_2026=.75, ajuste_volume=1., intensidade=.35):
    """Reconstrói todas as zonas oficiais e devolve projeções por zona, município e UF.

    snapshot: {versao, eleicao, catalogo_origem, catalogo: [{uf,municipio,zona}],
               observacoes: {'UF|MUN|ZONA': {lula,flavio,validos,
                              secoes,secoes_total,capturado_em,...}}}.
    Registros com data de coleta velha não são tratados como dados atuais.
    """
    if not isinstance(snapshot, dict) or snapshot.get('versao') != VERSAO:
        raise ValueError('Snapshot zonal com versão não reconhecida')
    if snapshot.get('eleicao') != ELEICAO:
        raise ValueError('Snapshot não corresponde ao 2º turno federal 6258')
    catalogo = {}
    for item in snapshot.get('catalogo', []):
        chave = chave_zona(item['uf'], item['municipio'], item['zona'])
        if chave in catalogo:
            raise ValueError(f'Zona duplicada no catálogo: {chave}')
        catalogo[chave] = item
    if not catalogo:
        raise ValueError('Não há zonas no catálogo')
    ufs_catalogo = {k[0] for k in catalogo}
    origem = snapshot.get('catalogo_origem','')
    catalogo_oficial = origem == 'EA16_TSE_3221'
    completo = catalogo_oficial and ufs_catalogo == set(UFS) and len(catalogo)>=5000
    if exigir_catalogo_nacional and not completo:
        raise ValueError('Catálogo EA16 nacional do pleito 3221 não foi confirmado; '
                         'não extrapolar amostra como projeção nacional')
    if agora is None:
        agora = datetime.now(timezone.utc).timestamp()
    observadas = {}
    idade_expirada = []
    rejeitadas = []
    registros = snapshot.get('observacoes', {})
    if not isinstance(registros, dict):
        raise ValueError('Observações devem formar um dicionário')
    for ident, item in registros.items():
        if not isinstance(item, dict):
            rejeitadas.append(ident)
            continue
        try:
            chave = chave_zona(*ident.split('|'))
            if chave not in catalogo:
                rejeitadas.append(ident)
                continue
            capturado = float(item['capturado_em'])
            if not math.isfinite(capturado) or capturado > agora+60:
                raise ValueError('horário de coleta inválido')
            if agora-capturado > idade_max:
                # O voto oficialmente observado continua sendo um piso válido.
                # Não descartá-lo por falta de uma consulta recente.
                idade_expirada.append(ident)
            l,f,v = (int(item[c]) for c in ('lula','flavio','validos'))
            s,ts = (int(item[c]) for c in ('secoes','secoes_total'))
            if min(l,f,v,s,ts) < 0 or l+f > v or s>ts or (v>0 and (ts==0 or s==0)):
                raise ValueError('votos/seções inconsistentes')
            if s==0 and v>0:
                raise ValueError('votos em zona sem seções totalizadas')
            observadas[chave] = {'lula':l,'flavio':f,'validos':v,
                                'secoes':s,'secoes_total':ts}
        except (KeyError,TypeError,ValueError):
            rejeitadas.append(ident)
    if rejeitadas:
        # Não produzir previsão a partir de snapshots com votos inválidos ou IDs errados.
        raise ValueError(f'{len(rejeitadas)} observações zonais inválidas: '
                         + ', '.join(str(k) for k in rejeitadas[:3]))
    modelo = projetar_zonas(
        observadas,historico,peso_2026=peso_2026,
        ajuste_volume=ajuste_volume,intensidade=intensidade,
        universo=set(catalogo))
    nomes = nomes or {}
    estados = defaultdict(lambda: {'lula_apurado':0,'flavio_apurado':0,
                                    'validos_apurados':0,'lula_estimado':0.,
                                    'flavio_estimado':0.,'zonas_total':0,
                                    'zonas_consultadas':0,'zonas_concluidas':0,
                                    'secoes_apuradas_consultadas':0,
                                    'secoes_total_consultadas':0})
    municipios = defaultdict(lambda: {'lula_apurado':0,'flavio_apurado':0,
                                       'validos_apurados':0,'lula_estimado':0.,
                                       'flavio_estimado':0.,'zonas_total':0,
                                       'zonas_consultadas':0,'zonas_concluidas':0})
    expiradas=set(idade_expirada)
    linhas = []
    for linha in modelo['linhas']:
        chave = chave_zona(linha['uf'],linha['municipio'],linha['zona'])
        obs = observadas.get(chave)
        if obs is None:
            status = 'não consultada'
        elif id_zona(chave) in expiradas:
            status = 'desatualizada'
        elif obs['secoes_total'] > 0 and obs['secoes'] == obs['secoes_total']:
            status = 'concluída'
        elif obs['secoes'] > 0:
            status = 'parcial'
        else:
            status = 'sem votos'
        lf = linha['lula_projetado']+linha['flavio_projetado']
        r = {**linha,'nome_municipio':nome_municipio(chave[0],chave[1],nomes),
             'status':status, 'lula_restante_estimado':max(0.,linha['lula_projetado']-linha['lula_apurado']),
             'flavio_restante_estimado':max(0.,linha['flavio_projetado']-linha['flavio_apurado']),
             'votos_restantes_estimados':max(0.,lf-linha['lula_apurado']-linha['flavio_apurado']),
             'cobertura_historica':bool(linha['historico_disponivel']),
             'secoes_cadastradas_ea16':catalogo[chave].get('secoes_cadastradas_ea16')}
        linhas.append(r)
        for acc in (estados[chave[0]],municipios[chave[:2]]):
            acc['lula_apurado']+=linha['lula_apurado']
            acc['flavio_apurado']+=linha['flavio_apurado']
            acc['validos_apurados']+=linha['validos_apurados']
            acc['lula_estimado']+=linha['lula_projetado']
            acc['flavio_estimado']+=linha['flavio_projetado']
            acc['zonas_total']+=1
            acc['zonas_consultadas']+=int(obs is not None and id_zona(chave) not in expiradas)
            acc['zonas_concluidas']+=int(obs is not None and
                                        obs['secoes_total']>0 and
                                        obs['secoes']==obs['secoes_total'])
        if obs is not None:
            estados[chave[0]]['secoes_apuradas_consultadas']+=obs['secoes']
            estados[chave[0]]['secoes_total_consultadas']+=obs['secoes_total']
    for acc in [*estados.values(),*municipios.values()]:
        denom=acc['lula_estimado']+acc['flavio_estimado']
        acc['lula_pct_estimado']=100*acc['lula_estimado']/denom if denom else None
        acc['flavio_pct_estimado']=100*acc['flavio_estimado']/denom if denom else None
    nacionais = {
        'lula_estimado':sum(x['lula_estimado'] for x in estados.values()),
        'flavio_estimado':sum(x['flavio_estimado'] for x in estados.values()),
        'lula_apurado':sum(x['lula_apurado'] for x in estados.values()),
        'flavio_apurado':sum(x['flavio_apurado'] for x in estados.values()),
        'zonas_total':len(catalogo),
        'zonas_consultadas':len(observadas)-len(idade_expirada),
        'zonas_com_observacao':len(observadas),
        'zonas_desatualizadas':len(idade_expirada),
        'zonas_concluidas':sum(x['zonas_concluidas'] for x in estados.values()),
        'catalogo_oficial_nacional':completo,
        'catalogo_origem':origem,
    }
    den=nacionais['lula_estimado']+nacionais['flavio_estimado']
    nacionais['lula_pct_estimado']=100*nacionais['lula_estimado']/den if den else None
    nacionais['flavio_pct_estimado']=100*nacionais['flavio_estimado']/den if den else None
    nacionais['cobertura_zonas_pct']=100*(len(observadas)-len(idade_expirada))/len(catalogo)
    nacionais['apuracao_integral_zonas']=(nacionais['zonas_concluidas']==len(catalogo))
    nacionais['metodologia']='Projeção experimental, não é resultado oficial do TSE'
    return {'linhas':linhas,'municipios':dict(municipios),'ufs':dict(estados),
            'brasil':nacionais,'observadas':observadas,
            'erros_ignorados':[], 'desatualizadas':idade_expirada}
