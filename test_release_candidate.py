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

    def test_rejeita_branch_main_sem_autorizacao(self):
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/main'}):
            with self.assertRaisesRegex(ValueError,'main'):
                release_candidate.montar()


if __name__=='__main__':
    unittest.main()
