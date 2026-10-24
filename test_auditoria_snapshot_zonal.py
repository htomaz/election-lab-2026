"""Teste da conciliação territorial sem chamar rede TSE."""
import unittest

from auditoria_snapshot_zonal import auditar_parciais


class TestAuditoriaSnapshot(unittest.TestCase):
    def setUp(self):
        self.zona={'lula':60,'flavio':40,'validos':100,
                   'secoes':1,'secoes_total':1,
                   'geracao':'25/10/2026 18:00:00'}
        self.snapshot={'catalogo':[{'uf':'SP','municipio':'71072','zona':'0001'}],
                       'observacoes':{'SP|71072|0001':dict(self.zona)}}
        self.uf={'lula':60,'flavio':40,'validos':100,
                 'secoes':1,'secoes_total':1,
                 'geracao':'25/10/2026 18:00:00'}

    def test_zona_igual_uf_reconcilia(self):
        r=auditar_parciais(self.snapshot,{'SP':self.uf})
        self.assertEqual(r['por_uf'][0]['status'],'reconciliado')
        self.assertTrue(r['pode_divulgar_projecao'])
        self.assertEqual(r['nacional']['status'],'cobertura_incompleta')

    def test_zona_supera_uf_e_bloqueia(self):
        self.uf['lula']=40
        self.uf['flavio']=40
        self.uf['validos']=80
        r=auditar_parciais(self.snapshot,{'SP':self.uf})
        self.assertEqual(r['por_uf'][0]['status'],'inconsistente')
        self.assertEqual(r['bloqueantes'],['SP'])

    def test_uf_antiga_nao_e_declarada_inconsistente(self):
        self.uf['geracao']='25/10/2026 17:00:00'
        self.uf['validos']=50
        self.uf['lula']=30
        self.uf['flavio']=20
        r=auditar_parciais(self.snapshot,{'SP':self.uf})
        self.assertEqual(r['por_uf'][0]['status'],'uf_defasada')

    def test_catalogo_nao_aceita_zona_injetada(self):
        self.snapshot['observacoes']['SP|71072|9999']=dict(self.zona)
        with self.assertRaisesRegex(ValueError,'não consta'):
            auditar_parciais(self.snapshot,{'SP':self.uf})


if __name__=='__main__':
    unittest.main()
