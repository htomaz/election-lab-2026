"""Testes básicos de invariantes da projeção e da leitura do TSE."""
import unittest
from modelo import projetar_locais
from tse import UFS, normalizar_ea20, url_resultado_zona


class TestInvariantes(unittest.TestCase):
    def test_uf_completa_nao_projeta_votos_adicionais(self):
        hist = {uf: {(2026, 1): {'lula': 60, 'direita': 40, 'validos': 100}} for uf in UFS}
        dados = {uf: {'lula': 45, 'flavio': 55, 'validos': 100,
                      'secoes': 10, 'secoes_total': 10} for uf in UFS}
        resultado = projetar_locais(dados, hist)
        self.assertTrue(resultado['completo'])
        self.assertAlmostEqual(resultado['lula'], 45 * len(UFS))
        self.assertAlmostEqual(resultado['flavio'], 55 * len(UFS))

    def test_schema_real_tse_votos_validos_nao_sao_nulos(self):
        p = {'carg':[{'agr':[{'par':[{'cand':[
            {'n':'13','vap':'60'},{'n':'22','vap':'40'}]}]}]}],
            'v':{'vv':'100','tvn':'17'},'s':{'st':'2','ts':'10'}}
        r = normalizar_ea20(p, 'SP')
        self.assertEqual(r['validos'], 100)
        self.assertEqual(r['lula'], 60)
        self.assertEqual(r['flavio'], 40)

    def test_url_zona_padronizada(self):
        self.assertIn('sp71072-z0001-c0001-e006258-u.json',
                      url_resultado_zona('SP','71072','1'))

    def test_rejeita_votos_validos_sem_candidatos(self):
        payload = {'carg': [], 'v': {'vv': '100', 'tvn': '10'},
                   's': {'st': '1', 'ts': '10'}}
        with self.assertRaises(ValueError):
            normalizar_ea20(payload, 'SP')


if __name__ == '__main__':
    unittest.main()
