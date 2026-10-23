"""Invariantes do modelo territorial; sem dependência de rede."""
import csv
import tempfile
import unittest
from pathlib import Path
from modelo_zonas import carregar_zonas, projetar_zonas


class TestZonas(unittest.TestCase):
    def setUp(self):
        self.a=('SP','71072','0001')
        self.b=('SP','71072','0002')
        self.refs={
            self.a:{(2022,2):{'lula':60,'direita':40,'validos':100},
                    (2026,1):{'lula':70,'direita':30,'validos':100}},
            self.b:{(2022,2):{'lula':20,'direita':80,'validos':100},
                    (2026,1):{'lula':25,'direita':75,'validos':100}}
        }

    def test_uma_zona_apurada_outra_continua_projetada(self):
        obs={self.a:{'lula':55,'flavio':45,'validos':100,
                     'secoes':10,'secoes_total':10}}
        x=projetar_zonas(obs,self.refs,universo={self.a,self.b},intensidade=0)
        self.assertAlmostEqual(x['lula'],55+(.75*25+.25*20))
        self.assertAlmostEqual(x['flavio'],45+(100-(.75*25+.25*20)))
        self.assertEqual(x['por_uf']['SP']['zonas_observadas'],1)

    def test_cem_por_cento_converge_observado(self):
        obs={self.a:{'lula':55,'flavio':45,'validos':100,'secoes':1,'secoes_total':1},
             self.b:{'lula':35,'flavio':65,'validos':100,'secoes':1,'secoes_total':1}}
        for i in (0,.35,.8):
            x=projetar_zonas(obs,self.refs,universo=set(obs),intensidade=i)
            self.assertAlmostEqual(x['lula'],90)
            self.assertAlmostEqual(x['flavio'],110)

    def test_universo_exclui_zona_extinta(self):
        obs={self.a:{'lula':55,'flavio':45,'validos':100,'secoes':1,'secoes_total':1}}
        x=projetar_zonas(obs,self.refs,universo={self.a})
        self.assertAlmostEqual(x['lula'],55)
        self.assertAlmostEqual(x['flavio'],45)

    def test_rejeita_parcial_invalida(self):
        obs={self.a:{'lula':90,'flavio':50,'validos':100,'secoes':1,'secoes_total':2}}
        with self.assertRaisesRegex(ValueError,'inconsistente'):
            projetar_zonas(obs,self.refs)

    def test_carregar_historico_zonas(self):
        with tempfile.TemporaryDirectory() as pasta:
            path=Path(pasta)/'zonas.csv'
            with path.open('w',newline='',encoding='utf-8') as arq:
                w=csv.writer(arq)
                w.writerow(['uf','municipio','zona','ano','turno','lula','direita','validos'])
                w.writerow(['SP','71072','0001',2026,1,70,30,100])
            dados=carregar_zonas(path)
            self.assertEqual(dados[self.a][(2026,1)]['validos'],100)


if __name__=='__main__':
    unittest.main()
