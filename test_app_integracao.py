"""Teste de integração da aplicação Streamlit inteira, sem votos reais.

AppTest executa as três abas, filtros e parâmetros; mocks impedem
qualquer consulta à rede ou alteração persistente de dados oficiais.
O teste de navegador (Playwright) complementa este teste.
"""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class TestAplicativoCompleto(unittest.TestCase):
    def carregar(self):
        with patch('municipios_tse.obter_municipios',return_value={}):
            return AppTest.from_file('app.py', default_timeout=90).run()

    def test_demonstracao_carrega_tres_abas_e_resultados(self):
        app=self.carregar()
        self.assertFalse(app.exception,
                         [str(x.message) for x in app.exception])
        self.assertEqual(len(app.tabs),3)
        self.assertTrue(any('Painel' in x.label for x in app.tabs))
        self.assertTrue(any('Zonas' in x.label for x in app.tabs))
        self.assertTrue(any('Históricos' in x.label for x in app.tabs))
        avisos=[str(x.proto) for x in app.warning]
        self.assertTrue(any('MODO DEMONSTRAÇÃO' in s for s in avisos))
        self.assertGreaterEqual(len(app.metric),6)

    def test_fonte_real_antes_de_apuracao_nao_exibe_votos_ficticios(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with patch('tse.resultado_disponivel',return_value=False), \
             patch('painel_zonal_completo.resultado_disponivel',
                   return_value=False), \
             patch('municipios_tse.obter_municipios',return_value={}):
            app=AppTest.from_file('app.py',default_timeout=90).run()
            self.assertFalse(app.exception,
                             [str(x.message) for x in app.exception])
            fontes=[r for r in app.radio if r.label=='Fonte de dados']
            self.assertEqual(len(fontes),1)
            fontes[0].set_value('TSE oficial · 2º turno')
            app.run()
            self.assertFalse(app.exception,
                             [str(x.message) for x in app.exception])
            avisos=[str(x.proto) for x in app.info]
            self.assertTrue(any('divulgação oficial' in s for s in avisos))
            self.assertFalse(any('Lula · parcial simulada' in str(m.proto)
                                 for m in app.metric))


if __name__=='__main__':
    unittest.main()
