"""Fixture reduzida do EA20 de SP, 1º turno presidencial de 2026.

Valores extraídos de arquivo SP publicado em 04/10/2026 18:19:59,
espelho público tonylampada/apuracao-2026:
data/20261004-182314/presidente-sp.json.
Números são REAIS DO PRIMEIRO TURNO, não dados do segundo turno.
"""
import unittest
from tse import normalizar_ea20


class TestEA20Publicado(unittest.TestCase):
    def test_votos_validos_e_nulos_reais(self):
        votos={
            '22':1569040,'55':61502,'13':929766,'27':965,
            '21':659,'16':1479,'70':93426,'30':9035,
            '80':3788,'35':521,'14':79336,'29':427}
        payload={
            'dg':'04/10/2026','hg':'18:19:59',
            's':{'st':'12021','ts':'103656'},
            'v':{'vv':'2749944','tvn':'93775'},
            'carg':[{'cd':'1','agr':[{'par':[{
                'cand':[{'n':n,'vap':str(q)} for n,q in votos.items()]
            }]}]}]
        }
        self.assertEqual(sum(votos.values()),2749944)
        normal=normalizar_ea20(payload,'SP')
        self.assertEqual(normal['validos'],2749944)
        self.assertEqual(normal['lula'],929766)
        self.assertEqual(normal['flavio'],1569040)
        self.assertEqual(normal['secoes'],12021)
        self.assertEqual(normal['outros'],251138)
        self.assertEqual(normal['geracao'],'04/10/2026 18:19:59')

    def test_divergencia_real_e_rejeitada(self):
        payload={'dg':'04/10/2026','hg':'18:19:59',
                 's':{'st':'1','ts':'2'},'v':{'vv':'100','tvn':'20'},
                 'carg':[{'cd':'1','agr':[{'par':[{'cand':[
                     {'n':'13','vap':'45'},{'n':'22','vap':'43'}]}]}]}]}
        with self.assertRaisesRegex(ValueError,'divergência'):
            normalizar_ea20(payload,'SP')


if __name__=='__main__':
    unittest.main()
