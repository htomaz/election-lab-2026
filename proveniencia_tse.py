"""Proveniência defensiva de snapshots EA20, SEM alegar assinatura JWS.

Para arquivos baixados por HTTPS da URL oficial, registra hash SHA-256 do
conteúdo JSON e URL esperada. Para upload, relê algumas zonas da CDN do TSE
a pedido do operador e compara votos, geração e hash. Um hash informado
pelo próprio upload NÃO comprova autenticidade; a confirmação só vale
para as zonas efetivamente reconsultadas, no momento de cada leitura.

Assinaturas JWS/cadeia oficial de confiança exigem verificador separado
com chaves públicas autenticadas do TSE; não são simuladas aqui.
"""
from __future__ import annotations
import hashlib
import json
from urllib.parse import urlsplit
from auditoria_ao_vivo import _data_geracao
from motor_zonal_completo import chave_zona
from tse import url_resultado_zona


HOST='resultados.tse.jus.br'
CAMPOS=('lula','flavio','validos','secoes','secoes_total')


def validar_url_fonte(url,esperada=None):
    if not isinstance(url,str):
        raise ValueError('URL da fonte EA20 ausente')
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname!=HOST or u.port not in (None,443):
        raise ValueError('URL não é a origem HTTPS oficial do TSE')
    if u.username or u.password or u.query or u.fragment:
        raise ValueError('URL EA20 contém credenciais/parâmetros inesperados')
    if esperada is not None and url!=esperada:
        raise ValueError('URL EA20 não coincide com a zona esperada')
    return True


def resumo_sha256(objeto):
    if not isinstance(objeto,dict):
        raise ValueError('EA20 não é objeto JSON')
    dados=json.dumps(objeto,sort_keys=True,ensure_ascii=False,
                     separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(dados).hexdigest()


def auditar_amostra(snapshot,buscar,max_zonas=5):
    """Reconsulta no máximo cinco zonas, aleatoriamente estáveis.

    Sem hash da fonte baixada pelo coletor, confere geração e totais,
    mas informa explicitamente ausência da prova de identidade byte-a-byte.
    Nunca classifica zonas NÃO reconsultadas como autenticadas.
    """
    if not 1<=max_zonas<=10:
        raise ValueError('Amostra deve conter entre uma e dez zonas')
    itens=snapshot.get('observacoes')
    if not isinstance(itens,dict):
        raise ValueError('Snapshot com observações inválidas')
    chaves=sorted(itens)
    if not chaves:
        return {'consultadas':0,'confirmadas':0,'divergentes':0,
                'atualizadas':0,'inconclusivas':0,'detalhes':[],
                'nota':'Sem votos zonais para verificar'}
    # Ordem determinística por hash, sem privilegiar UF ou município inicial.
    ordenadas=sorted(chaves,key=lambda s:hashlib.sha256(
        s.encode('utf-8')).digest())
    amostra=ordenadas[:max_zonas]
    saida=[]
    for ident in amostra:
        try:
            k=chave_zona(*ident.split('|'))
            antigo=itens[ident]
            url=url_resultado_zona(*k)
            validar_url_fonte(antigo.get('url',url),url)
            atual,erro=buscar(*k)
            if erro or not atual:
                saida.append({'zona':ident,'status':'inconclusivo',
                              'motivo':str(erro or 'Fonte indisponível')[:120]})
                continue
            validar_url_fonte(atual.get('url',url),url)
            velha=_data_geracao(antigo.get('geracao'))
            nova=_data_geracao(atual.get('geracao'))
            if velha is None or nova is None:
                status,motivo='inconclusivo','Horários EA20 não comparáveis'
            elif nova>velha:
                status,motivo='atualizado','CDN já contém geração posterior ao arquivo'
            elif nova<velha:
                status,motivo='inconclusivo','CDN retornou geração mais antiga'
            elif any(int(antigo.get(x,-1))!=int(atual.get(x,-2))
                     for x in CAMPOS):
                status,motivo='divergente','Divergência de votos/seções na mesma geração'
            elif antigo.get('sha256_ea20') and atual.get('sha256_ea20'):
                if antigo['sha256_ea20']==atual['sha256_ea20']:
                    status,motivo='confirmado','SHA-256 e contagens coincidem'
                else:
                    status,motivo='divergente','SHA-256 divergiu na mesma geração'
            else:
                status,motivo='inconclusivo','Totais coincidem, mas falta hash verificável'
            saida.append({'zona':ident,'status':status,'motivo':motivo})
        except (ValueError,KeyError,TypeError) as exc:
            saida.append({'zona':ident,'status':'divergente',
                          'motivo':str(exc)[:120]})
    return {
      'consultadas':len(saida),
      'confirmadas':sum(x['status']=='confirmado' for x in saida),
      'divergentes':sum(x['status']=='divergente' for x in saida),
      'atualizadas':sum(x['status']=='atualizado' for x in saida),
      'inconclusivas':sum(x['status']=='inconclusivo' for x in saida),
      'detalhes':saida,
      'nota':('Somente a amostra foi verificada por HTTPS na CDN oficial. '
              'Não é verificação de assinatura JWS nem autenticação do '
              'snapshot completo.')
    }
