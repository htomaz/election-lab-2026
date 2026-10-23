"""Leitura defensiva dos arquivos EA20 do TSE (2º turno, presidente)."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

ELEICAO = 6258  # Eleição federal / 2º turno de 2026 (TSE)
BASE = 'https://resultados.tse.jus.br/oficial/ele2026'
UFS = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO','ZZ']
NUM_LULA = '13'
NUM_FLAVIO = '22'


def as_int(value, default=0):
    try:
        return int(str(value).replace('.', '').replace(' ', '').split(',')[0])
    except (ValueError, TypeError):
        return default


def url_resultado(uf: str, eleicao: int = ELEICAO) -> str:
    local = uf.lower()
    return f'{BASE}/{eleicao}/dados/{local}/{local}-c0001-e{eleicao:06d}-u.json'


def url_resultado_zona(uf: str, municipio: str, zona: str, eleicao: int = ELEICAO) -> str:\n    uf = uf.lower()\n    municipio = str(municipio).zfill(5)\n    zona = str(zona).zfill(4)\n    if uf.upper() not in UFS or not municipio.isdigit() or not zona.isdigit() or len(municipio)!=5 or len(zona)!=4:\n        raise ValueError('Código de UF, município ou zona inválido')\n    return f'{BASE}/{eleicao}/dados/{uf}/{uf}{municipio}-z{zona}-c0001-e{eleicao:06d}-u.json'\n\n\ndef normalizar_ea20(payload: dict, uf: str) -> dict:
    if not isinstance(payload, dict) or 'carg' not in payload:
        raise ValueError(f'{uf}: arquivo sem bloco EA20 carg')
    votos = {}
    nomes = {}
    for cargo in payload.get('carg', []):
        for agrupamento in cargo.get('agr', []):
            for partido in agrupamento.get('par', []):
                for candidato in partido.get('cand', []):
                    numero = str(candidato.get('n', '')).strip()
                    if not numero:
                        continue
                    votos[numero] = votos.get(numero, 0) + as_int(candidato.get('vap'))
                    nomes[numero] = candidato.get('nmu') or candidato.get('nm') or numero
    secoes = payload.get('s') or {}
    # EA20: vv = votos válidos; tvn = total de votos NULOS (não confundir).\n    validos_oficiais = as_int((payload.get('v') or {}).get('vv'))
    validos_candidatos = sum(votos.values())
    # 2º turno presidencial: não produzir percentual se os votos não batem
    if validos_oficiais and abs(validos_candidatos - validos_oficiais) > 1:
        raise ValueError(f'{uf}: divergência de votos válidos {validos_oficiais} vs {validos_candidatos}')
    total = validos_oficiais or validos_candidatos
    if total and (NUM_LULA not in votos or NUM_FLAVIO not in votos):
        raise ValueError(f'{uf}: candidatos esperados ausentes do JSON; conferir layout e números')
    st = as_int(secoes.get('st'))
    ts = as_int(secoes.get('ts'))
    if st < 0 or ts < st or (total > 0 and ts == 0):
        raise ValueError(f'{uf}: quantidade inválida de seções')
    data = str(payload.get('dg',''))
    hora = str(payload.get('hg',''))
    return {'uf':uf,'lula':votos.get(NUM_LULA, 0),'flavio':votos.get(NUM_FLAVIO, 0),
            'validos':total,'secoes':st,'secoes_total':ts,
            'geracao':f'{data} {hora}'.strip(),'nomes':nomes,'url':url_resultado(uf),
            'outros':max(0,total-votos.get(NUM_LULA,0)-votos.get(NUM_FLAVIO,0))}


def resultado_disponivel(agora=None):
    agora = agora or datetime.now(ZoneInfo('America/Sao_Paulo'))
    inicio = datetime(2026,10,25,17,0,tzinfo=ZoneInfo('America/Sao_Paulo'))
    return agora >= inicio


def baixar_um(uf: str):
    url = url_resultado(uf)
    try:
        resp = requests.get(url, timeout=(6,15), headers={'User-Agent':'MonitorEleitoral2026/0.1 (dados publicos TSE)'})
        resp.raise_for_status()
        return uf, normalizar_ea20(resp.json(), uf), None
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
        resultado = normalizar_ea20(r.json(), uf.upper())
        resultado.update({'municipio':str(municipio).zfill(5),'zona':str(zona).zfill(4), 'url':url})
        return resultado, None
    except (requests.RequestException, ValueError, TypeError) as exc:
        return None, f'{type(exc).__name__}: {str(exc)[:160]}'
