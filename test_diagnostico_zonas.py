"""Testes do diagnóstico histórico territorial."""
import csv
import tempfile
import unittest
from pathlib import Path
from diagnostico_zonas import diagnosticar_zonas


class TestDiagnostico(unittest.TestCase):
    def test_dispersao_ponderada(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'zonas.csv'
            with p.open('w', newline='', encoding='utf-8') as f:
                w=csv.writer(f)
                w.writerow(['uf','municipio','zona','ano','turno','lula','direita','validos'])
                w.writerow(['SP','00001','0001',2022,2,80,20,100])
                w.writerow(['SP','00001','0002',2022,2,20,80,100])
            result=diagnosticar_zonas(p)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['zonas'],2)
            self.assertEqual(result[0]['municipios'],1)
            self.assertAlmostEqual(result[0]['participacao_lula_duelo'],.5)
            self.assertAlmostEqual(result[0]['desvio_padrao_zonas_pp'],30)


if __name__ == '__main__':
    unittest.main()
