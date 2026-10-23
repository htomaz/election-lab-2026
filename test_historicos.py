"""Testes da reconciliação territorial com dados sintéticos."""
import csv
import tempfile
import unittest
from pathlib import Path
from validar_historicos import auditar


def gravar(path, campos, linhas):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas)


class TestHistoricos(unittest.TestCase):
    def test_reconciliacao_e_duplicacao(self):
        with tempfile.TemporaryDirectory() as temp:
            u, z = Path(temp)/'ufs.csv', Path(temp)/'zonas.csv'
            base = dict(uf='SP', ano='2026', turno='1',
                        lula='40', direita='45', validos='100')
            zona = dict(base, municipio='71072', zona='0001')
            gravar(u, list(base), [base])
            gravar(z, list(zona), [zona])
            self.assertEqual(auditar(u,z)['2026T1']['validos'], 100)
            gravar(z, list(zona), [zona, zona])
            with self.assertRaisesRegex(ValueError, 'duplicada'):
                auditar(u,z)

    def test_divergencia_uf_zona(self):
        with tempfile.TemporaryDirectory() as temp:
            u, z = Path(temp)/'ufs.csv', Path(temp)/'zonas.csv'
            base = dict(uf='SP', ano='2022', turno='2',
                        lula='50', direita='50', validos='100')
            gravar(u, list(base), [base])
            zona = dict(base, municipio='71072', zona='0001', validos='101')
            gravar(z, list(zona), [zona])
            with self.assertRaisesRegex(ValueError, 'divergentes'):
                auditar(u,z)


if __name__ == '__main__':
    unittest.main()
