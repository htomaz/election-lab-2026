"""Regressão: primeiro turno 6257/T1 não pode ser lido como 6258/T2."""
import unittest
from unittest.mock import patch

from tse import normalizar_ea20
from teste_integracao_tse import validar, ZONA, _esperado


def arquivo_primeiro_turno():
    return {'ele':'6257','t':'1','f':'o','tpabr':'zona',
            'cdabr':'0001','dg':'04/10/2026','hg':'21:01:01',
            's':{'st':10,'ts':10},
            'v':{'vv':120,'vb':3,'tvn':2,'tv':125},
            'carg':[{'cd':'1','agr':[{'par':[{'cand':[
                {'n':'13','vap':50},{'n':'22','vap':60},
                {'n':'30','vap':10}
            ]}]}]}]}


class TestParserHistorico2026(unittest.TestCase):
    def test_primeiro_turno_so_quando_explicitamente_selecionado(self):
        p=arquivo_primeiro_turno()
        with self.assertRaisesRegex(ValueError,'eleição diferente'):
            normalizar_ea20(p,'SP',exigir_metadados=True)
        r=normalizar_ea20(
            p,'SP',eleicao_esperada=6257,turno_esperado=1,
            abrangencia_esperada='zona',exigir_metadados=True)
        self.assertEqual((r['lula'],r['flavio'],r['outros']),(50,60,10))

    def test_identidade_cruzada_continua_bloqueada(self):
        p=arquivo_primeiro_turno()
        with self.assertRaisesRegex(ValueError,'não permitida'):
            normalizar_ea20(p,'SP',eleicao_esperada=6258,turno_esperado=1)
        with self.assertRaisesRegex(ValueError,'eleição diferente'):
            normalizar_ea20(p,'SP',eleicao_esperada=6258,turno_esperado=2)

    def test_integracao_historica_compara_candidatos_e_validos(self):
        p=arquivo_primeiro_turno()
        with patch('teste_integracao_tse._obter',return_value=p),\
             patch('teste_integracao_tse._esperado',return_value={
                 'lula':50,'direita':60,'validos':120}):
            x=validar(1)
        self.assertEqual(x['status'],'confere')
        self.assertEqual(x['secoes'],10)

    def test_integracao_rejeita_historico_incorreto(self):
        p=arquivo_primeiro_turno()
        with patch('teste_integracao_tse._obter',return_value=p),\
             patch('teste_integracao_tse._esperado',return_value={
                 'lula':50,'direita':59,'validos':120}):
            with self.assertRaisesRegex(ValueError,'não confere'):
                validar(1)


if __name__=='__main__':
    unittest.main()
