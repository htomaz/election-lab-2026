"""Diagnóstico automático sem consultar o TSE."""
import unittest
from auditar_coleta_programada import avaliar

class TestAuditoriaColetaProgramada(unittest.TestCase):
    def setUp(self):
        self.snap={'versao':1,'eleicao':6258,'catalogo_origem':'EA16_TSE_3221',
                   'catalogo':[{'uf':'SP','municipio':'71072','zona':'0001'}],
                   'observacoes':{'SP|71072|0001':{
                       'lula':60,'flavio':40,'validos':100,
                       'secoes':1,'secoes_total':2,
                       'geracao':'25/10/2026 18:00:00'}}}
        self.uf={'SP':{'lula':100,'flavio':90,'validos':190,
                       'secoes':2,'secoes_total':4,
                       'geracao':'25/10/2026 18:10:00'}}

    def test_ausencia_de_brasil_nao_e_aprovada(self):
        r=avaliar(self.snap,self.uf)
        self.assertEqual(r['status'],'inconclusivo')
        self.assertIn('BR',r['faltantes'])

    def test_amostra_impossivel_e_bloqueada(self):
        uf={'SP':{**self.uf['SP'],'lula':40,'validos':80}}
        r=avaliar(self.snap,uf)
        self.assertEqual(r['status'],'divergente')
        self.assertIn('SP',r['auditoria']['bloqueantes'])

    def test_zona_mais_recente_nao_e_falso_erro(self):
        uf={'SP':{**self.uf['SP'],
                  'geracao':'25/10/2026 17:50:00'}}
        r=avaliar(self.snap,uf)
        self.assertEqual(r['status'],'inconclusivo')
        self.assertEqual(r['auditoria']['por_uf'][0]['status'],
                         'uf_defasada')

if __name__=='__main__':
    unittest.main()
