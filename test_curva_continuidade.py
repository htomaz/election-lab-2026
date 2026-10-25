"""Invariantes do gráfico: observado -> previsão final, sem emendar séries falsas."""
import csv
import math
import unittest
from pathlib import Path

from curva_continuidade import (
    construir_continuacao, inclinacao_recente, limpar_pontos,
)


class TestContinuidadeApuracao(unittest.TestCase):
    def test_juncao_exata_e_meta_exata(self):
        parcial = [
            (12.0, 48.20, "2026-10-25T17:10:00-03:00"),
            (27.0, 48.85, "2026-10-25T17:12:00-03:00"),
            (40.0, 49.20, "2026-10-25T17:14:00-03:00"),
        ]
        caminho = construir_continuacao(parcial, 50.76)
        self.assertEqual(caminho[0], (40.0, 49.20))
        self.assertEqual(caminho[-1], (100., 50.76))
        self.assertTrue(all(x2 > x1 for (x1,_),(x2,_) in zip(caminho,caminho[1:])))
        self.assertTrue(all(0 <= y <= 100 for _,y in caminho))
        self.assertAlmostEqual(100 - caminho[0][1], 50.80, places=8)
        self.assertAlmostEqual(100 - caminho[-1][1], 49.24, places=8)

    def test_inclinacao_na_juncao_reflete_parciais_recentes(self):
        parcial = [
            (30., 47.9, "2026-10-25T17:15:00-03:00"),
            (34., 48.3, "2026-10-25T17:16:00-03:00"),
            (38., 48.7, "2026-10-25T17:17:00-03:00"),
        ]
        slope = inclinacao_recente(parcial)
        self.assertAlmostEqual(slope, .10, places=5)
        trajeto = construir_continuacao(parcial, 50.)
        primeiros = (trajeto[1][1]-trajeto[0][1])/(trajeto[1][0]-trajeto[0][0])
        # A primeira secante já incorpora parte da curvatura entre pontos.
        self.assertAlmostEqual(primeiros, .10, delta=.025)

    def test_tendencia_contraria_retorna_ao_resultado_do_modelo(self):
        # Tendência observada de queda, mas modelo estima recuperação de Lula.
        serie = [(50., 50.6, None), (54., 50.2, None), (58., 49.8, None)]
        trajeto = construir_continuacao(serie, 51.1)
        self.assertEqual(trajeto[0], (58., 49.8))
        self.assertEqual(trajeto[-1], (100., 51.1))
        self.assertLess(trajeto[1][1], 49.8)
        self.assertTrue(all(math.isfinite(y) for _,y in trajeto))

    def test_curvatura_visual_nao_supera_meio_ponto(self):
        serie=[(12., 48.0, None), (16., 48.9, None), (20., 49.8, None)]
        fim=50.3
        trajeto=construir_continuacao(serie,fim)
        x0,y0=trajeto[0]
        for x,y in trajeto:
            linear=y0+(fim-y0)*(x-x0)/(100.-x0)
            self.assertLessEqual(abs(y-linear),.500001)
        self.assertEqual(trajeto[-1],(100.,fim))

    def test_sem_modelo_ou_sem_apuracao_nao_inventa_dados(self):
        self.assertEqual(construir_continuacao([], 50.), [])
        self.assertEqual(construir_continuacao([(25., 47., None)], None), [])
        self.assertEqual(construir_continuacao([(25., 47., None)], float('nan')), [])
        self.assertEqual(construir_continuacao([(100., 52.2, None)], 51.4), [])

    def test_elimina_duplicados_e_regressoes_do_historico(self):
        original = [
            (10., 48., None), (10., 48.2, None),
            (9., 48.1, None), (20., 49.0, None), (20., 49.1, None),
            (float('nan'), 49., None),
        ]
        self.assertEqual(
            limpar_pontos(original),
            [(10., 48.2, None), (20., 49.1, None)]
        )
        self.assertEqual(construir_continuacao(original, 49.9)[0], (20., 49.1))

    def test_referencias_historicas_sao_100_pontos_imutaveis(self):
        arq = Path(__file__).resolve().parent / 'data/curvas_medias_apuracao_2022T2_2026T1.csv'
        with arq.open(encoding='utf-8-sig', newline='') as ar:
            linhas = list(csv.DictReader(ar, delimiter=';'))
        self.assertEqual(len(linhas), 100)
        for i, linha in enumerate(linhas, 1):
            p = int(linha['votos_apurados_pct'])
            l = float(linha['media_lula_pct'].replace(',', '.'))
            f = float(linha['media_flavio_pct'].replace(',', '.'))
            self.assertEqual(p, i)
            self.assertAlmostEqual(l + f, 100., places=4)
        self.assertAlmostEqual(float(linhas[-1]['media_lula_pct'].replace(',', '.')), 49.02)
        self.assertAlmostEqual(float(linhas[-1]['media_flavio_pct'].replace(',', '.')), 50.98)


if __name__ == '__main__':
    unittest.main()
