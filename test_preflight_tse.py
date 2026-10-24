"""EA11: confirmar eleição 6258/pleito 3221 antes de consultar zonas."""
import unittest
from preflight_tse import verificar_config


class TestPreflightTSE(unittest.TestCase):
    def setUp(self):
        self.t1={'cd':'6257','cdt2':'6258','t':'1','tp':'8'}
        self.t2={'cd':'6258','t':'2','tp':'8',
                 'abr':[{'cd':'br','cp':[{'cd':'1'}]}]}
        self.base={'dg':'24/10/2026','hg':'12:00',
                   'pl':[{'cd':'3220','c':'ele2026','e':[self.t1]}]}

    def test_pendente_antes_do_segundo_turno_e_valido(self):
        r=verificar_config(self.base)
        self.assertEqual(r['status'],'pleito_3221_nao_publicado')
        self.assertFalse(r['pleito_2turno_confirmado'])

    def test_confirma_apenas_ciclo_cargo_e_turno_corretos(self):
        self.base['pl'].append({'cd':'3221','c':'ele2026','e':[self.t2]})
        r=verificar_config(self.base)
        self.assertTrue(r['pleito_2turno_confirmado'])

    def test_rejeita_outro_cargo_e_erro_de_eleicao(self):
        self.base['pl'].append({'cd':'3221','c':'ele2026','e':[{
            'cd':'6258','t':'1','tp':'8','abr':[{'cp':[{'cd':'1'}]}]}]})
        with self.assertRaisesRegex(ValueError,'não confirma'):
            verificar_config(self.base)

    def test_rejeita_cadastro_malformado(self):
        with self.assertRaisesRegex(ValueError,'lista oficial'):
            verificar_config({'pl':None})


if __name__=='__main__':
    unittest.main()
