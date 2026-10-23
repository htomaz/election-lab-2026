"""Nomes municipais oficiais do TSE para exibição; códigos continuam nas APIs.

EA12 da eleição federal de 2026 (1º turno), já publicada:
https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json

Formato: {"abr":[{"cd":"SP","mu":[{"cd":"71072","nm":"SÃO PAULO",...}]}]}.
O mapa é indexado por (UF, código TSE de 5 dígitos), nunca por IBGE.
"""
from __future__ import annotations
from pathlib import Path
import csv
import requests

ELEICAO_REFERENCIA = 6257
URL_MUNICIPIOS = (
    'https://resultados.tse.jus.br/oficial/ele2026/'
    f'{ELEICAO_REFERENCIA}/config/mun-e{ELEICAO_REFERENCIA:06d}-cm.json'
)


def normalizar_codigo(codigo):
    valor = str(codigo).strip()
    if not valor.isdigit() or len(valor) > 5:
        raise ValueError(f'Código municipal TSE inválido: {valor!r}')
    return valor.zfill(5)


def interpretar_ea12(payload):
    """Extrai (UF, código TSE) -> nome; recusa dados vazios ou ambíguos."""
    if not isinstance(payload, dict) or not isinstance(payload.get('abr'), list):
        raise ValueError('Configuração EA12 sem lista de abrangências')
    nomes = {}
    for estado in payload['abr']:
        uf = str(estado.get('cd', '')).upper().strip()
        for municipio in estado.get('mu', []):
            codigo = normalizar_codigo(municipio.get('cd',''))
            nome = str(municipio.get('nm','')).strip()
            if not nome or not uf:
                raise ValueError(f'Nome de município ausente em {uf}/{codigo}')
            chave = (uf, codigo)
            if chave in nomes and nomes[chave] != nome:
                raise ValueError(f'Município duplicado com nomes distintos: {chave}')
            nomes[chave] = nome
    if not nomes:
        raise ValueError('EA12 sem municípios')
    return nomes


def ler_csv_local(caminho):
    """Fallback persistido opcional (colunas uf, municipio, nome)."""
    nomes = {}
    with Path(caminho).open(newline='',encoding='utf-8-sig') as arq:
        leitor = csv.DictReader(arq)
        if not {'uf','municipio','nome'}.issubset(leitor.fieldnames or []):
            raise ValueError('Cadastro de nomes municipais sem colunas necessárias')
        for r in leitor:
            chave=(r['uf'].strip().upper(),normalizar_codigo(r['municipio']))
            nome=r['nome'].strip()
            if not nome or (chave in nomes and nomes[chave]!=nome):
                raise ValueError(f'Cadastro de municípios inconsistente: {chave}')
            nomes[chave]=nome
    return nomes


def obter_municipios(caminho_local=None):
    """Prefere snapshot local versionado; consulta EA12 oficial se não houver."""
    if caminho_local and Path(caminho_local).is_file():
        base=ler_csv_local(caminho_local)
    else:
        resposta=requests.get(URL_MUNICIPIOS, timeout=(5, 15),
                             headers={'User-Agent':'ElectionLab2026/0.5 (EA12 publico TSE)'})
        resposta.raise_for_status()
        base=interpretar_ea12(resposta.json())
    # O arquivo tem > 5 mil municípios incluindo o exterior. Um resultado
    # incompleto não deve trocar nomes silenciosamente no dashboard.
    if len(base)<5000:
        raise ValueError(f'Cadastro EA12 incompleto: somente {len(base)} localidades')
    return base


def nome_municipio(uf, codigo, nomes):
    chave=(str(uf).strip().upper(),normalizar_codigo(codigo))
    return nomes.get(chave) or f'Município {chave[1]} (nome indisponível)'


def ordenar_municipios(uf, codigos, nomes):
    return sorted(set(codigos),key=lambda codigo:
                  (nome_municipio(uf,codigo,nomes).casefold(),
                   normalizar_codigo(codigo)))
