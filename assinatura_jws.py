"""Verificador local de JWS Ed25519 da publicação do TSE.

Só há confiança quando a chave de 32 bytes foi fornecida e conferida
INDEPENDENTEMENTE pelo operador contra o manual oficial TSE (apêndice B).
Jamais usar chaves jwk/x5c fornecidas no próprio JWS como raiz de confiança.

Aceita compact JWS (header.payload.signature) ou formato flattened JSON
(protected,payload,signature). Não aceita alg=none, chaves embutidas,
payload destacado, b64=false ou algoritmos alternativos.

Verifica assinatura do arquivo de PUBLICAÇÃO, não a assinatura de BU,
cadeia X.509, revogação de certificados ou horário de incorporação.
"""
from __future__ import annotations
import base64
import json
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

# Publicado diretamente pelo TSE em 16/09/2026, Apêndice B do
# Manual de verificação dos arquivos JWS, pág. 8/11.
# Esta é uma CHAVE PÚBLICA, não uma credencial nem segredo.
# https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/manual-verificacao-jws
TSE_JWS_PUBLIC_KEY_B64_OFICIAL='kWlpNHjuws1csyQZwzn3Fhzbi3RD435RbpThtSr4hMc'
TSE_JWS_KID_OFICIAL='sNbt9Q_fLS65zE1_ZLNV-XRRwPY'
MAX_JWS=8*1024*1024


def _b64(s):
    if not isinstance(s,str) or not s or not re.fullmatch(r'[A-Za-z0-9_-]+',s):
        raise ValueError('Base64url JWS inválido')
    return base64.urlsafe_b64decode(s+'='*((-len(s))%4))


def _unpack(content):
    if isinstance(content,bytes):
        if len(content)>MAX_JWS:
            raise ValueError('JWS maior que 8 MB')
        content=content.decode('utf-8')
    if not isinstance(content,str) or len(content)>MAX_JWS:
        raise ValueError('JWS inválido/excessivo')
    content=content.strip()
    if content.startswith('{'):
        obj=json.loads(content)
        if not isinstance(obj,dict) or not all(
            isinstance(obj.get(k),str) for k in ('protected','payload','signature')
        ):
            raise ValueError('JWS JSON sem assinatura flattening')
        header,payload,sig=(obj[k] for k in ('protected','payload','signature'))
    else:
        partes=content.split('.')
        if len(partes)!=3:
            raise ValueError('Compact JWS precisa de três componentes')
        header,payload,sig=partes
    header_data=json.loads(_b64(header))
    if not isinstance(header_data,dict) or header_data.get('alg')!='EdDSA':
        raise ValueError('Somente assinatura EdDSA é aceita')
    if header_data.get('b64') is False or header_data.get('crit'):
        raise ValueError('Extensões JWS desconhecidas não são permitidas')
    if any(x in header_data for x in ('jwk','jku','x5u','x5c')):
        raise ValueError('Não confiar em chave/certificado embutido no JWS')
    assinatura=_b64(sig)
    if len(assinatura)!=64:
        raise ValueError('Assinatura Ed25519 deve conter 64 bytes')
    # RFC 7515: protected-base64 + '.' + payload-base64 são os bytes
    # efetivamente assinados. Nunca reconstruir JSON antes de verificar.
    entrada=(header+'.'+payload).encode('ascii')
    return _b64(payload),assinatura,entrada,header_data


def chave_publica_confiavel(b64):
    if not isinstance(b64,str) or not b64.strip():
        raise ValueError('Chave TSE não configurada')
    raw=_b64(b64.strip().rstrip('='))
    if len(raw)!=32:
        raise ValueError('Chave pública Ed25519 deve conter 32 bytes')
    return Ed25519PublicKey.from_public_bytes(raw)


def verificar_jws(conteudo,chave_b64=None):
    # Sem argumento, utiliza exclusivamente a chave do ambiente OFICIAL
    # publicada pelo TSE. Chave de desenvolvimento jamais é aceita no
    # caminho padrão. O parâmetro explícito serve a testes offline.
    if chave_b64 is None:
        chave_b64=TSE_JWS_PUBLIC_KEY_B64_OFICIAL
    chave=chave_publica_confiavel(chave_b64)
    payload,assinatura,entrada,header_data=_unpack(conteudo)
    if chave_b64==TSE_JWS_PUBLIC_KEY_B64_OFICIAL and (
        header_data.get('kid')!=TSE_JWS_KID_OFICIAL
    ):
        raise ValueError('JWS com kid diferente do certificado público OFICIAL do TSE')
    try:
        chave.verify(assinatura,entrada)
    except InvalidSignature as exc:
        raise ValueError('Assinatura Ed25519 inválida') from exc
    try:
        obj=json.loads(payload)
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('Payload assinado não contém JSON válido') from exc
    if not isinstance(obj,dict):
        raise ValueError('Payload JWS não é objeto JSON')
    return obj


def comparar_assinado_zona(jws,chave_b64,uf,municipio,zona,observacao):
    from tse import normalizar_ea20
    assinado=verificar_jws(jws,chave_b64)
    validado=normalizar_ea20(assinado,uf,
                           abrangencia_esperada='zona',
                           exigir_metadados=True)
    if str(assinado.get('cdabr','')).zfill(4)!=str(zona).zfill(4):
        raise ValueError('Zona assinada não coincide com a solicitada')
    for c in ('lula','flavio','validos','secoes','secoes_total','geracao'):
        if str(validado[c])!=str(observacao.get(c)):
            raise ValueError('Assinatura válida, mas dados diferem do snapshot: '+c)
    return {'assinatura_valida':True,'dados_conferidos':True,
            'geracao':validado['geracao'],
            'nota':'JWS da publicação verificado; não autentica boletins de urna'}
