"""Recuperação persistente dos snapshots zonais via GitHub Actions artifacts.

Diferente do cache, cada run de coleta disponibiliza um artifact retido por
30 dias. O arquivo inclui SHA-256 do JSON para detectar corrupção no
transporte; NÃO substitui a autenticação de votos pelo TSE.

Somente lê backups produzidos pelo próprio workflow numa branch aprovada.
Não usa PAT embutido: GITHUB_TOKEN dos Actions ou um segredo explicitamente
provisionado. Restaurar por merge, jamais apagar/parcial antiga sobre nova.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
import requests

from auditoria_ao_vivo import validar_substituicao
from motor_zonal_completo import chave_zona
from serie_nacional_actions import incorporar

REPO='htomaz/election-lab-2026'
BRANCH='fix/auditoria-pre-segundo-turno'


def branch_do_backup(branch=None):
    """Mantém ambientes de teste e produção separados por origem."""
    valor=(branch or os.environ.get('ELECTION_LAB_SNAPSHOT_BRANCH')
           or os.environ.get('GITHUB_REF_NAME') or BRANCH)
    if valor not in ('main','fix/auditoria-pre-segundo-turno'):
        raise ValueError('Branch de backup não autorizada')
    return valor


NOME='snapshot-zonal-6258'
NOME_JSON='dados_zonais_6258.json'
MAX_BYTES=30*1024*1024


def validar_snapshot(dados):
    if not isinstance(dados,dict) or dados.get('versao')!=1 or (
        dados.get('eleicao')!=6258
    ):
        raise ValueError('Backup de eleição/formato diferente')
    if not isinstance(dados.get('catalogo'),list) or not isinstance(
        dados.get('observacoes'),dict
    ):
        raise ValueError('Backup sem catálogo/observações')
    if dados.get('catalogo_origem')!='EA16_TSE_3221':
        raise ValueError('Backup sem indicação da fonte EA16 oficial')
    chaves=set()
    for item in dados['catalogo']:
        k=chave_zona(item['uf'],item['municipio'],item['zona'])
        if k in chaves:
            raise ValueError('Backup com zona duplicada')
        chaves.add(k)
    for key in dados['observacoes']:
        if not isinstance(key,str) or chave_zona(*key.split('|')) not in chaves:
            raise ValueError('Backup com observação fora do catálogo')
    incorporar(dados.get('historico_br',[]),[])
    return True


def extrair_artifact(blob):
    if not isinstance(blob,bytes) or len(blob)>MAX_BYTES:
        raise ValueError('ZIP do artifact acima de 30 MB')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        nomes=set(z.namelist())
        if NOME_JSON not in nomes or 'snapshot.sha256' not in nomes:
            raise ValueError('Backup sem JSON e SHA-256 obrigatório')
        if z.getinfo(NOME_JSON).file_size>MAX_BYTES or (
            z.getinfo('snapshot.sha256').file_size>128
        ):
            raise ValueError('Backup ZIP excede limites de extração')
        with z.open(NOME_JSON) as fonte:
            bruto=fonte.read(MAX_BYTES+1)
        if len(bruto)>MAX_BYTES:
            raise ValueError('JSON grande demais')
        original=z.read('snapshot.sha256').decode('ascii').strip()
        if not re.fullmatch(r'[a-f0-9]{64}',original):
            raise ValueError('Manifesto SHA-256 inválido')
        obtido=hashlib.sha256(bruto).hexdigest()
        if original!=obtido:
            raise ValueError('SHA-256 do arquivo do backup não confere')
        dados=json.loads(bruto.decode('utf-8'))
        validar_snapshot(dados)
        return dados


def mesclar(local,remoto):
    """Retém catálogo e parciais locais mesmo após restauração de backup."""
    validar_snapshot(remoto)
    if local is None:
        return remoto
    validar_snapshot(local)
    base={tuple((x['uf'],x['municipio'],x['zona'])):x
          for x in remoto['catalogo']}
    for x in local['catalogo']:
        k=tuple((x['uf'],x['municipio'],x['zona']))
        base[k]=x if k in base else x
    combinado={**remoto}
    combinado['catalogo']=list(base.values())
    combinado['historico_br']=incorporar(
        remoto.get('historico_br',[]),local.get('historico_br',[]))
    combinado['observacoes']=dict(remoto['observacoes'])
    for chave,v in local['observacoes'].items():
        antigo=combinado['observacoes'].get(chave)
        if antigo is None:
            combinado['observacoes'][chave]=v
        else:
            ok,_=validar_substituicao(antigo,v)
            if ok:
                combinado['observacoes'][chave]=v
    validar_snapshot(combinado)
    return combinado


def listar_artifacts(sess,token,repo=REPO):
    url=f'https://api.github.com/repos/{repo}/actions/artifacts'
    r=sess.get(url,headers={'Authorization':f'Bearer {token}',
                            'Accept':'application/vnd.github+json'},
               params={'name':NOME,'per_page':100},timeout=(6,25))
    r.raise_for_status()
    return r.json()['artifacts']


def baixar_mais_recente(sess,token,repo=REPO,branch=BRANCH,
                        ignorar_run=None):
    if not token:
        raise ValueError('É necessário token GitHub com acesso de leitura a Actions')
    arts=listar_artifacts(sess,token,repo=repo)
    possiveis=sorted((
        a for a in arts if a.get('name')==NOME and not a.get('expired')
        and a.get('workflow_run',{}).get('head_branch')==branch
        and a.get('workflow_run',{}).get('id')!=ignorar_run
    ),key=lambda x:x.get('id',0),reverse=True)
    if not possiveis:
        return None
    # Artifacts antigos anteriores à implantação do manifesto não são
    # restauráveis; procurar a cópia válida mais recente, sem descartá-la.
    for art in possiveis[:20]:
        ident=int(art['id'])
        url=f'https://api.github.com/repos/{repo}/actions/artifacts/{ident}/zip'
        r=sess.get(url,headers={'Authorization':f'Bearer {token}',
                                'Accept':'application/vnd.github+json'},
                   timeout=(6,40))
        r.raise_for_status()
        try:
            resultado=extrair_artifact(r.content)
        except (ValueError,zipfile.BadZipFile,UnicodeError,KeyError):
            continue
        return {'artifact_id':ident,'run_id':art['workflow_run']['id'],
                'snapshot':resultado}
    return None


def baixar_historico_validado(sess,token,repo=REPO,branch=None,
                              ignorar_run=None,max_artifacts=12):
    """Devolve backups válidos do mais antigo para o mais novo.

    Um artifact recente pode ter menos zonas caso uma execução tenha
    perdido o cache. A união conservadora recupera também observações
    mais antigas, sem regressão das gerações oficiais.
    """
    destino_branch=branch_do_backup(branch)
    arts=listar_artifacts(sess,token,repo=repo)
    elegiveis=sorted(
        (a for a in arts if a.get('name')==NOME and not a.get('expired')
         and a.get('workflow_run',{}).get('head_branch')==destino_branch
         and a.get('workflow_run',{}).get('id')!=ignorar_run),
        key=lambda a:int(a.get('id',0)),reverse=True)
    snapshots=[]
    for art in elegiveis[:max_artifacts]:
        resposta=sess.get(
            f"https://api.github.com/repos/{repo}/actions/artifacts/{int(art['id'])}/zip",
            headers={'Authorization':f'Bearer {token}',
                     'Accept':'application/vnd.github+json'},
            timeout=(6,40))
        resposta.raise_for_status()
        try:
            dados=extrair_artifact(resposta.content)
        except (ValueError,zipfile.BadZipFile,UnicodeError,KeyError):
            continue
        snapshots.append((int(art['id']),dados))
    return list(reversed(snapshots))


def recuperar(destino,token=None,sess=None,ignorar_run=None,branch=None):
    from coletor_zonal import carregar_arquivo,salvar_atomico,_arquivo_bloqueado
    token=token or os.environ.get('GITHUB_SNAPSHOT_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError('Não há token de leitura de artifacts configurado')
    sess=sess or requests.Session()
    historico=baixar_historico_validado(
        sess,token,branch=branch,ignorar_run=ignorar_run)
    if not historico:
        return {'restaurado':False,'motivo':'Nenhum artifact válido encontrado'}
    path=Path(destino)
    with _arquivo_bloqueado(path):
        original=carregar_arquivo(path) if path.exists() else None
        atualizado=original
        # Mesclar em ordem cronológica: nenhuma parcial mais antiga
        # pode apagar votos de uma geração mais recente.
        for _,snapshot in historico:
            atualizado=mesclar(atualizado,snapshot)
        salvar_atomico(path,atualizado)
    return {'restaurado':True,'artifact_id':historico[-1][0],
            'artifacts_mesclados':len(historico),
            'branch':branch_do_backup(branch),
            'zonas_com_votos':len(atualizado['observacoes']),
            'zonas_catalogadas':len(atualizado['catalogo'])}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--destino',default=NOME_JSON)
    p.add_argument('--ignorar-run',type=int)
    a=p.parse_args()
    print(json.dumps(recuperar(a.destino,ignorar_run=a.ignorar_run),
                     indent=2,ensure_ascii=False))
