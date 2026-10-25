"""Auditoria dos CSVs territoriais antes de liberar projeções eleitorais."""
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path

CAMPOS_ZONAS = {'uf','municipio','zona','ano','turno','lula','direita','validos'}
CAMPOS_UFS = {'uf','ano','turno','lula','direita','validos'}
ANOS_TURNOS = {(2022, 2), (2026, 1)}


def ler_validado(caminho, campos, chave):
    caminho = Path(caminho)
    if not caminho.is_file():
        raise FileNotFoundError(caminho)
    linhas, chaves = [], set()
    with caminho.open(newline='', encoding='utf-8-sig') as arquivo:
        leitor = csv.DictReader(arquivo)
        if not campos.issubset(leitor.fieldnames or []):
            raise ValueError(f'{caminho.name}: colunas obrigatórias ausentes')
        for numero, r in enumerate(leitor, 2):
            try:
                ano, turno = int(r['ano']), int(r['turno'])
                valores = tuple(int(r[c]) for c in ('lula','direita','validos'))
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{caminho.name}:{numero}: valor inválido') from exc
            if (ano, turno) not in ANOS_TURNOS:
                raise ValueError(f'{caminho.name}:{numero}: eleição não esperada')
            if min(valores) < 0 or valores[0] + valores[1] > valores[2]:
                raise ValueError(f'{caminho.name}:{numero}: votos inconsistentes')
            if not r['uf'].strip():
                raise ValueError(f'{caminho.name}:{numero}: UF vazia')
            k = tuple(r[c] for c in chave)
            if k in chaves:
                raise ValueError(f'{caminho.name}:{numero}: chave duplicada {k}')
            chaves.add(k)
            linhas.append((r, valores))
    if not linhas:
        raise ValueError(f'{caminho.name}: arquivo sem dados')
    return linhas


def auditar(historico_ufs, historico_zonas):
    zonas = ler_validado(historico_zonas, CAMPOS_ZONAS,
                         ('uf','municipio','zona','ano','turno'))
    ufs = ler_validado(historico_ufs, CAMPOS_UFS, ('uf','ano','turno'))
    agregados = defaultdict(lambda: [0, 0, 0])
    zonas_por_uf = defaultdict(set)
    for r, votos in zonas:
        k = (r['uf'], r['ano'], r['turno'])
        for i, v in enumerate(votos):
            agregados[k][i] += v
        zonas_por_uf[k].add((r['municipio'], r['zona']))
    totais = {(r['uf'],r['ano'],r['turno']): tuple(v) for r,v in ufs}
    if set(agregados) != set(totais):
        raise ValueError('Cobertura diferente entre arquivos de UFs e zonas')
    divergentes = [k for k, v in agregados.items() if tuple(v) != totais[k]]
    if divergentes:
        raise ValueError(f'Totais por UF divergentes das zonas: {divergentes[:5]}')
    cobertura = {}
    for ano, turno in sorted(ANOS_TURNOS):
        keys = [k for k in totais if (int(k[1]),int(k[2])) == (ano,turno)]
        cobertura[f'{ano}T{turno}'] = {
            'localidades': len(keys),
            'zonas': sum(len(zonas_por_uf[k]) for k in keys),
            'validos': sum(totais[k][2] for k in keys)
        }

    # Referência nacional de 2022: resultados oficiais do segundo turno.
    # Detecta, entre outros problemas, arquivos com todos os votos duplicados.
    total_2022 = cobertura['2022T2']['validos']
    if cobertura['2022T2']['localidades'] == 28 and total_2022 != 118552353:
        raise ValueError(
            f'2022T2: {total_2022} votos válidos; esperado 118552353. '
            'Verifique duplicação ou cobertura incompleta antes de usar o histórico.'
        )
    total_2026 = cobertura['2026T1']['validos']
    if cobertura['2026T1']['localidades'] == 28 and total_2026 != 119300788:
        raise ValueError(f'2026T1: {total_2026} votos válidos; esperado 119300788.')
    return cobertura


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--ufs', default='historico_ufs.csv')
    p.add_argument('--zonas', default='historico_zonas.csv')
    args = p.parse_args()
    for periodo, resultado in auditar(args.ufs,args.zonas).items():
        print(periodo, resultado)
