"""A versão auditada deve ser reprodutível e não publicar no GitHub."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import release_candidate


class TestReleaseCandidate(unittest.TestCase):
    def test_manifesto_detecta_arquivo_trocado_apos_testes(self):
        with tempfile.TemporaryDirectory() as pasta:
            file=Path(pasta)/'codigo.py'
            file.write_text('versao-a',encoding='utf-8')
            with patch.object(release_candidate,'ARQUIVOS',(str(file),)), \
                 patch.object(release_candidate,'commit',return_value='abc123'), \
                 patch.dict(os.environ,{'GITHUB_REF':
                    'refs/heads/fix/auditoria-pre-segundo-turno',
                    'GITHUB_SHA':'abc123','GITHUB_HEAD_REF':''}):
                manifesto=release_candidate.montar()
                self.assertTrue(release_candidate.verificar(manifesto))
                self.assertFalse(manifesto['publicado'])
                file.write_text('versao-b',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'Arquivo divergente'):
                    release_candidate.verificar(manifesto)

    def test_manifesto_da_auditoria_25out_tem_branch_correta(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'c.py'
            arquivo.write_text('auditoria',encoding='utf-8')
            with patch.object(release_candidate,'ARQUIVOS',(str(arquivo),)), \
                 patch.object(release_candidate,'commit',return_value='sha-certo'), \
                 patch.dict(os.environ,{
                     'GITHUB_REF':'refs/pull/2/merge',
                     'GITHUB_HEAD_REF':'fix/validacao-conciliacao-25out26',
                     'GITHUB_EVENT_NAME':'pull_request',
                     'ELECTION_LAB_EXPECTED_SHA':'sha-certo'}):
                manifesto=release_candidate.montar()
                self.assertEqual(manifesto['branch'],
                                 'fix/validacao-conciliacao-25out26')
                self.assertTrue(release_candidate.verificar(manifesto))

    def test_manifesto_branch_curvas_e_novos_arquivos_auditados(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'curva_continuidade.py'
            arquivo.write_text('versao-testada',encoding='utf-8')
            with patch.object(release_candidate,'ARQUIVOS',(str(arquivo),)), \
                 patch.object(release_candidate,'commit',return_value='sha-branch'), \
                 patch.dict(os.environ,{
                     'GITHUB_REF':'refs/pull/3/merge',
                     'GITHUB_HEAD_REF':'feature/curvas-medias-fixas-por-votos',
                     'GITHUB_EVENT_NAME':'pull_request',
                     'ELECTION_LAB_EXPECTED_SHA':'sha-branch'}):
                manifesto=release_candidate.montar()
                self.assertEqual(manifesto['branch'],'feature/curvas-medias-fixas-por-votos')
                self.assertTrue(release_candidate.verificar(manifesto))
                self.assertFalse(manifesto['publicado'])

    def test_branch_aleatoria_nao_pode_emitir_manifesto(self):
        with patch.dict(os.environ,{'GITHUB_REF':'refs/pull/2/merge',
                                   'GITHUB_HEAD_REF':'branch-nao-aprovada'}):
            with self.assertRaisesRegex(ValueError,'outra branch'):
                release_candidate.montar()

    def test_rejeita_branch_main_sem_autorizacao(self):
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/main'}):
            with self.assertRaisesRegex(ValueError,'main'):
                release_candidate.montar()


if __name__=='__main__':
    unittest.main()
