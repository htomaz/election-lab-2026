"""Smoke-test executando o Streamlit, não só compilando módulos Python."""
import unittest
from streamlit.testing.v1 import AppTest


class TestPainelZonalSmoke(unittest.TestCase):
    def test_renderiza_preview_sem_apuracao_do_segundo_turno(self):
        code=(
            "from pathlib import Path\n"
            "from painel_zonal_completo import exibir_modelo_zonal_completo\n"
            "exibir_modelo_zonal_completo(Path.cwd(),nomes={})\n"
        )
        app=AppTest.from_string(code,default_timeout=90).run()
        self.assertFalse(app.exception, [str(e.message) for e in app.exception])
        mensagens=[str(x.proto) for x in app.warning]
        # A aba não pode inventar resultado oficial sem EA20.
        self.assertTrue(any('PRÉVIA COM HISTÓRICO' in str(m) for m in mensagens))
        self.assertGreaterEqual(len(app.metric),6)


if __name__=='__main__':
    unittest.main()
