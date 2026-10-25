"""Ensaio offline de interrupção/retomada de 6.292 consultas zonais.

NENHUMA requisição à internet; dados sintéticos e catálogo injetado.
Confere arquivo atômico, recomeço, ausência de dupla contagem e limites.
"""
import json
import tempfile
import time
from pathlib import Path

from coletor_zonal import coletar
from modelo_zonas import carregar_zonas
from tse import UFS


def executar():
    h=carregar_zonas('historico_zonas.csv')
    catalogo={k:{'uf':k[0],'municipio':k[1],'zona':k[2],
                  'nome':'SIMULACAO','secoes_cadastradas_ea16':1}
              for k,v in h.items() if (2026,1) in v}
    if len(catalogo)!=6292:
        raise AssertionError('Universo sintético deveria ter 6292 zonas')
    agora=[1800000000.]
    contagem=[0]

    def buscar(uf,municipio,zona):
        contagem[0]+=1
        hist=h[(uf,municipio,zona)][(2026,1)]
        votos=hist['validos']
        par=hist['lula']+hist['direita']
        l=round(votos*hist['lula']/par) if par else round(votos/2)
        return {'lula':l,'flavio':votos-l,'validos':votos,
                'uf':uf,'municipio':municipio,'zona':zona,
                'secoes':1,'secoes_total':1,
                'geracao':'25/10/2026 18:00:00'},None

    t0=time.monotonic()
    with tempfile.TemporaryDirectory() as pasta:
        local=Path(pasta)/'dados_6258.json'
        kw={'origem':catalogo,'coletar_zona':buscar,
            'permitir_antes':True,'todas':True,'taxa':12.,
            'concorrencia':8,'clock':lambda:agora[0],
            'sleep':lambda t:None}
        primeiro=coletar(local,limite=500,**kw)
        parcial=json.loads(local.read_text(encoding='utf-8'))
        if primeiro['atualizadas']!=500 or len(parcial['observacoes'])!=500:
            raise AssertionError('Falha no checkpoint inicial')
        segundo=coletar(local,limite=10000,**kw)
        inteiro=json.loads(local.read_text(encoding='utf-8'))
        if segundo['atualizadas']!=5792 or len(inteiro['observacoes'])!=6292:
            raise AssertionError('A retomada perdeu ou duplicou zonas')
        terceiro=coletar(local,limite=10000,**kw)
        if terceiro['requisicoes']!=0 or contagem[0]!=6292:
            raise AssertionError('Reconsulta indevida de zonas recentes')
        if inteiro.get('catalogo_origem')!='CATALOGO_INJETADO_TESTE':
            raise AssertionError('Simulação não pode aparentar coleta oficial')
        agora[0]+=200
        retomar=coletar(local,limite=50,**kw)
        if retomar['requisicoes']!=50:
            raise AssertionError('Falha na revisão incremental após janela')
        total=time.monotonic()-t0
        if total>60:
            raise AssertionError('Simulação do coletor excedeu 60 segundos')
        return {'zonas':len(catalogo),'primeira_coleta':primeiro['atualizadas'],
                'segunda_coleta':segundo['atualizadas'],
                'consultas_evitadas':len(catalogo)-terceiro['requisicoes'],
                'reconsulta_apos_200s':retomar['requisicoes'],
                'duracao_total_s':round(total,3),
                'tamanho_snapshot_mb':round(local.stat().st_size/1048576,2)}


if __name__=='__main__':
    print(json.dumps(executar(),indent=2,ensure_ascii=False))
