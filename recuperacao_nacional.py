"""Recuperação LOCAL segura da série nacional a partir do snapshot já validado.

Não acessa GitHub ou rede. O Streamlit gratuito pode reiniciar e perder o
SQLite; o arquivo zonal só é usado se estiver disponível no mesmo filesystem.
"""
from __future__ import annotations
import json
from pathlib import Path

from backup_actions import validar_snapshot
from registro import sincronizar_historico_br


def recuperar_serie_de_snapshot(caminho, arquivo_banco=None):
    """Restaura somente registros BR oficiais de snapshot zonal íntegro.

    Retorna motivos explícitos quando não há backup ou o backup é inválido.
    Usa merge de gerações sem excluir dados do banco existente.
    """
    path=Path(caminho)
    if not path.is_file():
        return {'restaurado':False,'motivo':'snapshot ausente'}
    if path.stat().st_size>30*1024*1024:
        return {'restaurado':False,'motivo':'snapshot acima do limite'}
    try:
        with path.open('r',encoding='utf-8') as handle:
            snapshot=json.load(handle)
        validar_snapshot(snapshot)
        historico=snapshot.get('historico_br') or []
        if not historico:
            return {'restaurado':False,'motivo':'sem histórico BR'}
        resultado=sincronizar_historico_br(historico,arquivo=arquivo_banco)
        return {'restaurado':True,**resultado}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            json.JSONDecodeError) as exc:
        return {'restaurado':False,'motivo':str(exc)[:180]}
