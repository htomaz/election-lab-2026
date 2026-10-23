"""Importação sob demanda de arquivos históricos públicos do TSE.

Não executar em background: Streamlit Community Cloud pode suspender a aplicação.
Os arquivos CSV processados precisam ser baixados e enviados ao GitHub para persistir.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import zipfile
import requests
from importar_historico import importar_zip

URLS = {
    2022: 'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip',
    2026: 'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2026.zip',
}
LIMITE_BYTES = 650 * 1024 * 1024


def baixar_e_importar(ano: int, pasta='.', progresso=None, limite_bytes=LIMITE_BYTES):
    """Baixa ZIP em disco temporário e importa em streaming, sem extrair CSV em disco.

    progresso(recebido, total_estimado) é opcional. Erros não são mascarados.
    """
    if ano not in URLS:
        raise ValueError('Ano histórico não suportado.')
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f'tse_{ano}_') as temp:
        destino = Path(temp) / f'votacao_candidato_munzona_{ano}.zip'
        with requests.get(URLS[ano], stream=True, timeout=(15, 75),
                          headers={'User-Agent':'ElectionLab2026/0.3 (consulta publica TSE)'}) as r:
            r.raise_for_status()
            total = int(r.headers.get('Content-Length') or 0)
            if total > limite_bytes:
                raise ValueError(f'Arquivo excede o limite de segurança ({limite_bytes//(1024*1024)} MB).')
            livre = shutil.disk_usage(temp).free
            if total and livre < total + 60 * 1024 * 1024:
                raise OSError('Espaço insuficiente na hospedagem para baixar o ZIP histórico.')
            baixados = 0
            with destino.open('wb') as f:
                for bloco in r.iter_content(chunk_size=1024*1024):
                    if not bloco:
                        continue
                    baixados += len(bloco)
                    if baixados > limite_bytes:
                        raise ValueError('Download interrompido: tamanho superior ao limite de segurança.')
                    f.write(bloco)
                    if progresso:
                        progresso(baixados, total)
        if not zipfile.is_zipfile(destino):
            raise ValueError('O TSE não retornou um arquivo ZIP válido.')
        return importar_zip(destino, ano, 2 if ano == 2022 else 1,
                           arquivo_saida=pasta/'historico_ufs.csv',
                           arquivo_zonas=pasta/'historico_zonas.csv')
