"""Smoke-test executando o Streamlit, não só compilando módulos Python."""
import unittest
import json
import shutil
import tempfile
from pathlib import Path
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

    def test_snapshot_de_uma_uf_nao_e_rotulado_nacional(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            shutil.copyfile('historico_zonas.csv',p/'historico_zonas.csv')
            snap={'versao':1,'eleicao':6258,'catalogo_origem':'EA16_TSE_3221',
                  'catalogo':[{'uf':'SP','municipio':'71072','zona':'0001',
                               'secoes_cadastradas_ea16':100}],
                  'observacoes':{}}
            (p/'dados_zonais_6258.json').write_text(
                json.dumps(snap),encoding='utf-8')
            code=(
                'from pathlib import Path\n'
                'from painel_zonal_completo import exibir_modelo_zonal_completo\n'
                f'exibir_modelo_zonal_completo(Path({str(p)!r}),nomes={{}})\n'
            )
            app=AppTest.from_string(code,default_timeout=90).run()
            self.assertFalse(app.exception,
                             [str(x.message) for x in app.exception])
            avisos=[str(x.proto) for x in app.warning]
            self.assertTrue(
                any('Cadastro EA16 parcial' in t for t in avisos),
                {'avisos':avisos,
                 'erros':[str(x.proto) for x in app.error],
                 'infos':[str(x.proto) for x in app.info]}
            )
            titulos=[str(x.proto) for x in app.markdown]
            self.assertTrue(any('SOMENTE das UFs' in t for t in titulos))



if __name__=='__main__':
    unittest.main()
