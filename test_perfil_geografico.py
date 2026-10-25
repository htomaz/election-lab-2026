"""Ajuste por composição só funciona após conciliação exata TSE UF x zonas."""
import unittest
from perfil_geografico import compor_perfis_conciliados
from modelo import projetar_locais


class TestPerfilGeografico(unittest.TestCase):
    def setUp(self):
        a=('SP','71072','0001');b=('SP','71072','0002')
        self.chaves=(a,b)
        self.historico={
            a:{(2022,2):{'lula':60,'direita':40,'validos':100}},
            b:{(2022,2):{'lula':20,'direita':80,'validos':100}},
        }
        # Catálogo completo sintético apenas para validar o esquema e as
        # 6.000 zonas, NÃO corresponde a cadastro real do TSE.
        cat=[{'uf':'SP','municipio':k[1],'zona':k[2]} for k in (a,b)]
        cat.extend({'uf':'SP','municipio':str(90000+i//1000),
                    'zona':str(i%1000).zfill(4)} for i in range(5998))
        self.snapshot={'versao':1,'eleicao':6258,
                       'catalogo_origem':'EA16_TSE_3221','catalogo':cat,
                       'observacoes':{'SP|71072|0001':{
                           'lula':60,'flavio':40,'validos':100,
                           'secoes':10,'secoes_total':10,'fase':'o','turno':2}}}
        self.ufs={'SP':{'lula':60,'flavio':40,'validos':100}}

    def test_proporcao_historica_remanescente_reconciliada(self):
        p=compor_perfis_conciliados(self.ufs,self.snapshot,self.historico)
        self.assertIn('SP',p)
        d=p['SP']['periodos'][(2022,2)]
        self.assertEqual(d['lula_apurado_hist'],60)
        self.assertEqual(d['lula_total_hist'],80)
        self.assertEqual(d['direita_total_hist'],120)
        ufhist={'SP':{(2022,2):{'lula':80,'direita':120,'validos':200}}}
        modelo=projetar_locais({'SP':{'lula':60,'flavio':40,'validos':100,
                                    'secoes':1,'secoes_total':2}},
                              ufhist,peso_2026=0,composicao_historica=p)
        self.assertAlmostEqual(modelo['linhas'][0]['Lula projeção (%)'],40.)

    def test_zona_observada_sem_historico_nao_cria_vies_artificial(self):
        # Uma zona apurada sem correspondente em 2022 não deve ter
        # votos históricos zero por omissão: bloquear a correção.
        del self.historico[self.chaves[0]][(2022,2)]
        self.assertEqual(
            compor_perfis_conciliados(self.ufs,self.snapshot,self.historico),
            {})

    def test_snapshot_zona_parcial_nao_serve_de_geografia_completa(self):
        self.snapshot['observacoes']['SP|71072|0001']['secoes']=5
        self.assertEqual(compor_perfis_conciliados(
            self.ufs,self.snapshot,self.historico),{})

    def test_divergencia_ea20_vs_uf_bloqueia_correcao(self):
        self.ufs['SP']['lula']=61
        self.assertEqual(compor_perfis_conciliados(
            self.ufs,self.snapshot,self.historico),{})

    def test_catalogo_falso_ou_snapshot_primeiro_turno_bloqueados(self):
        self.snapshot['catalogo_origem']='historico_2026T1_PREVIA'
        self.assertEqual(compor_perfis_conciliados(
            self.ufs,self.snapshot,self.historico),{})
        self.snapshot['catalogo_origem']='EA16_TSE_3221'
        self.snapshot['eleicao']=6257
        self.assertEqual(compor_perfis_conciliados(
            self.ufs,self.snapshot,self.historico),{})
        self.snapshot['eleicao']=6258
        self.snapshot['observacoes']['SP|71072|0001']['turno']=1
        self.assertEqual(compor_perfis_conciliados(
            self.ufs,self.snapshot,self.historico),{})


if __name__=='__main__':
    unittest.main()
