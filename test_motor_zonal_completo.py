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

    def _calcular_teste(self,**kwargs):
        return executar(self.snapshot,self.historico,nomes=self.nomes,
                        agora=self.now,exigir_catalogo_nacional=False,**kwargs)

    def test_sem_observacoes_mantem_todas_as_zonas(self):
        r=self._calcular_teste()
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
        r=self._calcular_teste()
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
        r=self._calcular_teste()
        self.assertEqual(r['brasil']['lula_apurado'],80)
        self.assertEqual(r['brasil']['flavio_apurado'],120)
        self.assertAlmostEqual(r['brasil']['lula_estimado'],80)
        self.assertAlmostEqual(r['brasil']['flavio_estimado'],120)
        self.assertTrue(r['brasil']['apuracao_integral_zonas'])

    def test_observacao_expirada_nao_se_faz_parecer_atual(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':35,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now-2400}
        r=self._calcular_teste()
        # Coleta antiga não é 'ao vivo', mas os votos já publicados
        # continuam conhecidos e não podem ser reestimados como ausentes.
        self.assertEqual(r['brasil']['lula_apurado'],65)
        self.assertEqual(r['brasil']['zonas_desatualizadas'],1)
        self.assertEqual(r['brasil']['zonas_consultadas'],0)
        self.assertEqual(r['brasil']['zonas_com_observacao'],1)
        self.assertEqual(next(x for x in r['linhas'] if x['zona']=='0001')['status'],
                         'desatualizada')

    def test_nega_nacional_sem_ea16_3221_completo(self):
        with self.assertRaisesRegex(ValueError,'Catálogo EA16 nacional'):
            executar(self.snapshot,self.historico,agora=self.now)

    def test_rejeita_parcial_acima_dos_validos(self):
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':65,'flavio':65,'validos':100,'secoes':2,
            'secoes_total':2,'capturado_em':self.now}
        with self.assertRaisesRegex(ValueError,'inválidas'):
            self._calcular_teste()

    def test_zona_sem_historico_usa_reserva_estadual(self):
        self.snapshot['catalogo'].append({
            'uf':'SP','municipio':'71072','zona':'0003'})
        r=self._calcular_teste()
        self.assertEqual(len(r['linhas']),3)
        zona3=next(x for x in r['linhas'] if x['zona']=='0003')
        self.assertFalse(zona3['cobertura_historica'])
        self.assertGreater(zona3['lula_projetado'],0)
        self.assertGreater(zona3['flavio_projetado'],0)

    def test_ano_errado_impede_mistura_primeiro_turno(self):
        self.snapshot['eleicao']=6257
        with self.assertRaisesRegex(ValueError,'não corresponde'):
            self._calcular_teste()

    def test_reconstrucao_nacional_2026t1_se_todas_zonas_contadas(self):
        # Teste algébrico com o resultado final já conhecido de 2026T1:
        # os demais candidatos entram em validos, mas não são Flávio.
        from modelo_zonas import carregar_zonas
        historico=carregar_zonas('historico_zonas.csv')
        chaves=[k for k,v in historico.items() if (2026,1) in v]
        snap={'versao':1,'eleicao':6258,'catalogo_origem':'TESTE_HISTORICO',
              'catalogo':[{'uf':k[0],'municipio':k[1],'zona':k[2]} for k in chaves],
              'observacoes':{}}
        for k in chaves:
            v=historico[k][(2026,1)]
            snap['observacoes'][id_zona(k)]={'lula':v['lula'],
                'flavio':v['direita'],'validos':v['validos'],
                'secoes':1,'secoes_total':1,'capturado_em':self.now}
        r=executar(snap,historico,agora=self.now,
                  exigir_catalogo_nacional=False)
        self.assertEqual(r['brasil']['zonas_concluidas'],len(chaves))
        self.assertAlmostEqual(r['brasil']['lula_estimado'],53879538,places=3)
        self.assertAlmostEqual(r['brasil']['flavio_estimado'],56104503,places=3)
        self.assertAlmostEqual(r['brasil']['lula_apurado'],53879538,places=3)
        self.assertAlmostEqual(r['brasil']['flavio_apurado'],56104503,places=3)

    def test_participacao_completa_consolida_abstencao_brancos_nulos(self):
        part={
            self.z1:{
                (2022,2):{'aptos':150,'comparecimento':120,'abstencoes':30,
                          'brancos':5,'nulos':5,'validos':110},
                (2026,1):{'aptos':160,'comparecimento':130,'abstencoes':30,
                          'brancos':6,'nulos':6,'validos':118}},
            self.z2:{
                (2022,2):{'aptos':150,'comparecimento':120,'abstencoes':30,
                          'brancos':5,'nulos':5,'validos':110},
                (2026,1):{'aptos':160,'comparecimento':130,'abstencoes':30,
                          'brancos':6,'nulos':6,'validos':118}}
        }
        self.snapshot['observacoes'][id_zona(self.z1)]={
            'lula':44,'flavio':38,'validos':82,
            'brancos':4,'nulos':4,'aptos':160,
            'aptos_processados':100,'comparecimento':90,'abstencoes':10,
            'secoes':2,'secoes_total':4,'capturado_em':self.now}
        r=self._calcular_teste(participacao=part)
        b=r['brasil']
        self.assertEqual(b['zonas_modeladas_participacao'],2)
        self.assertAlmostEqual(b['comparecimento_estimado_participacao']+
                               b['abstencoes_estimadas_participacao'],
                               b['aptos_estimados_participacao'])
        self.assertGreater(b['brancos_estimados_participacao'],4)
        self.assertGreater(b['nulos_estimados_participacao'],4)
        self.assertEqual(r['linhas'][0]['modelo_volume'],'participacao')
        self.assertEqual(b['lula_apurado'],44)
        self.assertEqual(b['flavio_apurado'],38)
        self.assertAlmostEqual(sum(x['lula_estimado'] for x in r['ufs'].values()),
                               b['lula_estimado'])

    def test_chave_identidade_tse(self):
        self.assertEqual(chave_zona('sp','71072','1'),self.z1)


if __name__=='__main__':
    unittest.main()
