"""Histórico de participação por município/zona, extraído do TSE.

Fonte: detalhe_votacao_munzona_{ano}.zip (Presidente, ano/turno).
Diferente de votacao_candidato_munzona, esse arquivo contém:
aptos, comparecimento, abstenções, votos brancos, nulos e válidos.
Não confundir linhas de cargos distintos nem somar uma zona várias vezes.

Uso:
 python importar_participacao.py --zip2022 detalhe_votacao_munzona_2022.zip
 python importar_participacao.py --zip2026 detalhe_votacao_munzona_2026.zip
"""
from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
import csv
import io
import zipfile

COLUNAS=('uf','municipio','zona','ano','turno','aptos','comparecimento',
         'abstencoes','brancos','nulos','validos')
NECESSARIAS={'NR_TURNO','SG_UF','CD_MUNICIPIO','NR_ZONA','CD_CARGO',
             'QT_APTOS','QT_COMPARECIMENTO','QT_ABSTENCOES'}
VALIDOS_COLUNAS=('QT_VOTOS_VALIDOS','QT_VOTOS_NOMINAIS_VALIDOS')


def _inteiro(linha,campo,padrao=None):
    if campo not in linha or linha[campo] is None or linha[campo].strip()=='':
        if padrao is not None:
            return padrao
        raise ValueError(f'Coluna {campo} ausente/vazia')
    x=int(linha[campo])
    if x<0:
        raise ValueError(f'{campo} negativo')
    return x


def ler_zip(caminho,ano,turno):
    caminho=Path(caminho)
    mapa={}
    if not caminho.exists():
        raise FileNotFoundError(caminho)
    with zipfile.ZipFile(caminho) as arquivo:
        nomes=[n for n in arquivo.namelist() if n.lower().endswith('.csv')
               and not n.split('/')[-1].startswith('._')]
        nacionais=[n for n in nomes if n.upper().endswith(('_BRASIL.CSV','_BR.CSV'))]
        if nacionais:
            nomes=nacionais
        if not nomes:
            raise ValueError('ZIP oficial sem CSV')
        for nome in nomes:
            with arquivo.open(nome) as bruto:
                leitor=csv.DictReader(io.TextIOWrapper(
                    bruto,encoding='latin-1',newline=''),delimiter=';')
                leitor.fieldnames=[x.lstrip('\ufeff').upper().strip()
                                   for x in (leitor.fieldnames or [])]
                if not NECESSARIAS.issubset(leitor.fieldnames):
                    raise ValueError(f'{nome}: cabeçalhos não reconhecidos: {leitor.fieldnames}')
                if not any(k in leitor.fieldnames for k in VALIDOS_COLUNAS):
                    raise ValueError(f'{nome}: sem votos válidos')
                if not {'QT_VOTOS_BRANCOS','QT_VOTOS_NULOS'}.issubset(leitor.fieldnames):
                    raise ValueError(f'{nome}: faltam brancos/nulos')
                for r in leitor:
                    if r['NR_TURNO'].strip()!=str(turno) or r['CD_CARGO'].strip().lstrip('0')!='1':
                        continue
                    uf=r['SG_UF'].strip().upper()
                    if len(uf)!=2:
                        continue
                    codigo=r['CD_MUNICIPIO'].strip().zfill(5)
                    zona=r['NR_ZONA'].strip().zfill(4)
                    if not codigo.isdigit() or not zona.isdigit():
                        raise ValueError('Município/zona com código inválido')
                    chave=(uf,codigo,zona,ano,turno)
                    if chave in mapa:
                        raise ValueError(f'Duplicação de zona/cargo/turno em {nome}: {chave}')
                    aptos=_inteiro(r,'QT_APTOS')
                    comp=_inteiro(r,'QT_COMPARECIMENTO')
                    abst=_inteiro(r,'QT_ABSTENCOES')
                    br=_inteiro(r,'QT_VOTOS_BRANCOS')
                    nul=_inteiro(r,'QT_VOTOS_NULOS')
                    if 'QT_VOTOS_VALIDOS' in r and r['QT_VOTOS_VALIDOS'].strip():
                        vv=_inteiro(r,'QT_VOTOS_VALIDOS')
                    else:
                        vv=_inteiro(r,'QT_VOTOS_NOMINAIS_VALIDOS')
                        vv+=_inteiro(r,'QT_VOTOS_LEGENDA',0)
                    if comp>aptos or abst>aptos or vv+br+nul>comp:
                        raise ValueError(f'Participação/votos incompatíveis: {chave}')
                    # O TSE documenta exceções pontuais por transferências
                    # temporárias, portanto não exigir aptos == comp+abst.
                    mapa[chave]=(aptos,comp,abst,br,nul,vv)
    if not mapa:
        raise ValueError(f'ZIP sem Presidente {ano}T{turno}')
    return mapa


def salvar_historico(mapa,caminho,ano,turno,exigir_cobertura=True):
    if exigir_cobertura:
        ufs={k[0] for k in mapa}
        if len(ufs)!=28 or len(mapa)<6000:
            raise ValueError(f'Histórico de participação incompleto: '
                             f'{len(ufs)} localidades, {len(mapa)} zonas')
    destino=Path(caminho)
    anteriores={}
    if destino.exists():
        with destino.open(newline='',encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                k=(r['uf'],r['municipio'],r['zona'],int(r['ano']),int(r['turno']))
                if (k[3],k[4])!=(ano,turno):
                    anteriores[k]=tuple(int(r[c]) for c in COLUNAS[5:])
    anteriores.update(mapa)
    destino.parent.mkdir(parents=True,exist_ok=True)
    import os
    import tempfile
    fd,temp=tempfile.mkstemp(dir=str(destino.parent),prefix='.part-',suffix='.csv')
    try:
        with os.fdopen(fd,'w',newline='',encoding='utf-8') as f:
            w=csv.writer(f)
            w.writerow(COLUNAS)
            for k,v in sorted(anteriores.items()):
                w.writerow([*k,*v])
        os.replace(temp,destino)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {'linhas_total':len(anteriores),'linhas_importadas':len(mapa),
            'aptos':sum(v[0] for v in mapa.values()),
            'comparecimento':sum(v[1] for v in mapa.values()),
            'abstencoes':sum(v[2] for v in mapa.values()),
            'brancos':sum(v[3] for v in mapa.values()),
            'nulos':sum(v[4] for v in mapa.values()),
            'validos':sum(v[5] for v in mapa.values())}


def carregar_participacao(caminho='historico_participacao_zonas.csv'):
    path=Path(caminho)
    if not path.exists():
        return {}
    m=defaultdict(dict)
    with path.open(newline='',encoding='utf-8-sig') as f:
        leitor=csv.DictReader(f)
        if not set(COLUNAS).issubset(leitor.fieldnames or []):
            raise ValueError('Colunas insuficientes no histórico de participação')
        for r in leitor:
            chave=(r['uf'].upper(),r['municipio'].zfill(5),r['zona'].zfill(4))
            ano_turno=(int(r['ano']),int(r['turno']))
            if ano_turno in m[chave]:
                raise ValueError(f'Zona histórica de participação duplicada: {chave}')
            x={c:int(r[c]) for c in COLUNAS[5:]}
            if min(x.values())<0 or x['comparecimento']>x['aptos'] or (
                x['validos']+x['brancos']+x['nulos']>x['comparecimento']
            ):
                raise ValueError(f'Valores de participação inconsistentes: {chave}')
            m[chave][ano_turno]=x
    return dict(m)


def main():
    cli=ArgumentParser()
    cli.add_argument('--zip2022')
    cli.add_argument('--zip2026')
    cli.add_argument('--saida',default='historico_participacao_zonas.csv')
    a=cli.parse_args()
    if not a.zip2022 and not a.zip2026:
        cli.error('Informe ao menos um ZIP oficial')
    for ano,turno,path in ((2022,2,a.zip2022),(2026,1,a.zip2026)):
        if path:
            mapa=ler_zip(path,ano,turno)
            print(ano,turno,salvar_historico(mapa,a.saida,ano,turno))
if __name__=='__main__':
    main()
