"""Resumo auditável de backtest: apuração de zonas, votos e participação.

Não altera parâmetros. Trabalha sobre CSVs produzidos pelos scripts
retrospectivos já existentes e distingue aleatorização de stress tests.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from statistics import mean
from pathlib import Path


def ler(path):
    with open(path,encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))


def resumo_votos(rows):
    groups=defaultdict(list)
    for row in rows:
        scenario=row["cenario"]
        cls="aleatoria" if scenario.startswith("aleatorio_") else "ordem_extrema"
        key=(cls,int(row["progresso_zonas_pct"]),row["modelo"])
        groups[key].append(float(row["erro_pp"]))
    out=[]
    for (classe,etapa,modelo),errors in sorted(groups.items()):
        if (classe=="aleatoria" and len(errors)!=10 or
            classe=="ordem_extrema" and len(errors)!=3):
            raise ValueError("Número de cenários inesperado")
        out.append({"alvo":"2026T1_vs_2022T2_proxy",
                    "variavel":"margem_lula_pp",
                    "selecao":classe,"progresso_pct":etapa,
                    "modelo":modelo,"n_cenarios":len(errors),
                    "mae":round(mean(map(abs,errors)),4),
                    "erro_assinado_medio":round(mean(errors),4),
                    "erro_max_abs":round(max(map(abs,errors)),4)})
    if len(rows)!=416:raise ValueError("Esperadas 416 previsões de votos")
    return out


def resumo_participacao(rows):
    groups=defaultdict(list)
    for row in rows:
        if row["variavel"] not in ("validos","comparecimento","brancos","nulos"):
            continue
        modelo=row["modelo"]
        intensidade=float(row["intensidade"])
        if (modelo=="historico" and intensidade!=0 or
            modelo!="historico" and intensidade!=.30):
            continue
        cls="aleatoria" if row["cenario"].startswith("aleatorio_") else "ordem_prior"
        key=(cls,int(row["progresso_zonas_pct"]),modelo,row["variavel"])
        # Percentual do total nacional verdadeiro; NÃO pontos percentuais.
        groups[key].append(float(row["erro_abs_pct"]))
    out=[]
    for (classe,etapa,modelo,variavel),errors in sorted(groups.items()):
        if len(errors)!=4:raise ValueError("Quatro cenários esperados por grupo")
        out.append({"alvo":"2022T2_vs_2022T1_temporal",
                    "variavel":variavel+"_erro_relativo_pct",
                    "selecao":classe,"progresso_pct":etapa,
                    "modelo":modelo+("_30" if modelo!="historico" else ""),
                    "n_cenarios":len(errors),
                    "mae":round(mean(errors),5),
                    "erro_assinado_medio":None,
                    "erro_max_abs":round(max(errors),5)})
    if len(rows)!=3328:raise ValueError("Esperadas 3328 previsões de participação")
    return out


def formatar(cab, rows, etapas, modelos):
    print("\n"+cab)
    print("Etapa   "+"  ".join(f"{m:>17}" for m in modelos))
    for etapa in etapas:
        x=[]
        for modelo in modelos:
            z=[r for r in rows if r["progresso_pct"]==etapa and r["modelo"]==modelo]
            if len(z)!=1:raise ValueError(f"Sem resultado único {etapa}/{modelo}")
            x.append(f"{z[0]['mae']:>17.4f}")
        print(f"{etapa:>3}%    "+"  ".join(x))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--votos",required=True)
    p.add_argument("--participacao",required=True)
    p.add_argument("--saida",required=True)
    args=p.parse_args()
    v=resumo_votos(ler(args.votos))
    a=resumo_participacao(ler(args.participacao))
    rows=v+a
    with open(args.saida,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    stages=(5,10,20,30,50,70,90,100)
    mods=("UF_atual","zona_estatica","zona_adaptativa","hibrido")
    formatar("VOTOS — MAE em p.p. (2026 1ºT: Lula / (Lula + 22); 10 ordens aleatórias)",
             [r for r in v if r["selecao"]=="aleatoria"],stages,mods)
    formatar("VOTOS — MAE em p.p. (3 cenários extremos; NÃO são cronologia real)",
             [r for r in v if r["selecao"]=="ordem_extrema"],stages,mods)
    mods2=("historico","ajuste_uf_30","hierarquico_30")
    formatar("VÁLIDOS — MAE relativo ao total BR em % (2022 1ºT -> 2ºT; 4 ordens aleatórias)",
             [r for r in a if r["selecao"]=="aleatoria" and r["variavel"]=="validos_erro_relativo_pct"],
             stages,mods2)
    formatar("COMPARECIMENTO — MAE relativo ao BR em % (2022 1ºT -> 2ºT; 4 ordens aleatórias)",
             [r for r in a if r["selecao"]=="aleatoria" and r["variavel"]=="comparecimento_erro_relativo_pct"],
             stages,mods2)
    for etapa in (5,20,50,90):
        subset=[r for r in v if r["selecao"]=="aleatoria"
                and r["progresso_pct"]==etapa]
        champion=min(subset,key=lambda r:r["mae"])
        print("MELHOR_VOTOS_ALEATORIO",json.dumps(
            {"progresso_pct":etapa,"modelo":champion["modelo"],
             "mae_pp":champion["mae"]},ensure_ascii=False))
    print("BACKTEST_TOTAL",json.dumps(
        {"comparativo_linhas":416,"participacao_linhas":3328,
         "resumos_linhas":len(rows),
         "aviso":"Proxy 2026T1 não é segundo turno 2026 e ordem de zonas não é ordem das seções reais."},
        ensure_ascii=False))


if __name__=="__main__":
    main()
