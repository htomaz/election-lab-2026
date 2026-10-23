"""Testes de conciliação EA20 entre recortes de município/zona e UF."""
import unittest

from auditoria_ao_vivo import reconciliar_zonas, validar_substituicao


class TestAuditoriaAoVivo(unittest.TestCase):
    def setUp(self):
        self.a=('SP','71072','0001')
        self.b=('SP','71072','0002')
        self.zonas={
            self.a:{'lula':40,'flavio':60,'validos':100,
                    'secoes':1,'secoes_total':2,'geracao':'25/10/2026 17:05:00'},
            self.b:{'lula':10,'flavio':30,'validos':40,
                    'secoes':1,'secoes_total':1,'geracao':'25/10/2026 17:05:00'}}
        self.uf={'lula':250,'flavio':290,'validos':540,
                 'secoes':9,'secoes_total':30,'geracao':'25/10/2026 17:06:00'}

    def test_amostra_inferior_nao_e_conciliacao_total(self):
        res=reconciliar_zonas(self.zonas,self.uf)
        self.assertEqual(res['status'],'parcial_compativel')
        self.assertEqual(res['diferencas']['validos'],400)

    def test_soma_superior_ao_estado_sincronizado_e_inconsistente(self):
        uf=dict(self.uf,validos=120,lula=35)
        self.assertEqual(reconciliar_zonas(self.zonas,uf)['status'],'inconsistente')

    def test_uf_antiga_nao_gera_falso_erro(self):
        uf=dict(self.uf,validos=120,lula=35,geracao='25/10/2026 17:04:00')
        self.assertEqual(reconciliar_zonas(self.zonas,uf)['status'],'uf_defasada')

    def test_geracao_nao_identificavel(self):
        uf=dict(self.uf,geracao='')
        self.assertEqual(reconciliar_zonas(self.zonas,uf)['status'],'geracao_desconhecida')

    def test_conciliacao_integral_exige_universo_e_secoes(self):
        zonas={self.a:dict(self.zonas[self.a],secoes=2,secoes_total=2),
               self.b:self.zonas[self.b]}
        uf={'lula':50,'flavio':90,'validos':140,'secoes':3,'secoes_total':3,
            'geracao':'25/10/2026 17:06:00'}
        self.assertEqual(reconciliar_zonas(zonas,uf)['status'],'parcial_compativel')
        self.assertEqual(reconciliar_zonas(zonas,uf,universo=set(zonas))['status'],
                         'reconciliado')

    def test_rejeita_regressao_da_apuracao(self):
        atual=dict(self.zonas[self.a],secoes=0,geracao='25/10/2026 17:08:00')
        ok,motivo=validar_substituicao(self.zonas[self.a],atual)
        self.assertFalse(ok)
        self.assertIn('regrediu',motivo)

    def test_rejeita_snapshot_antigo(self):
        atual=dict(self.zonas[self.a],geracao='25/10/2026 17:03:00')
        self.assertFalse(validar_substituicao(self.zonas[self.a],atual)[0])


if __name__=='__main__':
    unittest.main()
