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
from contextlib import contextmanager
try:
    import fcntl
except ImportError:  # Windows
    fcntl=None

import requests

from auditoria_ao_vivo import validar_substituicao
from motor_zonal_completo import chave_zona, id_zona
from preflight_tse import consultar_config
from tse import ELEICAO, UFS, baixar_zona, resultado_disponivel

PLEITO = 3221  # Eleições gerais 2026 - segundo turno
EA16_URL = (
    'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/'
    f'{PLEITO}/config/{{uf}}/{{uf}}-p{PLEITO:06d}-cs.json'
)
BLOQUEANTES = ('403','404','429')


def catalogar_ea16(payload, uf=None):
    """Transforma EA16 UF→município→zona→seção em catálogo de zonas válidas.

    A lista de municípios EA12 NÃO contém necessariamente os vínculos por
    zona; estes estão no arquivo EA16 de configuração de seções.
    """
    if not isinstance(payload,dict) or not isinstance(payload.get('abr'),list):
        raise ValueError('EA16 sem abrangências')
    catalogo={}
    encontrados=set()
    for local in payload['abr']:
        local_uf=str(local.get('cd','')).upper().strip()
        if local_uf not in UFS or (uf is not None and local_uf!=uf.upper()):
            continue
        encontrados.add(local_uf)
        for mu in local.get('mu',[]):
            nome=str(mu.get('nm','')).strip()
            if not isinstance(mu.get('zon'),list):
                raise ValueError(f'EA16 sem zonas do município {local_uf}/{mu.get("cd")}')
            for z in mu['zon']:
                chave=chave_zona(local_uf,mu.get('cd',''),z.get('cd',''))
                if chave in catalogo:
                    raise ValueError(f'Chave duplicada EA16: {chave}')
                secoes=z.get('sec',[])
                if not isinstance(secoes,list) or any(
                    not isinstance(sec,dict) for sec in secoes
                ):
                    raise ValueError(f'EA16: seções inválidas {chave}')
                # EA16 "sec" contém tanto seções PRINCIPAIS quanto
                # AGREGADAS. As agregadas têm atributo nsp e seus
                # votos integram a urna principal. EA20 s.ts conta
                # somente urnas principais, não len(sec).
                ids=[str(sec.get('ns','')).zfill(4) for sec in secoes]
                if len(ids)!=len(set(ids)) or any(
                    not sec.get('ns') for sec in secoes
                ):
                    raise ValueError(f'EA16: seção duplicada/sem ID {chave}')
                agregadas=[sec for sec in secoes if
                           str(sec.get('nsp') or '').strip()]
                principais=[sec for sec in secoes if not
                            str(sec.get('nsp') or '').strip()]
                ids_principais={str(sec['ns']).zfill(4)
                                for sec in principais}
                if any(str(sec['nsp']).zfill(4) not in ids_principais
                       for sec in agregadas):
                    raise ValueError(f'EA16: nsp sem seção principal {chave}')
                catalogo[chave]={'uf':chave[0],'municipio':chave[1],
                                 'zona':chave[2],'nome':nome,
                                 'secoes_cadastradas_ea16':len(principais),
                                 'secoes_agregadas_ea16':len(agregadas),
                                 'secoes_listadas_ea16':len(secoes)}
    if not catalogo or (uf is not None and uf.upper() not in encontrados):
        raise ValueError(f'EA16 sem zonas da abrangência {uf or "BR"}')
    return catalogo


def baixar_catalogo(http_get=None, abrangencias=None, pleito=PLEITO):
    """Baixa EA16 de cada UF; usa somente zonas descritas na fonte oficial."""
    pegar=http_get or requests.get
    catalogo={}
    ufs=list(abrangencias or UFS)
    for uf in ufs:
        uf=uf.upper()
        if uf not in UFS:
            raise ValueError(f'UF EA16 inválida: {uf}')
        url=(
            'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/'
            f'{pleito}/config/{uf.lower()}/{uf.lower()}-p{pleito:06d}-cs.json'
        )
        resposta=pegar(url,timeout=(5,30),
                       headers={'User-Agent':'ElectionLab2026/0.6 (catalogo EA16 TSE)'})
        resposta.raise_for_status()
        por_uf=catalogar_ea16(resposta.json(),uf=uf)
        if set(catalogo).intersection(por_uf):
            raise ValueError(f'Zonas repetidas entre arquivos EA16: {uf}')
        catalogo.update(por_uf)
    if len(ufs)==len(UFS) and (
        len(catalogo)<5000 or {k[0] for k in catalogo}!=set(UFS)
    ):
        raise ValueError('Catálogo EA16 nacional incompleto')
    return catalogo


def carregar_arquivo(caminho):
    caminho=Path(caminho)
    if not caminho.exists():
        return {'versao':1,'eleicao':ELEICAO,'catalogo_origem':'EA16_TSE_3221',
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


@contextmanager
def _arquivo_bloqueado(caminho):
    """Evita coletas concorrentes sobre o mesmo snapshot no Linux do Streamlit.

    Lock não bloqueante: quem já está coletando continua, o segundo operador
    recebe diagnóstico e não arrisca perder progresso por concorrência.
    """
    alvo=Path(caminho)
    alvo.parent.mkdir(parents=True,exist_ok=True)
    with (alvo.parent/(alvo.name+'.lock')).open('a+b') as arq:
        if fcntl is not None:
            try:
                fcntl.flock(arq.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Já existe uma coleta usando este arquivo') from exc
            try:
                yield
            finally:
                fcntl.flock(arq.fileno(),fcntl.LOCK_UN)
        else:
            # Windows: bloquear um byte de arquivo com msvcrt.
            import msvcrt
            arq.seek(0,os.SEEK_END)
            if arq.tell()==0:
                arq.write(b'\\0')
                arq.flush()
            arq.seek(0)
            try:
                msvcrt.locking(arq.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:
                raise RuntimeError('Já existe uma coleta usando este arquivo') from exc
            try:
                yield
            finally:
                arq.seek(0)
                msvcrt.locking(arq.fileno(),msvcrt.LK_UNLCK,1)


def coletar(caminho, uf=None, todas=False, limite=300, taxa=12.,
            concorrencia=8, renovar_apos=120, agora=None, origem=None,
            coletar_zona=None, permitir_antes=False, clock=None, sleep=None):
    """Executa coleta com exclusão mútua por arquivo, inclusive na UI."""
    with _arquivo_bloqueado(caminho):
        return _coletar_impl(
            caminho,uf=uf,todas=todas,limite=limite,taxa=taxa,
            concorrencia=concorrencia,renovar_apos=renovar_apos,agora=agora,
            origem=origem,coletar_zona=coletar_zona,
            permitir_antes=permitir_antes,clock=clock,sleep=sleep)


def _catalogo_verificado_interno(catalogo):
    """Somente formato e cobertura: NÃO verifica assinatura/proveniência."""
    return len(catalogo)>=5000 and {k[0] for k in catalogo}==set(UFS)


def _cat_existente(dados):
    anterior={}
    for item in dados.get('catalogo',[]):
        try:
            k=chave_zona(item['uf'],item['municipio'],item['zona'])
            if k in anterior:
                return {}
            anterior[k]=item
        except (KeyError,ValueError,TypeError):
            return {}
    return anterior


def _is_bloqueio(erro):
    return bool(erro and any(c in str(erro) for c in BLOQUEANTES))


def _validar_observacao_zonal(chave, observacao):
    """Não permitir que respostas malformadas contaminem o snapshot oficial."""
    if not isinstance(observacao, dict):
        raise ValueError('Resposta zonal não é um objeto')
    uf, municipio, zona = chave
    if (str(observacao.get('uf','')).upper()!=uf or
        str(observacao.get('municipio','')).zfill(5)!=municipio or
        str(observacao.get('zona','')).zfill(4)!=zona):
        raise ValueError('Resposta EA20 não corresponde à zona solicitada')
    campos=('lula','flavio','validos','secoes','secoes_total')
    if any(type(observacao.get(c)) is not int or observacao[c]<0
           for c in campos):
        raise ValueError('Votos ou seções não são inteiros não negativos')
    if observacao['lula']+observacao['flavio']!=observacao['validos']:
        raise ValueError('Votos válidos divergentes dos dois candidatos')
    if observacao['secoes']>observacao['secoes_total'] or (
        observacao['validos']>0 and observacao['secoes']==0
    ):
        raise ValueError('Seções EA20 incompatíveis com os votos')
    try:
        datetime.strptime(observacao['geracao'], '%d/%m/%Y %H:%M:%S')
    except (ValueError,TypeError,KeyError) as exc:
        raise ValueError('Geração EA20 ausente ou malformada') from exc


def _coletar_impl(caminho, uf=None, todas=False, limite=300, taxa=12.,
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
    momento = datetime.fromtimestamp(agora if agora is not None else time.time(),timezone.utc)
    if not permitir_antes and not resultado_disponivel(momento):
        raise ValueError('A apuração oficial de 25/10 ainda não começou')
    clock=clock or time.time
    sleep=sleep or time.sleep
    dados=carregar_arquivo(caminho)
    # Jamais transformar votos fictícios em oficiais (nem o inverso) ao
    # reutilizar o mesmo nome de arquivo. Exigir snapshots separados.
    origem_esperada=('CATALOGO_INJETADO_TESTE' if origem is not None
                     else 'EA16_TSE_3221')
    if (dados.get('catalogo') or dados.get('observacoes')) and (
        dados.get('catalogo_origem')!=origem_esperada
    ):
        raise ValueError('Snapshot de origem diferente: não misturar '
                         'dados simulados e oficiais; use outro arquivo')
    ultimo_catalogo=_cat_existente(dados)
    data_cat=dados.get('catalogo_atualizado_em')
    idade_cat=clock()-float(data_cat) if data_cat is not None else float('inf')
    catalogo_recuperavel=(
        dados.get('catalogo_origem')=='EA16_TSE_3221' and
        0<=idade_cat<=21600 and bool(ultimo_catalogo)
    )
    renovou_catalogo=False
    if origem is not None:
        # Testes, não é fonte oficial; não mesclar com catálogos reais.
        catalogo=dict(origem)
        dados['catalogo_origem']='CATALOGO_INJETADO_TESTE'
    else:
        escopo=uf.upper() if uf else None
        ja_tem=(
            bool({k for k in ultimo_catalogo if k[0]==escopo})
            if escopo else _catalogo_verificado_interno(ultimo_catalogo)
        )
        if catalogo_recuperavel and ja_tem:
            catalogo=ultimo_catalogo
        else:
            # Não tentar adivinhar centenas de URLs EA16 se o TSE não
            # anunciou 3221/6258 no EA11. Uma única consulta de preflight.
            oficial=consultar_config()
            if not oficial['pleito_2turno_confirmado']:
                raise ValueError('TSE ainda não publicou o pleito 3221/6258 '
                                 'no arquivo EA11; coleta zonal suspensa')
            # Uma única UF NÃO precisa baixar os 28 catálogos. Preserve
            # o universo já conhecido para não apagar votos de outras UFs.
            novos=baixar_catalogo(abrangencias=[escopo] if escopo else UFS)
            renovou_catalogo=True
            # Falha segura caso o servidor responda com uma lista
            # anormalmente reduzida ou remova zonas com votos conhecidos.
            anteriores_uf={k for k in ultimo_catalogo
                           if escopo is None or k[0]==escopo}
            novas_uf={k for k in novos
                      if escopo is None or k[0]==escopo}
            if anteriores_uf and len(novas_uf)<.95*len(anteriores_uf):
                raise ValueError('EA16 reduziu mais de 5% das zonas conhecidas; '
                                 'conferência manual necessária antes de substituir')
            excluidas=anteriores_uf-novas_uf
            com_votos=[k for k in excluidas
                       if int(dados['observacoes'].get(id_zona(k),{}).get('validos',0))>0]
            if com_votos:
                raise ValueError('EA16 omitiu zonas com votos oficiais já registrados: '
                                 + str(com_votos[:4]))
            if escopo and dados.get('catalogo_origem')=='EA16_TSE_3221':
                catalogo={k:v for k,v in ultimo_catalogo.items() if k[0]!=escopo}
                catalogo.update(novos)
            else:
                catalogo=novos
        dados['catalogo_origem']='EA16_TSE_3221'
    if not catalogo:
        raise ValueError('Catálogo vazio')
    invalidas={k[0] for k in catalogo} - set(UFS)
    if invalidas:
        raise ValueError(f'UFs inválidas: {invalidas}')
    if origem is None and (renovou_catalogo or not data_cat):
        dados['catalogo_atualizado_em']=clock()
    dados['catalogo']=[catalogo[k] for k in sorted(catalogo)]
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
    falhas_consecutivas=0
    ultimo_checkpoint=time.monotonic()

    def checkpoint():
        dados['atualizado_em']=datetime.now(timezone.utc).isoformat()
        dados['erros_ultima_rodada']=erros[-30:]
        dados['interrompido_por_bloqueio']=bloqueio
        salvar_atomico(caminho,dados)

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
                    if not erro and obs:
                        _validar_observacao_zonal(chave,obs)
                except Exception as exc:
                    obs,erro=None,f'{type(exc).__name__}: {exc}'
                if erro:
                    erros.append({'zona':id_zona(chave),'erro':str(erro)[:180]})
                    falhas_consecutivas+=1
                    bloqueio=bool(bloqueio or _is_bloqueio(erro))
                elif obs:
                    k=id_zona(chave)
                    observacao={**obs,'capturado_em':clock()}
                    ok,motivo=validar_substituicao(anteriores.get(k),observacao)
                    if ok:
                        anteriores[k]=observacao
                        aceitas+=1
                        falhas_consecutivas=0
                    else:
                        erros.append({'zona':k,'erro':motivo})
                        falhas_consecutivas+=1
                else:
                    erros.append({'zona':id_zona(chave),'erro':'Resposta vazia'})
                    falhas_consecutivas+=1
                # Fail-safe: um lote de erros persistentes (timeout, 5xx ou
                # dados inválidos) não deve disparar milhares de novos GETs.
                if falhas_consecutivas>=20:
                    bloqueio=True
                    dados['motivo_bloqueio']='20 falhas consecutivas na coleta'
            if bloqueio and not dados.get('motivo_bloqueio'):
                dados['motivo_bloqueio']='HTTP 403/404/429; verificar fonte TSE'
            # Persiste parciais enquanto a coleta está em curso, não
            # somente após milhares de GETs. Recuperação após interrupção.
            if aceitas and (aceitas%100==0 or
                           time.monotonic()-ultimo_checkpoint>=20.):
                checkpoint()
                ultimo_checkpoint=time.monotonic()
            if not bloqueio:
                while len(pendentes)<concorrencia and submeter():
                    pass

    checkpoint()
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
