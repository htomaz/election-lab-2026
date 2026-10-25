"""Backup remoto: valida SHA256, escopo/branch e retomada não regressiva."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
from backup_actions import (extrair_artifact,mesclar,baixar_mais_recente,
                            recuperar,branch_do_backup)


def snapshot(secoes=1):
    return {'versao':1,'eleicao':6258,'catalogo_origem':'EA16_TSE_3221',
            'catalogo':[{'uf':'SP','municipio':'71072','zona':'0001'}],
            'observacoes':{'SP|71072|0001':{
               'geracao':f'25/10/2026 18:{secoes:02d}:00',
               'lula':60,'flavio':40,'validos':100,
               'secoes':secoes,'secoes_total':5,
               'capturado_em':1800000000.}}}


def artefato(dados,corromper=False):
    bruto=json.dumps(dados,ensure_ascii=False).encode()
    resumo=hashlib.sha256(bruto).hexdigest()
    if corromper:resumo='0'*64
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w') as z:
        z.writestr('dados_zonais_6258.json',bruto)
        z.writestr('snapshot.sha256',resumo+'\n')
    return mem.getvalue()


class Response:
    def __init__(self,value):self.value=value
    def raise_for_status(self):pass
    def json(self):return self.value
    @property
    def content(self):return self.value


class Sessao:
    def __init__(self,results):self.results=list(results);self.urls=[]
    def get(self,url,**kwargs):
        self.urls.append(url)
        return Response(self.results.pop(0))


class TestBackupActions(unittest.TestCase):
    def test_manifesto_sha_detecta_corrupcao(self):
        self.assertEqual(extrair_artifact(artefato(snapshot()))['eleicao'],6258)
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            extrair_artifact(artefato(snapshot(),corromper=True))

    def test_merge_nao_regrede_geracao(self):
        novo=snapshot(4)
        antigo=snapshot(2)
        self.assertEqual(mesclar(novo,antigo)['observacoes']['SP|71072|0001']['secoes'],4)
        self.assertEqual(mesclar(antigo,novo)['observacoes']['SP|71072|0001']['secoes'],4)

    def test_escolhe_artifact_validado_na_branch_correta(self):
        arts=[
            {'id':110,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'main','id':99}},
            {'id':100,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':20}},
            {'id':90,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':19}}
        ]
        sess=Sessao([{'artifacts':arts},artefato(snapshot(),True),
                     artefato(snapshot())])
        r=baixar_mais_recente(sess,'fake-token')
        self.assertEqual(r['artifact_id'],90)
        self.assertEqual(len(sess.urls),3)

    def test_recupera_uniao_de_artifacts_parciais_sem_regressao(self):
        antigo=snapshot(1)
        mais_novo=snapshot(3)
        # O backup recente perdeu uma segunda zona, mas o antigo não.
        segunda={'uf':'RJ','municipio':'60011','zona':'0001'}
        antigo['catalogo'].append(segunda)
        antigo['observacoes']['RJ|60011|0001']={
            'geracao':'25/10/2026 18:00:00',
            'lula':55,'flavio':45,'validos':100,
            'secoes':1,'secoes_total':5,'capturado_em':1800000000.}
        arts=[
            {'id':22,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':22}},
            {'id':21,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':21}},
            {'id':20,'name':'snapshot-zonal-6258','expired':False,
             'workflow_run':{'head_branch':'main','id':20}}]
        sess=Sessao([{'artifacts':arts},artefato(mais_novo),artefato(antigo)])
        with tempfile.TemporaryDirectory() as pasta:
            p=Path(pasta)/'snapshot.json'
            res=recuperar(p,token='fake',sess=sess,
                         branch='fix/auditoria-pre-segundo-turno')
            dados=json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(res['artifacts_mesclados'],2)
        self.assertEqual(res['zonas_com_votos'],2)
        self.assertEqual(dados['observacoes']['SP|71072|0001']['secoes'],3)
        self.assertEqual(dados['observacoes']['RJ|60011|0001']['secoes'],1)
        self.assertEqual(len(sess.urls),3)

    def test_backup_branch_autorizada(self):
        # Branch explicitamente selecionada é determinística e segura.
        with patch.dict('os.environ',{
            'ELECTION_LAB_SNAPSHOT_BRANCH':'main',
            'GITHUB_REF_NAME':'99/merge'},clear=True):
            self.assertEqual(branch_do_backup(),'main')
        # GITHUB_REF_NAME de PR não deve redirecionar backups.
        with patch.dict('os.environ',{'GITHUB_REF_NAME':'99/merge'},
                        clear=True):
            self.assertEqual(branch_do_backup(),'main')
        # O workflow usa a branch padrão sem depender de Secrets privados.
        with patch.dict('os.environ',{'GITHUB_REF_NAME':'main'},
                        clear=True):
            self.assertEqual(branch_do_backup(),'main')
        with patch.dict('os.environ',{'ELECTION_LAB_SNAPSHOT_BRANCH':
                                     'fix/auditoria-pre-segundo-turno'},
                        clear=True):
            self.assertEqual(branch_do_backup(),
                             'fix/auditoria-pre-segundo-turno')
        with self.assertRaisesRegex(ValueError,'não autorizada'):
            branch_do_backup('outra-branch')

    def test_backup_sem_catalogo_valido_nao_e_aceito(self):
        a=snapshot()
        a['catalogo']=[]
        with self.assertRaisesRegex(ValueError,'catálogo'):
            extrair_artifact(artefato(a))


if __name__=='__main__':
    unittest.main()
