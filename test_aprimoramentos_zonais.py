"""Guardrails: backtest turnout, deduplicação, correção e sensibilidade."""
import unittest

from backtest_participacao import compilar_base,estimar,avaliar,resumo
from calibrar_participacao import calibrar,resumo_folds
from modelo_zonas import projetar_zonas
from sensibilidade_zonal import faixa_sensibilidade,projetar_cenario


class TestAprimoramentosZonais(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priors,cls.alvos=compilar_base()

    def test_2022_t2_sem_votos_ocultos_ajuste_zero_igual_baseline(self):
        sel=list(self.alvos)[:70]
        puro,_=estimar(self.priors,self.alvos,sel,modelo='historico')
        zero,_=estimar(self.priors,self.alvos,sel,modelo='ajuste_uf',
                      intensidade=0)
        self.assertAlmostEqual(puro['validos'],zero['validos'])

    def test_apuracao_total_converge_resultado_oficial(self):
        r,_=estimar(self.priors,self.alvos,list(self.priors),
                    modelo='hierarquico',intensidade=.5)
        for c in ('comparecimento','validos','brancos','nulos'):
            esperado=sum(v[c] for v in self.alvos.values())
            self.assertAlmostEqual(r[c],esperado,places=4)

    def test_ausencia_de_votos_observados_reproduz_prior(self):
        a,_=estimar(self.priors,self.alvos,[],modelo='historico')
        b,_=estimar(self.priors,self.alvos,[],modelo='hierarquico')
        self.assertAlmostEqual(a['validos'],b['validos'])

    def test_nao_usa_votos_de_zona_nao_revelada(self):
        keys=list(self.alvos)
        sel=keys[:100]
        a,_=estimar(self.priors,self.alvos,sel,modelo='hierarquico',intensidade=.5)
        chave=keys[-1]
        original=self.alvos[chave]['validos']
        original_comp=self.alvos[chave]['comparecimento']
        original_brancos=self.alvos[chave]['brancos']
        original_nulos=self.alvos[chave]['nulos']
        try:
            # Alterações nos votos OCULTOS não podem mudar previsão.
            self.alvos[chave]['validos']=0
            self.alvos[chave]['comparecimento']=0
            self.alvos[chave]['brancos']=0
            self.alvos[chave]['nulos']=0
            b,_=estimar(self.priors,self.alvos,sel,modelo='hierarquico',intensidade=.5)
            self.assertAlmostEqual(a['validos'],b['validos'])
        finally:
            self.alvos[chave]['validos']=original
            self.alvos[chave]['comparecimento']=original_comp
            self.alvos[chave]['brancos']=original_brancos
            self.alvos[chave]['nulos']=original_nulos

    def test_cenarios_de_estresse_nao_alteram_votos_ja_apurados(self):
        completos=[{'lula_apurado':55,'flavio_apurado':45,'validos_apurados':100,
                    'validos_restantes_estimados':0,'lula_projetado':55.,
                    'flavio_projetado':45.,'participacao':{
                       'aptos_restantes':0,'taxa_validos_estimada_restante':.9,
                       'taxa_comparecimento_estimada_restante':.8}}]
        res=faixa_sensibilidade(completos,8,8)
        self.assertAlmostEqual(res['lula_min_pct'],55)
        self.assertAlmostEqual(res['lula_max_pct'],55)
        self.assertEqual(projetar_cenario(completos,8,8)['validos'],100)

    def test_estresse_sem_dados_participacao_sinaliza_cobertura(self):
        linhas=[{'lula_apurado':15,'flavio_apurado':15,'validos_apurados':30,
                 'validos_restantes_estimados':70,'lula_projetado':50,
                 'flavio_projetado':50,'participacao':None}]
        z=faixa_sensibilidade(linhas,2,3)
        self.assertEqual(z['central']['zonas_sem_dados_participacao'],1)
        self.assertLess(z['lula_min_pct'],z['lula_max_pct'])

    def test_correcao_hierarquica_limita_parcial_com_uma_secao(self):
        k=('SP','71072','0001')
        historico={k:{(2026,1):{'lula':60,'direita':40,'validos':100}}}
        # A parcial 1/100 recebe peso de maturidade pequeno.
        obs={k:{'lula':2,'flavio':0,'validos':2,'secoes':1,'secoes_total':100}}
        z=projetar_zonas(obs,historico,intensidade=1,
                         universo={k})
        self.assertLess(abs(z['swing_estadual']['SP']),.02)
        self.assertIn('diagnostico_representatividade_uf',z)

    def test_holdout_muito_pequeno_sem_erro_de_cobertura(self):
        linhas=calibrar(seeds=range(1),etapas=(10,100),intensidades=(0,.5))
        # 28 UFs x 3 modelos, cada UF testada somente fora do treino.
        self.assertEqual(len(linhas),84)
        self.assertEqual(len(set((r['uf_teste'],r['modelo']) for r in linhas)),84)
        self.assertEqual(len(resumo_folds(linhas)),3)


if __name__=='__main__':
    unittest.main()
