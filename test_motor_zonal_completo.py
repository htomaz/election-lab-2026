"""Motor zonal: apurado permanece fixo; restante calculado; agregações fecham."""
import unittest

from motor_zonal_completo import executar, id_zona, chave_zona


class TestMotorCompleto(unittest.TestCase):
    def setUp(self):
        self.z1=('SP','71072','0001')
        self.z2=('SP','71072','0002')
        self.historico={
            self.z1:{(2022,2):{'lula':60,'direita':40,'validos':100},
                     (2026,1):{'lula':70,'direita':30,'validos':100}},
            self.z2:{(2022,2):{'lula':20,'direita':80,'validos':100},
                     (2026,1):{'lula':30,'direita':70,'validos':100}}
        }
        self.now=1_800_000_000.
        self.snapshot={'versao':1,'eleicao':6258,
                       'catalogo_origem':'TESTE_NAO_OFICIAL',
                       'catalogo':[{'uf':z[0],'municipio':z[1],'zona':z[2]}
                                   for z in (self.z1,self.z2)],
                       'observacoes':{}}
        self.nomes={('SP','71072'):'SÃO PAULO'}

    def teste(self,**kwargs):
        return executar(self.snapshot,self.historico,nomes=self.nomes,
                        agora=self.now,exigir_catalogo_nacional=False,**kwargs)

    def test_sem_observacoes_mantem_todas_as_zonas(self):
        r=self.teste()
        self.assertEqual(len(r['linhas']),2)
        self.assertEqual(r['brasil']['zonas_consultadas'],0)
        self.assertTrue(all(v['status']=='não consultada' for v in r['linhas']))
        self.assertEqual(r['brasil']['lula_apurado'],0)
        self.assertEqual(r['linhas'][0]['nome_municipio'],'SÃO PAULO')

    def test_apurado_soma_uma_vez_e_pendente_e_estimado(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':35,'validos':100,
            'secoes':2,'secoes_total':2,'capturado_em':self.now
        }
        r=self.teste()
        por_zona={linha['zona']:linha for linha in r['linhas']}
        self.assertAlmostEqual(por_zona['0001']['lula_projetado'],65)
        self.assertAlmostEqual(por_zona['0001']['flavio_projetado'],35)
        self.assertEqual(por_zona['0001']['status'],'concluída')
        self.assertEqual(por_zona['0002']['status'],'não consultada')
        self.assertEqual(r['brasil']['lula_apurado'],65)
        self.assertEqual(r['brasil']['flavio_apurado'],35)
        self.assertAlmostEqual(
            sum(uf['lula_estimado'] for uf in r['ufs'].values()),
            r['brasil']['lula_estimado'])
        self.assertAlmostEqual(
            sum(mu['lula_estimado'] for mu in r['municipios'].values()),
            r['brasil']['lula_estimado'])
        self.assertEqual(r['brasil']['zonas_consultadas'],1)

    def test_duas_zonas_concluidas_reconstroem_exatamente_apurado(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':35,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now}
        self.snapshot['observacoes'][id_zona(self.z2)]={
            'lula':15,'flavio':85,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now}
        r=self.teste()
        self.assertEqual(r['brasil']['lula_apurado'],80)
        self.assertEqual(r['brasil']['flavio_apurado'],120)
        self.assertAlmostEqual(r['brasil']['lula_estimado'],80)
        self.assertAlmostEqual(r['brasil']['flavio_estimado'],120)
        self.assertTrue(r['brasil']['apuracao_integral_zonas'])

    def test_observacao_expirada_nao_se_faz_parecer_atual(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':35,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now-2400}
        r=self.teste()
        self.assertEqual(r['brasil']['lula_apurado'],0)
        self.assertEqual(r['brasil']['zonas_desatualizadas'],1)
        self.assertEqual(r['brasil']['zonas_consultadas'],0)
        self.assertEqual(next(x for x in r['linhas'] if x['zona']=='0001')['status'],
                         'desatualizada')

    def test_nega_nacional_sem_ea12_6258_completo(self):
        with self.assertRaisesRegex(ValueError,'Catálogo eleitoral nacional'):
            executar(self.snapshot,self.historico,agora=self.now)

    def test_rejeita_parcial_acima_dos_validos(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':65,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now}
        with self.assertRaisesRegex(ValueError,'inválidas'):
            self.teste()

    def test_zona_sem_historico_usa_reserva_estadual(self):
        self.snapshot['catalogo'].append({
            'uf':'SP','municipio':'71072','zona':'0003'})
        r=self.teste()
        self.assertEqual(len(r['linhas']),3)
        zona3=next(x for x in r['linhas'] if x['zona']=='0003')
        self.assertFalse(zona3['cobertura_historica'])
        self.assertGreater(zona3['lula_projetado'],0)
        self.assertGreater(zona3['flavio_projetado'],0)

    def test_ano_errado_impede_mistura_primeiro_turno(self):
        self.snapshot['eleicao']=6257
        with self.assertRaisesRegex(ValueError,'não corresponde'):
            self.teste()

    def test_chave_identidade_tse(self):
        self.assertEqual(chave_zona('sp','71072','1'),self.z1)


if __name__=='__main__':
    unittest.main()
