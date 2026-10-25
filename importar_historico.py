r"""Importar arquivos oficiais ZIP de votação por município/zona do TSE.

Uso: python importar_historico.py --zip2022 C:\...\votacao_candidato_munzona_2022.zip --zip2026 C:\...\votacao_candidato_munzona_2026.zip
Um dos ZIPs pode ser omitido, mas base de 2026 é essencial para calibração.
"""
from __future__ import annotations
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
import csv
import io
import zipfile

TOTAIS_OFICIAIS = {(2022,2): (118552353,60345999,58206354),
                   (2026,1): (119300788,53879538,56104503)}

UFS = set(['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO','ZZ'])


def importar_zip(caminho, ano, turno, arquivo_saida='data/historico_ufs.csv', arquivo_zonas='data/historico_zonas.csv'):
    caminho=Path(caminho)
    if not caminho.exists(): raise FileNotFoundError(f'Arquivo não encontrado: {caminho}')
    acumulado = defaultdict(lambda:[0,0,0])
    vistos=0
    arquivos_processados=[]
    with zipfile.ZipFile(caminho) as z:
        nomes=[x for x in z.namelist() if x.lower().endswith('.csv') and not x.split('/')[-1].startswith('._')]
        # _BRASIL contém o conjunto de UFs quando presente. Processar ambos duplicaria os votos.
        brasil=[x for x in nomes if x.upper().endswith(('_BRASIL.CSV','_BR.CSV'))]
        if brasil:
            nomes=brasil
        if not nomes: raise ValueError('ZIP sem arquivos CSV compatíveis')
        for nome in nomes:
            with z.open(nome) as f:
                texto=io.TextIOWrapper(f,encoding='latin-1',errors='replace',newline='')
                reader=csv.DictReader(texto,delimiter=';')
                if not reader.fieldnames: continue
                reader.fieldnames=[str(c).lstrip('\ufeff').strip().upper() for c in reader.fieldnames]
                necessarios={'NR_TURNO','SG_UF','NR_CANDIDATO','CD_CARGO','CD_MUNICIPIO','NR_ZONA'}
                if not necessarios.issubset(reader.fieldnames):
                    print(f'Ignorando {nome}: colunas essenciais ausentes')
                    continue
                vot_col=next((c for c in ['QT_VOTOS_NOMINAIS_VALIDOS','QT_VOTOS_NOMINAIS'] if c in reader.fieldnames),None)
                if not vot_col: raise ValueError(f'{nome}: coluna de votos nominais ausente')
                arquivos_processados.append(nome)
                for row in reader:
                    if row['NR_TURNO'].strip()!=str(turno):continue
                    if row['CD_CARGO'].strip().lstrip('0')!='1':continue
                    uf=row['SG_UF'].strip().upper()
                    if uf not in UFS:continue
                    try: votos=int(row[vot_col]); candidato=str(int(row['NR_CANDIDATO']))
                    except (TypeError,ValueError):continue
                    if votos<0: raise ValueError(f'{nome}: votos negativos')
                    # uma linha/candidato por zona, preservando o nível territorial.
                    municipio=row['CD_MUNICIPIO'].strip().zfill(5)
                    zona=row['NR_ZONA'].strip().zfill(4)
                    acc=acumulado[(uf,municipio,zona)]
                    acc[2]+=votos
                    if candidato=='13': acc[0]+=votos
                    elif candidato=='22': acc[1]+=votos
                    vistos+=1
    if not arquivos_processados or not acumulado:
        raise ValueError('Não foram encontrados votos presidenciais para o turno especificado; confira arquivo, ano e turno.')
    # Bloqueia importações incompletas e os votos 2x que apareceram em versões
    # antigas dos históricos. Não altera arquivos já corretos em caso de falha.
    cobertura={uf for (uf,_,_) in acumulado}
    if cobertura != UFS:
        raise ValueError(f'Importação incompleta: {len(cobertura)}/{len(UFS)} localidades; '
                         'arquivos existentes preservados.')
    referencia=TOTAIS_OFICIAIS.get((ano,turno))
    if referencia:
        observados=(sum(x[2] for x in acumulado.values()),
                    sum(x[0] for x in acumulado.values()),
                    sum(x[1] for x in acumulado.values()))
        if observados != referencia:
            raise ValueError(f'Totais do ZIP divergentes dos totais oficiais '
                             f'({ano}T{turno}): {observados} vs {referencia}. '
                             'Provável duplicação ou arquivo incorreto. '
                             'Nenhum CSV foi sobrescrito.')

    Path(arquivo_zonas).parent.mkdir(parents=True,exist_ok=True)
    head=['uf','municipio','zona','ano','turno','lula','direita','validos']
    linhas_anteriores=[]
    p=Path(arquivo_zonas)
    if p.exists():
        with p.open(newline='',encoding='utf-8-sig') as f:
            linhas_anteriores=[r for r in csv.DictReader(f) if not (r['ano']==str(ano) and r['turno']==str(turno))]
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=head); w.writeheader()
        w.writerows(linhas_anteriores)
        for (uf,mu,zona),v in sorted(acumulado.items()):
            w.writerow(dict(zip(head,[uf,mu,zona,ano,turno,*v])))
    ufs=defaultdict(lambda:[0,0,0])
    with p.open(newline='',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            v=ufs[(r['uf'],r['ano'],r['turno'])]
            for i,c in enumerate(('lula','direita','validos')):v[i]+=int(r[c])
    out=Path(arquivo_saida)
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['uf','ano','turno','lula','direita','validos'])
        for (uf,a,t),vals in sorted(ufs.items()):w.writerow([uf,a,t,*vals])
    print(f'{ano} turno {turno}: {vistos:,} linhas, {len(acumulado)} zonas em {len(arquivos_processados)} arquivo(s).')
    print(f'Salvo: {out} e {p}')
    if len({x[0] for x in acumulado})<25:
        print('AVISO: menos de 25 UFs localizadas. Verifique se este ZIP é completo.')
    return len(acumulado)


def main():
    a=ArgumentParser(description='Ler dados históricos presidenciais TSE de arquivos ZIP originais')
    a.add_argument('--zip2022',help='Arquivo ZIP da votação por município/zona de 2022')
    a.add_argument('--zip2026',help='Arquivo ZIP da votação por município/zona de 2026 (primeiro turno)')
    args=a.parse_args()
    if not args.zip2022 and not args.zip2026:
        a.error('Indique ao menos um arquivo --zip2022 ou --zip2026')
    if args.zip2022: importar_zip(args.zip2022,2022,2)
    if args.zip2026: importar_zip(args.zip2026,2026,1)
    print('Concluído. Reinicie/atualize o painel para carregar as novas bases.')

if __name__=='__main__':main()
