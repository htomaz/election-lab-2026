"""Pseudo-backtest reprodutível, NÃO valida o 2º turno de 2026.

Histórico único dos modelos: 2022T2. Alvo: 2026T1, participação de Lula
entre Lula e candidato 22. A lista de zonas do alvo é tratada como cadastro
pré-existente SEM votos; cenários extremos usam resultados futuros só para
definir a ordem (stress test, não simulação da divulgação real de seções).
"""
import argparse
import csv
import random
from collections import defaultdict
from modelo import projetar_locais
from modelo_zonas import carregar_zonas, projetar_zonas
from tse import UFS

PROGRESSOS=(5,10,20,30,50,70,90,100)


def executar(caminho, sementes=range(10)):
    dados=carregar_zonas(caminho)
    historia={k:{(2022,2):v[(2022,2)]} for k,v in dados.items() if (2022,2) in v}
    alvo={k:v[(2026,1)] for k,v in dados.items() if (2026,1) in v}
    chaves=list(alvo)
    if not chaves:raise ValueError('Histórico de 2026 ausente')
    verdade_l=sum(v['lula'] for v in alvo.values())
    verdade_f=sum(v['direita'] for v in alvo.values())
    verdade=100*verdade_l/(verdade_l+verdade_f)
    uf_hist=defaultdict(lambda:{(2022,2):{'lula':0,'direita':0,'validos':0}})
    for (uf,_,_), x in historia.items():
        for c in ('lula','direita','validos'):
            uf_hist[uf][(2022,2)][c]+=x[(2022,2)][c]
    ztotal=defaultdict(int)
    for uf,_,_ in chaves:ztotal[uf]+=1

    def indice_selecao(obs):
        soma=total=0.
        selecionadas=defaultdict(lambda:[0,0])
        for k in obs:
            h=historia.get(k,{}).get((2022,2))
            if h:
                selecionadas[k[0]][0]+=h['lula']
                selecionadas[k[0]][1]+=h['direita']
        for uf,reg in uf_hist.items():
            h=reg[(2022,2)]
            volume=h['validos'];total+=volume
            parte=selecionadas[uf]
            if sum(parte):
                pp=h['lula']/(h['lula']+h['direita'])
                soma+=volume*abs(parte[0]/sum(parte)-pp)
        return 100*soma/total

    cenarios=[('aleatorio_'+str(i),i) for i in sementes]+[
        ('pro_lula_primeiro',None),('pro_direita_primeiro',None),('maiores_primeiro',None)]
    rows=[]
    for nome,seed in cenarios:
        order=chaves.copy()
        if seed is not None:random.Random(seed).shuffle(order)
        elif nome=='maiores_primeiro':
            order.sort(key=lambda k:alvo[k]['validos'],reverse=True)
        else:
            order.sort(key=lambda k:alvo[k]['lula']/max(1,alvo[k]['lula']+alvo[k]['direita']),
                       reverse=nome=='pro_lula_primeiro')
        for pct in PROGRESSOS:
            n=max(1,round(len(order)*pct/100))
            obs={k:{'lula':alvo[k]['lula'],'flavio':alvo[k]['direita'],
                    'validos':alvo[k]['validos'],'secoes':1,'secoes_total':1} for k in order[:n]}
            agreg=defaultdict(lambda:{'lula':0,'flavio':0,'validos':0,'secoes':0})
            for (uf,_,_), x in obs.items():
                for c in ('lula','flavio','validos'):agreg[uf][c]+=x[c]
                agreg[uf]['secoes']+=1
            poruf={uf:{**agreg[uf],'secoes_total':ztotal[uf]} for uf in UFS}
            estado=projetar_locais(poruf,uf_hist,peso_2026=0)
            if not estado['completo']:
                raise ValueError('Cobertura territorial insuficiente')
            uf_pct=estado['lula_pct']
            # Nunca alimenta o modelo com os votos de 2026 não revelados.
            zona0=projetar_zonas(obs,historia,peso_2026=0,intensidade=0,
                                  universo=set(chaves))['lula_pct']
            zona35=projetar_zonas(obs,historia,peso_2026=0,intensidade=.35,
                                   universo=set(chaves))['lula_pct']
            indice=indice_selecao(obs)
            # Limiar exploratório escolhido neste mesmo exercício, sem holdout.
            beta=min(.9,max(0.,(indice-4.)/4.))
            misto=uf_pct*(1-beta)+zona35*beta
            for modelo,valor in [('UF_atual',uf_pct),('zona_estatica',zona0),
                                 ('zona_adaptativa',zona35),('hibrido',misto)]:
                rows.append({'cenario':nome,'progresso_zonas_pct':pct,'modelo':modelo,
                             'estimado_pct':round(valor,4),'verdade_pct':round(verdade,4),
                             'erro_pp':round(valor-verdade,4),
                             'erro_abs_pp':round(abs(valor-verdade),4),
                             'indice_selecao_pp':round(indice,4),'peso_zonal':round(beta,4)})
    return rows


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--zonas',default='historico_zonas.csv')
    a.add_argument('--saida',default='backtest_comparativo.csv')
    args=a.parse_args()
    rows=executar(args.zonas)
    with open(args.saida,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print(f'{len(rows)} resultados escritos: {args.saida}')
