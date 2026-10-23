"""Testes básicos de invariantes da projeção e da leitura do TSE."""
import unittest
from modelo import projetar_locais
from tse import UFS, normalizar_ea20


class TestInvariantes(unittest.TestCase):
    def test_uf_completa_nao_projeta_votos_adicionais(self):
        hist = {uf: {(2026, 1): {'lula': 60, 'direita': 40, 'validos': 100}} for uf in UFS}
        dados = {uf: {'lula': 45, 'flavio': 55, 'validos': 100,
                      'secoes': 10, 'secoes_total': 10} for uf in UFS}
        resultado = projetar_locais(dados, hist)
        self.assertTrue(resultado['completo'])
        self.assertAlmostEqual(resultado['lula'], 45 * len(UFS))
        self.assertAlmostEqual(resultado['flavio'], 55 * len(UFS))

    def test_rejeita_votos_validos_sem_candidatos(self):
        payload = {'carg': [], 'v': {'tvn': '100'},
                   's': {'st': '1', 'ts': '10'}}
        with self.assertRaises(ValueError):
            normalizar_ea20(payload, 'SP')


if __name__ == '__main__':
    unittest.main()
