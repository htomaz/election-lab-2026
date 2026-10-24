"""Coletor controlado de TODAS as combinações município/zona via EA12 e EA20.

Execução sob demanda, não é serviço permanente nem atualiza em background.
Persistência atômica em JSON para recuperação incremental após interrupções.

Uso após iniciar a apuração: 
  python coletor_zonal.py --uf SP --limite 300
  python coletor_zonal.py --todas --limite 10000 --taxa 12

O TSE informa limite global de 100 req/s por IP e bloqueios após 404.
Por padrão usamos 12 req/s e suspendemos a rodada após 403/404/429.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time

import requests

from auditoria_ao_vivo import validar_substituicao
from motor_zonal_completo import chave_zona, id_zona
from tse import ELEICAO, UFS, baixar_zona, resultado_disponivel

EA12_URL = (
    f'https://resultados.tse.jus.br/oficial/ele2026/{ELEICAO}/'
    f'config/mun-e{ELEICAO:06d}-cm.json'
)
BLOQUEANTES = ('403','404','429')


def catalogar_ea12(payload):
    """Somente zonas listadas na configuração oficial, evitando URLs inventadas."""
    if not isinstance(payload,dict) or not isinstance(payload.get('abr'),list):
        raise ValueError('EA12 sem abrangências')
    catalogo={}
    for local in payload['abr']:
        uf=str(local.get('cd','')).upper().strip()
        if uf not in UFS:
            continue
        for mu in local.get('mu',[]):
            nome=str(mu.get('nm','')).strip()
            for z in mu.get('zon',[]):
                chave=chave_zona(uf,mu.get('cd',''),z.get('cd',''))
                if chave in catalogo:
                    raise ValueError(f'Chave duplicada EA12: {chave}')
                catalogo[chave]={'uf':chave[0],'municipio':chave[1],
                                 'zona':chave[2],'nome':nome}
    if not catalogo:
        raise ValueError('EA12 sem zonas; não iniciar coleta')
    return catalogo


def baixar_catalogo(http_get=None):
    pegar=http_get or requests.get
    resposta=pegar(EA12_URL,timeout=(5,25),
                   headers={'User-Agent':'ElectionLab2026/0.6 (catalogo EA12 TSE)'})
    resposta.raise_for_status()
    return catalogar_ea12(resposta.json())


def carregar_arquivo(caminho):
    caminho=Path(caminho)
    if not caminho.exists():
        return {'versao':1,'eleicao':ELEICAO,'catalogo_origem':'EA12_TSE_6258',
                'catalogo':[],'observacoes':{},'atualizado_em':None,
                'erros_ultima_rodada':[]}
    with caminho.open(encoding='utf-8') as f:
        dados=json.load(f)
    if dados.get('versao')!=1 or dados.get('eleicao')!=ELEICAO:
        raise ValueError('O snapshot existente pertence a outra eleição/formato')
    if not isinstance(dados.get('observacoes'),dict):
        raise ValueError('O snapshot existente está corrompido')
    return dados


def salvar_atomico(caminho,dados):
    """Arquivo temporário no mesmo diretório + substituição atômica."""
    destino=Path(caminho)
    destino.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=str(destino.parent),prefix='.zonas-',suffix='.json')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(dados,f,ensure_ascii=False,separators=(',',':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,destino)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _is_bloqueio(erro):
    return bool(erro and any(c in str(erro) for c in BLOQUEANTES))


def coletar(caminho, uf=None, todas=False, limite=300, taxa=12.,
            concorrencia=8, renovar_apos=120, agora=None, origem=None,
            coletar_zona=None, permitir_antes=False, clock=None, sleep=None):
    """Consulta até limite zonas priorizando faltantes/vencidas.

    Testes podem injetar catálogo, coletor e relógio sem acessar a rede.
    Nunca apresenta observações não coletadas como votos oficiais.
    """
    if not (todas or uf) or (todas and uf):
        raise ValueError('Informe exatamente --uf ou --todas')
    if uf and uf.upper() not in UFS:
        raise ValueError('UF inválida')
    if not 1 <= limite <= 20000 or not 0 < taxa <= 30 or not 1 <= concorrencia <= 16:
        raise ValueError('Limite/taxa/concorrência fora da faixa segura')
    if renovar_apos < 0:
        raise ValueError('Idade de renovação inválida')
    if not permitir_antes and not resultado_disponivel():
        raise ValueError('A apuração oficial de 25/10 ainda não começou')
    clock=clock or time.time
    sleep=sleep or time.sleep
    catalogo=origem if origem is not None else baixar_catalogo()
    if not catalogo:
        raise ValueError('Catálogo vazio')
    if qualquer:=({k[0] for k in catalogo} - set(UFS)):
        raise ValueError(f'UFs inválidas: {qualquer}')
    dados=carregar_arquivo(caminho)
    dados['catalogo']=[catalogo[k] for k in sorted(catalogo)]
    dados['catalogo_origem']='EA12_TSE_6258' if origem is None else 'EA12_TSE_6258'
    antigo=dados['observacoes']
    # Atribuir novas chaves somente depois de validar o catálogo. Elimina extintas.
    conjunto={id_zona(k) for k in catalogo}
    dados['observacoes']={k:v for k,v in antigo.items() if k in conjunto}
    anteriores=dados['observacoes']
    alvo=[k for k in sorted(catalogo) if todas or k[0]==uf.upper()]
    def ultima_coleta(k):
        return float(anteriores.get(id_zona(k),{}).get('capturado_em',0) or 0)
    # Não consultadas antes das atualizadas recentemente; dado de 1 minuto não é novo.
    instante=clock() if agora is None else agora
    alvo.sort(key=lambda k: (ultima_coleta(k)>0, ultima_coleta(k),k))
    alvo=[k for k in alvo if instante-ultima_coleta(k) >= renovar_apos][:limite]
    buscar=coletar_zona or baixar_zona
    pendentes={}
    processadas=0
    aceitas=0
    erros=[]
    bloqueio=False

    with ThreadPoolExecutor(max_workers=concorrencia) as pool:
        cursor=iter(alvo)
        prox_tempo=clock()

        def submeter():
            nonlocal processadas,prox_tempo
            try:
                chave=next(cursor)
            except StopIteration:
                return False
            # Throttle GLOBAL da rodada (não por worker), inclusive em rede lenta.
            intervalo=max(0.,prox_tempo-clock())
            if intervalo:
                sleep(intervalo)
            prox_tempo=max(prox_tempo,clock())+1./taxa
            tarefa=pool.submit(buscar,*chave)
            pendentes[tarefa]=chave
            processadas+=1
            return True

        for _ in range(min(concorrencia,len(alvo))):
            submeter()
        while pendentes:
            concluido,_=wait(set(pendentes),return_when=FIRST_COMPLETED)
            for futuro in concluido:
                chave=pendentes.pop(futuro)
                try:
                    obs,erro=futuro.result()
                except Exception as exc:
                    obs,erro=None,f'{type(exc).__name__}: {exc}'
                if erro:
                    erros.append({'zona':id_zona(chave),'erro':str(erro)[:180]})
                    bloqueio=bool(bloqueio or _is_bloqueio(erro))
                elif obs:
                    k=id_zona(chave)
                    observacao={**obs,'capturado_em':clock()}
                    ok,motivo=validar_substituicao(anteriores.get(k),observacao)
                    if ok:
                        anteriores[k]=observacao
                        aceitas+=1
                    else:
                        erros.append({'zona':k,'erro':motivo})
                else:
                    erros.append({'zona':id_zona(chave),'erro':'Resposta vazia'})
            if not bloqueio:
                while len(pendentes)<concorrencia and submeter():
                    pass

    dados['atualizado_em']=datetime.now(timezone.utc).isoformat()
    dados['erros_ultima_rodada']=erros[:30]
    dados['interrompido_por_bloqueio']=bloqueio
    salvar_atomico(caminho,dados)
    return {'catalogo':len(catalogo),'zona_alvo':len(alvo),
            'requisicoes':processadas,'atualizadas':aceitas,
            'erros':len(erros),'interrompido':bloqueio,'arquivo':str(caminho),
            'zonas_com_snapshot':len(anteriores)}


def main():
    p=argparse.ArgumentParser(description='Coletar parciais oficiais EA20 por zona eleitoral')
    alvo=p.add_mutually_exclusive_group(required=True)
    alvo.add_argument('--uf',choices=UFS)
    alvo.add_argument('--todas',action='store_true')
    p.add_argument('--limite',type=int,default=300)
    p.add_argument('--taxa',type=float,default=12.,
                   help='Número máximo de consultas por segundo (máximo 30)')
    p.add_argument('--concorrencia',type=int,default=8)
    p.add_argument('--renovar-apos',type=int,default=120,
                   help='Não consultar novamente uma zona coletada há menos de N segundos')
    p.add_argument('--saida',default='dados_zonais_6258.json')
    args=p.parse_args()
    try:
        resultado=coletar(args.saida,uf=args.uf,todas=args.todas,limite=args.limite,
                          taxa=args.taxa,concorrencia=args.concorrencia,
                          renovar_apos=args.renovar_apos)
        print(json.dumps(resultado,ensure_ascii=False,indent=2))
        if resultado['interrompido']:
            p.exit(3,'Consultas interrompidas após erro de acesso do TSE.\n')
    except (ValueError,OSError,requests.RequestException) as exc:
        p.exit(2,f'Coleta não homologada: {type(exc).__name__}: {exc}\n')


if __name__=='__main__':
    main()
