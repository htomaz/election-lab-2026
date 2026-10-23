"""Snapshots nacionais locais; não depende de servidor de banco externo."""
from pathlib import Path
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

DB=Path('data/series.sqlite')


def salvar(nacional, projecao):
    if not nacional or not nacional.get('geracao') or not nacional.get('validos'):
        return
    DB.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB, timeout=8) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS snapshots (
          geracao TEXT PRIMARY KEY, capturado TEXT, secoes INTEGER, secoes_total INTEGER,
          validos INTEGER, lula INTEGER, flavio INTEGER,
          proj_lula REAL, proj_flavio REAL)''')
        c.execute('''INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)''',(
            nacional['geracao'], datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            nacional['secoes'], nacional['secoes_total'], nacional['validos'],
            nacional['lula'], nacional['flavio'],
            projecao['lula'] if projecao and projecao['completo'] else None,
            projecao['flavio'] if projecao and projecao['completo'] else None))


def serie():
    if not DB.exists(): return pd.DataFrame()
    with sqlite3.connect(DB,timeout=8) as c:
        return pd.read_sql_query('SELECT * FROM snapshots ORDER BY capturado',c)
