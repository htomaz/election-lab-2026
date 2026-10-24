"""Calibração por blocos de UF fora da amostra (espacial, NÃO temporal).

Usa pseudo-apuração 2022T2 com ordem conhecida apenas pela primeira rodada.
Otimiza intensidade usando *erros de treino* e avalia em UFs disjuntas.
Isto impede selecionar e relatar no MESMO conjunto de UFs; mas todas
são da mesma eleição, não satisfaz validação prospectiva de 2026.
"""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict

from backtest_participacao import (
    ETAPAS,INTENSIDADES,CAMPOS,compilar_base,cenarios,estimar
)


def calibrar(arquivo='historico_participacao_zonas.csv',
             seeds=range(4),etapas=ETAPAS,intensidades=INTENSIDADES):
    priors,alvos=compilar_base(arquivo)
    ufs=sorted({k[0] for k in alvos})
    grupos=(set(ufs[::2]),set(ufs[1::2]))
    verdade=defaultdict(float)
    for (uf,_,_),v in alvos.items():
        verdade[uf]+=v['validos']
    partes=[]
    for nome,ordem in cenarios(priors,alvos,seeds):
        for pct in etapas:
            if pct==100: continue
            n=max(1,round(len(ordem)*pct/100))
            obs=ordem[:n]
            for metodo in ('historico','ajuste_uf','hierarquico'):
                for intensidade in ((0.,) if metodo=='historico' else intensidades):
                    _,uf_est=estimar(priors,alvos,obs,intensidade,metodo)
                    # Valores revelados pertencem ao conjunto de evidências.
                    # Só os ALVOS restantes são ocultados pelo algoritmo.
                    for uf in ufs:
                        partes.append({
                            'uf':uf,'cenario':nome,'progresso':pct,
                            'modelo':metodo,'intensidade':intensidade,
                            'erro_abs':abs(uf_est[uf]['validos']-verdade[uf]),
                            'verdade':verdade[uf],
                        })
    saida=[]
    for fold,test_set in enumerate(grupos,1):
        treino=set(ufs)-test_set
        for metodo in ('historico','ajuste_uf','hierarquico'):
            escolhas=(0.,) if metodo=='historico' else intensidades
            medias=[]
            for intensidade in escolhas:
                linhas=[r for r in partes if r['modelo']==metodo
                       and r['intensidade']==intensidade
                       and r['uf'] in treino]
                mae=sum(r['erro_abs'] for r in linhas)/len(linhas)
                medias.append((mae,intensidade))
            _,escolhida=min(medias)
            valida=[r for r in partes if r['uf'] in test_set
                    and r['modelo']==metodo and r['intensidade']==escolhida]
            por_uf=defaultdict(list)
            for r in valida:
                por_uf[r['uf']].append(r['erro_abs'])
            for uf,valores in sorted(por_uf.items()):
                saida.append({
                  'fold':fold,'uf_teste':uf,'modelo':metodo,
                  'intensidade_escolhida_apenas_no_treino':escolhida,
                  'mae_validos_uf':round(sum(valores)/len(valores),2),
                  'mae_validos_uf_pct':round(100*sum(valores)/len(valores)/
                                              max(1,verdade[uf]),4),
                  'observacoes':len(valores),'tipo_validacao':(
                      'espacial_por_uf_2022T2_nao_prospectiva')
                })
    return saida


def resumo_folds(rows):
    saida=[]
    for m in ('historico','ajuste_uf','hierarquico'):
        grupo=[r for r in rows if r['modelo']==m]
        if not grupo: continue
        saida.append({'modelo':m,'mae_medio_pct_por_uf':round(
                         sum(x['mae_validos_uf_pct'] for x in grupo)/len(grupo),4),
                      'mae_medio_validos_por_uf':round(
                         sum(x['mae_validos_uf'] for x in grupo)/len(grupo),2),
                      'ufs_testadas':len(grupo),
                      'validacao':'holdout espacial, não temporal'})
    return sorted(saida,key=lambda x:x['mae_medio_pct_por_uf'])


def salvar(path,rows):
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dados',default='historico_participacao_zonas.csv')
    p.add_argument('--saida',default='calibracao_participacao_ufs.csv')
    p.add_argument('--resumo',default='resumo_calibracao_participacao.csv')
    a=p.parse_args()
    rows=calibrar(a.dados)
    salvar(a.saida,rows)
    res=resumo_folds(rows)
    salvar(a.resumo,res)
    print('Comparação de erro absoluto com seleção de parâmetros só nas UFs',
          'de treino:',res)


if __name__=='__main__':
    main()
