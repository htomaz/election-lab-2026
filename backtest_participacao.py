"""Backtest retrospectivo SEM vazamento nas observações: 2022T1 -> 2022T2.

Alvo 2022T2 totalmente conhecido apenas para pontuar erros e revelar
zonas inteiras. Nunca usa votos/comparecimento NÃO revelados para calibrar.
2018 não disponível; portanto calibração ainda é exploratória, não prospectiva.

Aptaos do 2º turno (informação do cadastro, potencialmente pré-eleitoral)
são informados como denominador e nunca confundidos com votos já apurados.
Não simula a ordem REAL da chegada das SEÇÕES dentro de uma zona.
"""
from __future__ import annotations
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from importar_participacao import carregar_participacao

ETAPAS=(5,10,20,30,50,70,90,100)
INTENSIDADES=(0.,.15,.30,.50,.75,1.)
CAMPOS=('comparecimento','validos','brancos','nulos')
LIMITES={'turnout':.12,'valid':.08,'blank':.06,'null':.06}


def limite(x,lo,hi):
    return max(lo,min(hi,x))


def razoes(item):
    aptos=item['aptos'];cmp=item['comparecimento']
    if aptos<=0 or cmp<=0:
        return None
    return {'turnout':cmp/aptos,'valid':item['validos']/cmp,
            'blank':item['brancos']/cmp,'null':item['nulos']/cmp}


def compilar_base(arquivo='historico_participacao_zonas.csv'):
    dados=carregar_participacao(arquivo)
    alvos={}
    priors={}
    for k,d in dados.items():
        if (2022,1) in d and (2022,2) in d:
            p=razoes(d[(2022,1)])
            if p is not None and d[(2022,2)]['aptos']>0:
                priors[k]=p
                alvos[k]=d[(2022,2)]
    if len(alvos)<6000:
        raise ValueError('Falta cobertura suficiente do TSE 2022T1/T2')
    return priors,alvos


def cenarios(priors,alvos,seeds=range(4)):
    """Ordem de liberação define-se APENAS por cadastro/prior de 2022T1."""
    keys=list(priors)
    itens=[(f'aleatorio_{s}',random.Random(s).sample(keys,len(keys))) for s in seeds]
    itens.extend([
        ('alta_abstencao_primeiro',sorted(keys,key=lambda k:priors[k]['turnout'])),
        ('baixa_abstencao_primeiro',sorted(keys,key=lambda k:-priors[k]['turnout'])),
        ('baixa_validade_primeiro',sorted(keys,key=lambda k:priors[k]['valid'])),
        ('maiores_eleitorados_primeiro',sorted(keys,key=lambda k:-alvos[k]['aptos']))
    ])
    return itens


def estimar(priors,alvos,observadas,intensidade=.35,modelo='ajuste_uf'):
    """Estimador fixo para avaliações cegas a qualquer zona restante."""
    if not 0<=intensidade<=1:
        raise ValueError('Intensidade inválida')
    if modelo not in ('historico','ajuste_uf','hierarquico'):
        raise ValueError('Modelo inválido')
    observadas=set(observadas)
    if not observadas <= set(priors):
        raise ValueError('Observadas fora do cadastro')
    zeros=lambda:{k:[0.,0.] for k in ('turnout','valid','blank','null')}
    estado=defaultdict(zeros);pais=zeros()
    for k in observadas:
        r=razoes(alvos[k])
        if r is None:continue
        pa=alvos[k]['aptos']
        cc=alvos[k]['comparecimento']
        for typ in ('turnout','valid','blank','null'):
            # Para médias das diferenças, pesos corretos são aptos no
            # comparecimento e presentes na validade/brancos/nulos.
            peso=pa if typ=='turnout' else cc
            for acc in (estado[k[0]],pais):
                acc[typ][0]+=peso*limite(r[typ]-priors[k][typ],
                                          -LIMITES[typ],LIMITES[typ])
                acc[typ][1]+=peso
    totais={c:0. for c in CAMPOS}
    por_uf=defaultdict(lambda:{c:0. for c in CAMPOS})
    for k,p in priors.items():
        if k in observadas:
            votos={c:float(alvos[k][c]) for c in CAMPOS}
        else:
            # Denominador do eleitorado é cadastro não-voto; suas variações
            # históricas são conhecidas ao abrir a eleição-alvo.
            aptos=alvos[k]['aptos']
            corrigidas={}
            for typ in ('turnout','valid','blank','null'):
                desvio=0.
                if modelo!='historico':
                    uf=estado[k[0]][typ]
                    br=pais[typ]
                    # Reação encolhida para não equiparar uma zona
                    # observada a uma amostra independente aleatória.
                    # Amortecimento=100 mil eleitores é hipótese fixa.
                    fu=uf[1]/(uf[1]+100000) if uf[1]>0 else 0.
                    fb=br[1]/(br[1]+1000000) if br[1]>0 else 0.
                    du=uf[0]/uf[1] if uf[1] else 0.
                    db=br[0]/br[1] if br[1] else 0.
                    if modelo=='ajuste_uf':
                        desvio=fu*du
                    else:
                        desvio=.75*fu*du+.25*fb*db
                corrigidas[typ]=limite(p[typ]+intensidade*desvio,0.,1.)
            soma=corrigidas['valid']+corrigidas['blank']+corrigidas['null']
            if soma>1:
                den=corrigidas['blank']+corrigidas['null']
                if den:
                    fator=(1-corrigidas['valid'])/den
                    corrigidas['blank']*=fator
                    corrigidas['null']*=fator
            presentes=aptos*corrigidas['turnout']
            votos={'comparecimento':presentes,
                   'validos':presentes*corrigidas['valid'],
                   'brancos':presentes*corrigidas['blank'],
                   'nulos':presentes*corrigidas['null']}
        for c in CAMPOS:
            totais[c]+=votos[c]
            por_uf[k[0]][c]+=votos[c]
    return totais,dict(por_uf)


def avaliar(arquivo='historico_participacao_zonas.csv',seeds=range(4),
            etapas=ETAPAS,intensidades=INTENSIDADES):
    priors,alvos=compilar_base(arquivo)
    verdadeira={c:sum(v[c] for v in alvos.values()) for c in CAMPOS}
    verdade_uf=defaultdict(lambda:{c:0 for c in CAMPOS})
    for k,v in alvos.items():
        for c in CAMPOS:verdade_uf[k[0]][c]+=v[c]
    saida=[]
    for scenario,order in cenarios(priors,alvos,seeds):
        for progresso in etapas:
            n=max(1,round(len(order)*progresso/100))
            observadas=order[:n]
            for metodo in ('historico','ajuste_uf','hierarquico'):
                for intensidade in ((0.,) if metodo=='historico' else intensidades):
                    total,por_uf=estimar(priors,alvos,observadas,intensidade,metodo)
                    mae_uf=sum(abs(por_uf[uf]['validos']-x['validos'])
                               for uf,x in verdade_uf.items())/len(verdade_uf)
                    for campo in CAMPOS:
                        v=total[campo]
                        saida.append({
                          'cenario':scenario,'progresso_zonas_pct':progresso,
                          'modelo':metodo,'intensidade':intensidade,
                          'variavel':campo,'estimativa':round(v,2),
                          'verdade':verdadeira[campo],
                          'erro':round(v-verdadeira[campo],2),
                          'erro_abs':round(abs(v-verdadeira[campo]),2),
                          'erro_abs_pct':round(100*abs(v-verdadeira[campo])/
                                                   max(1,verdadeira[campo]),5),
                          'mae_uf_validos':round(mae_uf,2),
                          'zonas_reveladas':n,'zonas_total':len(order)
                        })
    return saida


def resumo(rows):
    """Escolhe só uma intensidade observando erros: otimização IN-SAMPLE.

    O resumo é diagnóstico, NÃO deve alimentar hiperparâmetros de produção
    automaticamente; carece validação temporal independente.
    """
    grupos=defaultdict(list)
    for r in rows:
        if r['variavel']=='validos' and r['progresso_zonas_pct']<100:
            grupos[(r['modelo'],r['intensidade'])].append(r)
    res=[]
    for (metodo,intens),sub in grupos.items():
        res.append({'modelo':metodo,'intensidade':intens,
                    'erro_abs_medio_milhoes':round(
                        sum(x['erro_abs'] for x in sub)/len(sub)/1e6,5),
                    'erro_max_milhoes':round(
                        max(x['erro_abs'] for x in sub)/1e6,5),
                    'mae_uf_mil':round(
                        sum(x['mae_uf_validos'] for x in sub)/len(sub)/1000,3),
                    'observacoes':len(sub),
                    'calibracao':'retrospectiva_no_mesmo_alvo_nao_homologada'})
    return sorted(res,key=lambda x:x['erro_abs_medio_milhoes'])


def salvar(path,rows):
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dados',default='historico_participacao_zonas.csv')
    p.add_argument('--saida',default='backtest_participacao.csv')
    p.add_argument('--resumo',default='resumo_participacao.csv')
    a=p.parse_args()
    rows=avaliar(a.dados)
    salvar(a.saida,rows)
    sumar=resumo(rows)
    salvar(a.resumo,sumar)
    print('Backtest comparecimento 2022T2 (2022T1 referência):',
          len(rows),'linhas; melhor em amostra:',sumar[0])


if __name__=='__main__':
    main()
