"""Snapshots nacionais locais; não depende de servidor de banco externo."""
from pathlib import Path
import csv
import io
import math
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

DB=Path(__file__).resolve().parent/'data/series.sqlite'
CAMPOS=('geracao','capturado','secoes','secoes_total','validos','lula','flavio',
        'proj_lula','proj_flavio')


def salvar(nacional, projecao):
    if not nacional or not nacional.get('geracao') or not nacional.get('validos'):
        return
    DB.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB, timeout=8) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS snapshots (
          geracao TEXT PRIMARY KEY, capturado TEXT, secoes INTEGER, secoes_total INTEGER,
          validos INTEGER, lula INTEGER, flavio INTEGER,
          proj_lula REAL, proj_flavio REAL)''')
        c.execute('''INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(geracao) DO UPDATE SET
            capturado=excluded.capturado,
            secoes=excluded.secoes,
            secoes_total=excluded.secoes_total,
            validos=excluded.validos,
            lula=excluded.lula,
            flavio=excluded.flavio,
            proj_lula=COALESCE(excluded.proj_lula,snapshots.proj_lula),
            proj_flavio=COALESCE(excluded.proj_flavio,snapshots.proj_flavio)
            WHERE excluded.secoes>=snapshots.secoes''',(
            nacional['geracao'], datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            nacional['secoes'], nacional['secoes_total'], nacional['validos'],
            nacional['lula'], nacional['flavio'],
            projecao['lula'] if projecao and projecao['completo'] else None,
            projecao['flavio'] if projecao and projecao['completo'] else None))


def serie():
    if not DB.exists(): return pd.DataFrame()
    with sqlite3.connect(DB,timeout=8) as c:
        return pd.read_sql_query('SELECT * FROM snapshots ORDER BY capturado',c)



def sincronizar_historico_br(registros,arquivo=None):
    """Reconstrói o SQLite local usando APENAS a série BR do artifact validado.

    Votos já observados não são misturados com projeções; estas são
    preservadas quando o mesmo timestamp de geração já existir no banco.
    """
    from serie_nacional_actions import incorporar
    linhas=incorporar(registros,[])
    if not linhas:
        return {'linhas_recebidas':0,'linhas_inseridas_ou_atualizadas':0}
    destino=io.StringIO()
    writer=csv.DictWriter(destino,fieldnames=CAMPOS)
    writer.writeheader()
    for item in linhas:
        writer.writerow({**item,'proj_lula':'','proj_flavio':''})
    return restaurar_csv(destino.getvalue(),arquivo=arquivo)


def exportar_csv():
    """Backup simples e portátil; os números continuam identificados por geração."""
    df=serie()
    if df.empty:
        return ''
    return df.to_csv(index=False)


def restaurar_csv(conteudo,arquivo=None):
    """Importa CSV validado sem apagar registros existentes mais recentes.

    Importação explícita pela UI, não ocorre apenas ao selecionar arquivo.
    O banco é local e pode desaparecer em reinicializações do Streamlit Cloud.
    """
    if isinstance(conteudo,bytes):
        if len(conteudo)>5*1024*1024:
            raise ValueError('CSV de série maior que 5 MB')
        conteudo=conteudo.decode('utf-8-sig')
    if not isinstance(conteudo,str) or len(conteudo)>5*1024*1024:
        raise ValueError('CSV de série inválido ou maior que 5 MB')
    leitor=csv.DictReader(io.StringIO(conteudo))
    if not set(CAMPOS).issubset(leitor.fieldnames or []):
        raise ValueError('CSV sem as nove colunas do histórico')
    linhas=[]
    for r in leitor:
        geracao=str(r['geracao']).strip()
        capturado=str(r['capturado']).strip()
        if len(geracao)>100 or not geracao or len(capturado)>100:
            raise ValueError('Identificador ou horário inválido')
        try:
            dt=datetime.fromisoformat(capturado)
            if dt.tzinfo is None:
                raise ValueError('Captura sem timezone')
            ints=[int(r[col]) for col in ('secoes','secoes_total',
                                           'validos','lula','flavio')]
            floats=[]
            for col in ('proj_lula','proj_flavio'):
                texto=str(r[col] or '').strip()
                numero=float(texto) if texto else None
                if numero is not None and (not math.isfinite(numero) or numero<0):
                    raise ValueError('Projeção inválida')
                floats.append(numero)
        except (ValueError,TypeError,OverflowError) as exc:
            raise ValueError('Linha com datas/votos inválidos') from exc
        s,ts,v,l,f=ints
        if min(ints)<0 or s>ts or l+f>v:
            raise ValueError('CSV com votos ou seções inconsistentes')
        linhas.append((geracao,capturado,*ints,*floats))
        if len(linhas)>50000:
            raise ValueError('CSV acima de 50 mil gerações')
    destino=Path(arquivo) if arquivo is not None else DB
    destino.parent.mkdir(parents=True,exist_ok=True)
    adicionadas=0
    with sqlite3.connect(destino,timeout=8) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS snapshots (
          geracao TEXT PRIMARY KEY, capturado TEXT, secoes INTEGER, secoes_total INTEGER,
          validos INTEGER, lula INTEGER, flavio INTEGER,
          proj_lula REAL, proj_flavio REAL)''')
        for values in linhas:
            cur=db.execute('''INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(geracao) DO UPDATE SET
                   capturado=excluded.capturado,
                   secoes=excluded.secoes,
                   secoes_total=excluded.secoes_total,
                   validos=excluded.validos,
                   lula=excluded.lula,
                   flavio=excluded.flavio,
                   proj_lula=COALESCE(excluded.proj_lula,snapshots.proj_lula),
                   proj_flavio=COALESCE(excluded.proj_flavio,snapshots.proj_flavio)
                 WHERE excluded.capturado>snapshots.capturado
                   AND excluded.secoes>=snapshots.secoes''',values)
            adicionadas+=max(0,cur.rowcount)
    return {'linhas_recebidas':len(linhas),'linhas_inseridas_ou_atualizadas':adicionadas}
