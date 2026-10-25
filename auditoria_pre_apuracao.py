"""Auditoria independente do cadastro pré-apuração (2026, 2º turno).

Compara EA11, EA16 (28 UFs, zona/seções) e EA20 (BR + 28 UFs).
Nunca infere nem fabrica votos. Falhas de rede ou divergências NÃO são
tratadas como reconciliação. Relatório JSON persistido inclusive em falha.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

from coletor_zonal import baixar_catalogo
from modelo_zonas import carregar_zonas
from preflight_tse import consultar_config
from tse import UFS, baixar_um

PLEITO = 3221
ELEICAO = 6258


def comparar_catalogo(catalogo, oficiais, historico=None, exigir_sem_votos=True):
    """Conferência puramente determinística; dados já normalizados e auditados."""
    erros = []
    if not catalogo or not isinstance(catalogo,dict):
        raise ValueError("Sem catálogo oficial EA16")
    ufs_ea16 = {k[0] for k in catalogo}
    if ufs_ea16 != set(UFS):
        erros.append("EA16 não contém exatamente 28 abrangências: "
                     +repr(sorted(set(UFS)-ufs_ea16)))
    if set(oficiais) != set(UFS)|{'BR'}:
        erros.append("EA20 BR/UF incompletos: "
                     +repr(sorted((set(UFS)|{'BR'})-set(oficiais))))
    historico = historico or {}
    ant = {k for k,periodos in historico.items() if (2026,1) in periodos}
    ufs = []
    total_ea16 = 0
    total_ea20 = 0
    total_aptos = 0
    for uf in UFS:
        items = {k:v for k,v in catalogo.items() if k[0] == uf}
        se = sum(int(x['secoes_cadastradas_ea16']) for x in items.values())
        total_ea16 += se
        hist = {k for k in ant if k[0]==uf}
        cobertura = 100*len(set(items)&hist)/len(hist) if hist else None
        oficial = oficiais.get(uf)
        saida = {'uf':uf,'zonas_ea16':len(items),'secoes_ea16':se,
                 'secoes_ea20':None,'eleitorado_ea20':None,
                 'cobertura_historica_pct':round(cobertura,3)
                 if cobertura is not None else None,
                 'zonas_historicas_sem_correspondencia':len(hist-set(items))}
        if cobertura is not None and cobertura <95:
            erros.append(f"{uf}: cobertura EA16 de 2026T1 abaixo de 95%: {cobertura:.2f}%")
        if oficial:
            ts = int(oficial['secoes_total'])
            te = oficial.get('aptos')
            saida['secoes_ea20']=ts
            saida['eleitorado_ea20']=te
            total_ea20+=ts
            if te is not None: total_aptos+=int(te)
            else: erros.append(f"{uf}: eleitorado EA20 ausente")
            if ts != se:
                erros.append(f"{uf}: EA16 possui {se} seções, EA20 informa {ts}")
            if exigir_sem_votos and (oficial['secoes']!=0 or oficial['validos']!=0):
                erros.append(f"{uf}: apuração começou; auditoria pré-apuração não aplicável")
        else:
            erros.append(f"{uf}: EA20 indisponível")
        ufs.append(saida)
    br = oficiais.get('BR')
    resumo = {
        'pleito':PLEITO,'eleicao':ELEICAO,'gerado_em_utc':
            datetime.now(timezone.utc).isoformat(),
        'ufs_esperadas':len(UFS),'zonas_ea16':len(catalogo),
        'zonas_historicas_t1':len(ant),
        'secoes_ea16':total_ea16,'secoes_ea20_ufs':total_ea20,
        'secoes_ea20_br':br['secoes_total'] if br else None,
        'eleitorado_ea20_ufs':total_aptos,
        'eleitorado_ea20_br':br.get('aptos') if br else None,
        'geracao_ea20_br':br.get('geracao') if br else None,
        'auditoria_sem_votos':exigir_sem_votos,
        'por_uf':ufs,'divergencias':erros
    }
    if len(catalogo)<6000 or len(catalogo)>10000:
        erros.append(f"EA16: {len(catalogo)} zonas fora da faixa prevista")
    if br:
        if br['secoes_total'] != total_ea16:
            erros.append(f"BR EA20 {br['secoes_total']} seções != EA16 {total_ea16}")
        if br['secoes_total'] != total_ea20:
            erros.append(f"BR EA20 {br['secoes_total']} seções != soma UF {total_ea20}")
        if br.get('aptos') != total_aptos:
            erros.append(f"BR EA20 {br.get('aptos')} eleitores != soma UF {total_aptos}")
        if exigir_sem_votos and (br['secoes']!=0 or br['validos']!=0):
            erros.append("BR: há seções/votos observados; pré-apuração encerrada")
    else: erros.append("BR EA20 indisponível")
    resumo['status']='reconciliado' if not erros else 'divergente_ou_incompleto'
    return resumo


def buscar_agregados():
    dados={}
    erros={}
    # Máximo de 5 conexões, conforme coletor oficial do Election Lab.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(baixar_um,uf):uf for uf in ['BR',*UFS]}
        for futuro in as_completed(futures):
            uf, resultado, erro=futuro.result()
            if erro: erros[uf]=erro
            elif resultado: dados[uf]=resultado
            else: erros[uf]="Sem resposta"
    return dados, erros


def executar(destino, exigir_sem_votos=True):
    info={'tipo':'auditoria_antes_da_apuracao',
          'pleito':PLEITO,'eleicao':ELEICAO,'status':'inconclusivo'}
    try:
        config=consultar_config()
        info['configuracao_ea11']=config
        if not config['pleito_2turno_confirmado']:
            raise ValueError("EA11 não confirmou 3221/6258")
        catalogo=baixar_catalogo(pleito=PLEITO)
        info['catalogo_consultado']='EA16_TSE_3221'
        resultados,falhas=buscar_agregados()
        info['falhas_download_ea20']=falhas
        info.update(comparar_catalogo(
            catalogo,resultados,carregar_zonas(),exigir_sem_votos))
        if falhas:
            info['divergencias'].append('Download EA20 incompleto: '+repr(falhas))
            info['status']='divergente_ou_incompleto'
    except Exception as exc:
        info['status']='inconclusivo'
        info['erro_executar']=f"{type(exc).__name__}: {str(exc)[:700]}"
    finally:
        Path(destino).write_text(json.dumps(
            info,ensure_ascii=False,indent=2),encoding='utf-8')
    return info


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--saida',default='/tmp/auditoria_pre_25out26.json')
    p.add_argument('--permitir-apuracao',action='store_true')
    args=p.parse_args()
    r=executar(args.saida,exigir_sem_votos=not args.permitir_apuracao)
    print(json.dumps({k:v for k,v in r.items() if k!='por_uf'},
                     indent=2,ensure_ascii=False))
    if r['status']!='reconciliado':
        raise SystemExit(2)


if __name__=='__main__':
    main()
