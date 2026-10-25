"""Correção de viés de seleção territorial no modelo agregado por UF.

Caso fechado e controlado; não usa votos futuros nem finge possuir cronologia
de apuração real. Só corrige quando a identidade dos votos já apurados e o
histórico por região foram devidamente reconciliados.
"""
import unittest
from modelo import projetar_locais


UF = 'SP'
HIST = {UF: {(2022, 2): {'lula': 80, 'direita': 120, 'validos': 200}}}
PERFIL = {
    'lula_atual': 60, 'flavio_atual': 40,
    'periodos': {(2022, 2): {
        # Geografia A: 60/40 (já apurada).
        'lula_apurado_hist': 60, 'direita_apurado_hist': 40,
        # Estado inteiro: A 60/40 + B 20/80.
        'lula_total_hist': 80, 'direita_total_hist': 120,
    }}
}
OBS = {UF: {'lula': 60, 'flavio': 40,
            'validos': 100, 'secoes': 1, 'secoes_total': 2}}


def calcula(obs=OBS, perfil=None):
    rel = projetar_locais(
        obs, HIST, peso_2026=0, ajuste_volume=1.,
        intensidade=.35,
        composicao_historica=({UF: perfil} if perfil else None))
    return next(l for l in rel['linhas'] if l['UF'] == UF)


class TestModeloComposicao(unittest.TestCase):
    def test_parcial_geograficamente_seletiva_corrigida(self):
        # Observar só A (60% Lula) NÃO significa que B votará igual à média
        # estadual (40%). Com a identidade territorial, B = 20%.
        atual = calcula()
        corrigido = calcula(perfil=PERFIL)
        self.assertFalse(atual['Perfil geográfico validado'])
        self.assertAlmostEqual(atual['Lula projeção (%)'], 51.4, places=6)
        self.assertTrue(corrigido['Perfil geográfico validado'])
        self.assertAlmostEqual(corrigido['Histórico restante Lula (%)'], 20.)
        self.assertAlmostEqual(corrigido['Lula projeção (%)'], 40., places=6)
        self.assertEqual(corrigido['Lula projetado'], 80.)

    def test_swing_observado_nao_e_reversao_automatica(self):
        # A mostra deslocamento de +10 p.p. vs SEU próprio histórico.
        obs={UF:{'lula':70,'flavio':30,'validos':100,'secoes':1,'secoes_total':2}}
        perfil={**PERFIL, 'lula_atual':70,'flavio_atual':30}
        dado=calcula(obs, perfil)
        # O delta efetivo segue o ganho conservador do modelo:
        # remaining = .20 + .35 * clip(+.10, +/- .08) = .228.
        self.assertAlmostEqual(dado['Lula projeção (%)'], 46.4, places=6)
        self.assertTrue(dado['Perfil geográfico validado'])

    def test_perfil_desatualizado_ou_conteudo_invalido_volta_ao_base(self):
        base=calcula()['Lula projeção (%)']
        alteracoes=[
            {**PERFIL,'lula_atual':61},  # TSE já atualizou, perfil não
            {**PERFIL,'periodos':{}},    # faltam dados por período
            {**PERFIL,'periodos':{(2022,2):{
                **PERFIL['periodos'][(2022,2)],
                'lula_total_hist':79}}}, # histórico difere do UF
        ]
        for p in alteracoes:
            resultado=calcula(perfil=p)
            self.assertFalse(resultado['Perfil geográfico validado'])
            self.assertAlmostEqual(resultado['Lula projeção (%)'], base)

    def test_convergencia_no_final_e_invariancia_sem_perfil(self):
        completo={UF:{'lula':72,'flavio':128,
                      'validos':200,'secoes':2,'secoes_total':2}}
        dado=calcula(completo)
        self.assertAlmostEqual(dado['Lula projeção (%)'],36.)
        self.assertAlmostEqual(dado['Votos válidos projetados'],200.)


if __name__=='__main__':
    unittest.main()
