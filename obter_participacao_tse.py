"""Baixa o ZIP oficial TSE e gera histórico de participação por zona.

Usar somente dados históricos JÁ ENCERRADOS (2022T2 e 2026T1).
Não baixar o 2º turno de 2026 antes de publicado.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import requests
import zipfile

from importar_participacao import ler_zip, salvar_historico

URL='https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_{ano}.zip'
LIMITE=500*1024*1024


def baixar(ano,turno,saida='historico_participacao_zonas.csv'):
    if (ano,turno) not in ((2022,2),(2026,1)):
        raise ValueError('Apenas períodos históricos 2022T2 e 2026T1')
    with TemporaryDirectory(prefix='tse_participacao_') as tmp:
        z=Path(tmp)/f'detalhe_votacao_munzona_{ano}.zip'
        with requests.get(URL.format(ano=ano),stream=True,timeout=(15,90),
                          headers={'User-Agent':'ElectionLab2026/0.6 (dados publicos TSE)'}) as r:
            r.raise_for_status()
            tamanho=int(r.headers.get('Content-Length') or 0)
            if tamanho>LIMITE:
                raise ValueError('ZIP TSE excedeu limite de segurança (500 MB)')
            total=0
            with z.open('wb') as out:
                for parte in r.iter_content(chunk_size=1024*1024):
                    if parte:
                        total+=len(parte)
                        if total>LIMITE:
                            raise ValueError('Download interrompido ao alcançar 500 MB')
                        out.write(parte)
        if not zipfile.is_zipfile(z):
            raise ValueError('Download não retornou um ZIP válido')
        mapa=ler_zip(z,ano,turno)
        resumo=salvar_historico(mapa,saida,ano,turno)
        return {'ano':ano,'turno':turno,'bytes_zip':total,**resumo}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--ano',type=int,choices=[2022,2026],required=True)
    p.add_argument('--saida',default='historico_participacao_zonas.csv')
    a=p.parse_args()
    print(json.dumps(baixar(a.ano,2 if a.ano==2022 else 1,a.saida),
                     ensure_ascii=False,indent=2))
