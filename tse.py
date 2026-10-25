"""Leitura defensiva dos arquivos EA20 do TSE (2º turno, presidente)."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from urllib.parse import urlsplit
import requests

ELEICAO = 6258  # Eleição federal / 2º turno de 2026 (TSE)
BASE = 'https://resultados.tse.jus.br/oficial/ele2026'
UFS = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO','ZZ']
NUM_LULA = '13'
NUM_FLAVIO = '22'


def as_int(value, default=0):
    """Não truncar vírgulas nem converter campos corrompidos em zero.

    Campos quantitativos EA20 são INTEIROS. Apenas ausência explícita
    aceita o default, nunca strings malformadas ('1,5', 'abc', etc.).
    """
    if value is None:
        return default
    if isinstance(value,bool):
        raise ValueError('Campo EA20 quantitativo recebeu booleano')
    if isinstance(value,int):
        return value
    valor=str(value).strip().replace(' ','')
    # Pontos de milhar são tolerados para compatibilidade com arquivos
    # legados; a divulgação EA20 produz inteiros sem formatação.
    if '.' in valor:
        partes=valor.split('.')
        if (not partes[0].lstrip('-').isdigit() or
            any(len(x)!=3 or not x.isdigit() for x in partes[1:])):
            raise ValueError(f'Inteiro EA20 malformado: {value!r}')
        valor=''.join(partes)
    if not valor or not valor.lstrip('-').isdigit():
        raise ValueError(f'Inteiro EA20 malformado: {value!r}')
    return int(valor)


def url_resultado(uf: str, eleicao: int = ELEICAO) -> str:
    local = uf.lower()
    return f'{BASE}/{eleicao}/dados/{local}/{local}-c0001-e{eleicao:06d}-u.json'


def url_resultado_zona(uf: str, municipio: str, zona: str, eleicao: int = ELEICAO) -> str:
    uf = uf.lower()
    municipio = str(municipio).zfill(5)
    zona = str(zona).zfill(4)
    if uf.upper() not in UFS or not municipio.isdigit() or not zona.isdigit() or len(municipio)!=5 or len(zona)!=4:
        raise ValueError('Código de UF, município ou zona inválido')
    return f'{BASE}/{eleicao}/dados/{uf}/{uf}{municipio}-z{zona}-c0001-e{eleicao:06d}-u.json'


def normalizar_ea20(payload: dict, uf: str, *,
                    abrangencia_esperada=None, exigir_metadados=False,
                    eleicao_esperada=ELEICAO, turno_esperado=2) -> dict:
    if not isinstance(payload, dict) or 'carg' not in payload:
        raise ValueError(f'{uf}: arquivo sem bloco EA20 carg')
    # O parser de produção exige 6258/T2 por padrão. Somente a auditoria
    # histórica pode passar explicitamente 6257/T1; nunca reinterpretar
    # resultados de outro pleito como votos do segundo turno.
    if (int(eleicao_esperada),int(turno_esperado)) not in ((6257,1),(6258,2)):
        raise ValueError('Identidade de eleição/turno não permitida')
    # Conferir identidade do arquivo, não apenas sua estrutura.
    # EA20 oficial identifica eleição, turno, fase e abrangência.
    exigidos=('ele','t','f','tpabr')
    if exigir_metadados and any(k not in payload for k in exigidos):
        raise ValueError(f'{uf}: EA20 sem identidade obrigatória (ele,t,f,tpabr)')
    if 'ele' in payload and str(payload['ele'])!=str(eleicao_esperada):
        raise ValueError(f'{uf}: EA20 de eleição diferente de {eleicao_esperada}')
    if 't' in payload and str(payload['t'])!=str(turno_esperado):
        raise ValueError(f'{uf}: EA20 de turno diferente de {turno_esperado}')
    if 'f' in payload and str(payload['f']).lower()!='o':
        raise ValueError(f'{uf}: EA20 simulado ou fase desconhecida')
    abr=str(payload.get('tpabr','')).lower()
    if abrangencia_esperada and abr!=abrangencia_esperada:
        raise ValueError(f'{uf}: EA20 de abrangência {abr!r}; '
                         f'esperada {abrangencia_esperada!r}')
    if exigir_metadados and 'cdabr' not in payload:
        raise ValueError(f'{uf}: EA20 sem código de abrangência')
    if abr in ('br','uf') and 'cdabr' in payload and (
        str(payload['cdabr']).strip().upper()!=uf.upper()
    ):
        raise ValueError(f'{uf}: arquivo de outra abrangência')
    votos = {}
    nomes = {}
    for cargo in payload.get('carg', []):
        if str(cargo.get('cd','1')).lstrip('0') != '1':
            continue
        for agrupamento in cargo.get('agr', []):
            for partido in agrupamento.get('par', []):
                for candidato in partido.get('cand', []):
                    numero = str(candidato.get('n', '')).strip()
                    if not numero:
                        continue
                    if exigir_metadados and candidato.get('vap') is None:
                        raise ValueError(f'{uf}: candidato {numero} sem votos vap')
                    quantia = as_int(candidato.get('vap'))
                    if quantia < 0:
                        raise ValueError(f'{uf}: votos negativos')
                    votos[numero] = votos.get(numero, 0) + quantia
                    nomes[numero] = candidato.get('nmu') or candidato.get('nm') or numero
    secoes = payload.get('s') or {}
    # EA20: vv = votos válidos; tvn = total de votos NULOS.
    campos_votos=payload.get('v') or {}
    if exigir_metadados and (
        not all(k in secoes for k in ('st','ts')) or
        not all(k in campos_votos for k in ('vv','vb','tvn','tv'))
    ):
        raise ValueError(f'{uf}: blocos EA20 s/v sem contagens obrigatórias')
    tem_total_oficial='vv' in campos_votos
    validos_oficiais = as_int(campos_votos.get('vv'))
    validos_candidatos = sum(votos.values())
    # Votos são inteiros. Mesmo diferença de UM voto entre soma de
    # candidatos e votos válidos oficiais pode quebrar a convergência
    # no último município; não há arredondamento de contagens.
    if tem_total_oficial and validos_candidatos != validos_oficiais:
        raise ValueError(f'{uf}: divergência de votos válidos {validos_oficiais} vs {validos_candidatos}')
    total = validos_oficiais if tem_total_oficial else validos_candidatos
    if total and (NUM_LULA not in votos or NUM_FLAVIO not in votos):
        raise ValueError(f'{uf}: candidatos esperados ausentes do JSON; conferir layout e números')
    st = as_int(secoes.get('st'))
    ts = as_int(secoes.get('ts'))
    if st < 0 or ts < st or (total > 0 and (ts == 0 or st == 0)):
        raise ValueError(f'{uf}: quantidade inválida de seções')
    # EA20 disponibiliza eleitorado e comparecimento por abrangência.
    # e.te é o eleitorado total; e.est é o eleitorado das seções
    # totalizadas (NÃO o comparecimento); e.c e e.a são presença e
    # abstenção nas seções já totalizadas.
    dados_eleitorado = payload.get('e') or {}
    def opcional(bloco, campo):
        return as_int(bloco[campo]) if campo in bloco and bloco[campo] is not None else None
    aptos = opcional(dados_eleitorado,'te')
    aptos_processados = opcional(dados_eleitorado,'est')
    aptos_instalados = opcional(dados_eleitorado,'esi')
    aptos_nao_instalados = opcional(dados_eleitorado,'esni')
    aptos_nao_apurados = opcional(dados_eleitorado,'esna')
    aptos_nao_totalizados = opcional(dados_eleitorado,'esnt')
    comparecimento = opcional(dados_eleitorado,'c')
    abstencoes = opcional(dados_eleitorado,'a')
    brancos = opcional(campos_votos,'vb')
    nulos = opcional(campos_votos,'tvn')
    total_votos = opcional(campos_votos,'tv')
    if any(x is not None and x < 0 for x in
           (aptos,aptos_processados,aptos_instalados,
            aptos_nao_instalados,aptos_nao_apurados,
            aptos_nao_totalizados,comparecimento,abstencoes,
            brancos,nulos,total_votos)):
        raise ValueError(f'{uf}: dados negativos de comparecimento/abstenção')
    if aptos is not None and aptos_processados is not None and aptos_processados > aptos:
        raise ValueError(f'{uf}: eleitorado processado supera eleitorado total')
    # e.est inclui eleitorado de seções NÃO instaladas. O denominador
    # de comparecimento é e.esi, de seções instaladas (EA20 p.17-19).
    if (aptos_instalados is not None and aptos_processados is not None and
        aptos_instalados>aptos_processados):
        raise ValueError(f'{uf}: eleitorado instalado supera totalizado')
    if (aptos_instalados is not None and aptos_nao_instalados is not None
        and aptos_processados is not None
        and aptos_instalados+aptos_nao_instalados!=aptos_processados):
        raise ValueError(f'{uf}: composição e.esi + e.esni difere de e.est')
    if (aptos is not None and aptos_nao_totalizados is not None and
        aptos_processados is not None and
        aptos_processados+aptos_nao_totalizados!=aptos):
        raise ValueError(f'{uf}: composição e.est + e.esnt difere de e.te')
    if (aptos_instalados is not None and comparecimento is not None and
        abstencoes is not None and
        comparecimento+abstencoes>aptos_instalados):
        raise ValueError(f'{uf}: comparecimento + abstenção supera '
                         'eleitorado de seções instaladas')
    if (aptos_processados is not None and comparecimento is not None and
        abstencoes is not None and
        comparecimento+abstencoes > aptos_processados):
        raise ValueError(f'{uf}: comparecimento + abstenção supera eleitorado processado')
    if (total_votos is not None and
        any(x is not None for x in (brancos,nulos)) and
        total + (brancos or 0)+(nulos or 0)>total_votos):
        raise ValueError(f'{uf}: votos válidos, brancos e nulos superam total de votos')
    if comparecimento is not None and total_votos is not None and total_votos>comparecimento:
        raise ValueError(f'{uf}: votos totais superam comparecimento')
    data = str(payload.get('dg',''))
    hora = str(payload.get('hg',''))
    if exigir_metadados:
        try:
            datetime.strptime(data+' '+hora,'%d/%m/%Y %H:%M:%S')
        except ValueError as exc:
            raise ValueError(f'{uf}: horário de geração EA20 inválido') from exc
    return {'uf':uf,'lula':votos.get(NUM_LULA, 0),'flavio':votos.get(NUM_FLAVIO, 0),
            'validos':total,'secoes':st,'secoes_total':ts,
            'geracao':f'{data} {hora}'.strip(),'nomes':nomes,'url':url_resultado(uf),
            'outros':max(0,total-votos.get(NUM_LULA,0)-votos.get(NUM_FLAVIO,0)),
            'aptos':aptos,'aptos_processados':aptos_processados,
            'aptos_instalados':aptos_instalados,
            'aptos_nao_instalados':aptos_nao_instalados,
            'aptos_nao_apurados':aptos_nao_apurados,
            'comparecimento':comparecimento,'abstencoes':abstencoes,
            'fase':payload.get('f'),'turno':payload.get('t'),
            'id_geracao':payload.get('idg'),
            'brancos':brancos,'nulos':nulos,'total_votos':total_votos}


def resultado_disponivel(agora=None):
    agora = agora or datetime.now(ZoneInfo('America/Sao_Paulo'))
    inicio = datetime(2026,10,25,17,0,tzinfo=ZoneInfo('America/Sao_Paulo'))
    return agora >= inicio


def baixar_um(uf: str):
    url = url_resultado(uf)
    try:
        resp = requests.get(url, timeout=(6,15), headers={'User-Agent':'MonitorEleitoral2026/0.1 (dados publicos TSE)'})
        resp.raise_for_status()
        return uf, normalizar_ea20(resp.json(), uf,
                        abrangencia_esperada=('br' if uf=='BR' else 'uf'),
                        exigir_metadados=True), None
    except (requests.RequestException, ValueError, TypeError) as exc:
        return uf, None, f'{type(exc).__name__}: {str(exc)[:180]}'


def coletar():
    """29 GETs/rodada (BR+28 localidades); no máximo 5 concorrentes."""
    if not resultado_disponivel():
        return {}, {'BR':'A apuração oficial do 2º turno ainda não foi iniciada (25/10/2026, após 17h BRT).'}
    saida, erros = {}, {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futs = [executor.submit(baixar_um, uf) for uf in ['BR'] + UFS]
        for futuro in as_completed(futs):
            uf, item, erro = futuro.result()
            if erro: erros[uf] = erro
            elif item: saida[uf] = item
    return saida, erros


def baixar_zona(uf: str, municipio: str, zona: str):
    """EA20 agregado da zona: requisição pontual, não varredura nacional."""
    url = url_resultado_zona(uf, municipio, zona)
    try:
        r = requests.get(url, timeout=(4, 9), headers={'User-Agent':'ElectionLab2026/0.4 (TSE dados publicos)'})
        r.raise_for_status()
        # A CDN pode redirecionar; nunca aceitar arquivo de outra origem.
        url_recebida=getattr(r,'url',None)
        if isinstance(url_recebida,str) and (
            urlsplit(url_recebida).scheme!='https' or
            urlsplit(url_recebida).hostname!='resultados.tse.jus.br'
        ):
            raise ValueError('Redirecionamento de EA20 para origem não oficial')
        dados=r.json()
        resultado = normalizar_ea20(dados, uf.upper(),
                         abrangencia_esperada='zona', exigir_metadados=True)
        resultado['sha256_ea20']=hashlib.sha256(json.dumps(
            dados,sort_keys=True,ensure_ascii=False,
            separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
        if str(dados.get('cdabr','')).zfill(4)!=str(zona).zfill(4):
            raise ValueError('EA20 retornou zona diferente da solicitada')
        resultado.update({'municipio':str(municipio).zfill(5),'zona':str(zona).zfill(4), 'url':url})
        return resultado, None
    except (requests.RequestException, ValueError, TypeError) as exc:
        return None, f'{type(exc).__name__}: {str(exc)[:160]}'
