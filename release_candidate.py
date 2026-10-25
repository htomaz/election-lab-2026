"""Manifesto imutável de versão candidata, SEM fazer deploy.

Vincula código, base histórica, dependências e commit do GitHub.
Uma versão só é elegível para avaliação quando unidade + E2E passaram;
a publicação continua sob autorização humana explícita.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BRANCH='fix/auditoria-pre-segundo-turno'
ARQUIVOS=(
    'app.py','tse.py','modelo.py','modelo_zonas.py',
    'modelo_participacao.py','motor_zonal_completo.py',
    'painel_zonal_completo.py','coletor_zonal.py','registro.py',
    'proveniencia_tse.py','assinatura_jws.py','backup_actions.py',
    'auditar_coleta_programada.py','serie_nacional_actions.py',
    '.github/workflows/coleta_zonal.yml','.github/workflows/validacao.yml',
    'preflight_tse.py','auditoria_snapshot_zonal.py',
    'release_candidate.py','visual_e2e.py','requirements.txt',
    'historico_zonas.csv','historico_ufs.csv',
    'historico_participacao_zonas.csv',
)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def commit():
    return subprocess.check_output(
        ['git','rev-parse','HEAD'],text=True).strip()


def montar():
    if os.getenv('GITHUB_REF')=='refs/heads/main':
        raise ValueError('Gate bloqueado na main: candidatas são preparadas na branch de auditoria')
    if os.getenv('GITHUB_HEAD_REF') not in ('',None,BRANCH):
        raise ValueError('Pull request pertence a outra branch')
    files={}
    for item in ARQUIVOS:
        if not Path(item).is_file():
            raise ValueError('Arquivo obrigatório ausente: '+item)
        files[item]=sha(item)
    h=commit()
    # No evento pull_request, GITHUB_SHA aponta para merge sintético,
    # diferente do HEAD real da branch auditada. Comparar o SHA head
    # autorizado pelo evento/checkout para garantir a MESMA versão testada.
    esperado=os.getenv('ELECTION_LAB_EXPECTED_SHA') or (
        os.getenv('GITHUB_SHA') if os.getenv('GITHUB_EVENT_NAME')!='pull_request'
        else None
    )
    if esperado and esperado!=h:
        raise ValueError('Commit do checkout difere da versão auditada no workflow')
    return {'projeto':'Election Lab 2026',
            'tipo':'release_candidate_nao_publicada',
            'branch':BRANCH,'commit':h,
            'gerado_em_utc':datetime.now(timezone.utc).isoformat(),
            'python':sys.version.split()[0],
            'arquivos_sha256':files,
            'validacao':'Necessário CI e teste de navegador verdes; homologação humana pendente',
            'publicado':False}


def verificar(manifesto):
    if manifesto.get('branch')!=BRANCH or manifesto.get('publicado') is not False:
        raise ValueError('Manifesto com branch ou status inesperado')
    if manifesto.get('commit')!=commit():
        raise ValueError('Commit diferente do manifesto aprovado')
    for nome,esperado in manifesto['arquivos_sha256'].items():
        if sha(nome)!=esperado:
            raise ValueError('Arquivo divergente: '+nome)
    return True


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--arquivo',default='release-candidate.json')
    p.add_argument('--verificar',action='store_true')
    args=p.parse_args()
    if args.verificar:
        data=json.loads(Path(args.arquivo).read_text(encoding='utf-8'))
        verificar(data)
        print('Manifesto SHA-256 e commit íntegros:',data['commit'])
    else:
        data=montar()
        Path(args.arquivo).write_text(json.dumps(
            data,indent=2,ensure_ascii=False),encoding='utf-8')
        print('Release candidate preparada SEM DEPLOY:',data['commit'])


if __name__=='__main__':
    main()
