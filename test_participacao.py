"""Cenários de abstenção, comparecimento, votos inválidos e reconciliação."""
import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from importar_participacao import ler_zip, salvar_historico, carregar_participacao
from modelo_participacao import estimar_volume_zona, cenarios_eleitores_marginais
from modelo_zonas import projetar_zonas
from tse import normalizar_ea20


class TestParticipacao(unittest.TestCase):
    def setUp(self):
        self.z=('SP','71072','0001')
        self.part={self.z:{
            (2022,2):{'aptos':1000,'comparecimento':500,'abstencoes':500,
                      'validos':450,'brancos':20,'nulos':30},
            (2026,1):{'aptos':1000,'comparecimento':600,'abstencoes':400,
                      'validos':570,'brancos':10,'nulos':20}
        }}
        self.hist={self.z:{
            (2022,2):{'lula':270,'direita':180,'validos':450},
            (2026,1):{'lula':342,'direita':228,'validos':570}
        }}

    def test_historico_pondera_taxas_e_nao_apenas_votos(self):
        r=estimar_volume_zona(self.part[self.z],peso_2026=.75)
        self.assertAlmostEqual(r['taxa_comparecimento_historica'],.575)
        self.assertAlmostEqual(r['taxa_validos_historica'],.9375)
        self.assertAlmostEqual(r['validos_finais_estimados'],1000*.575*.9375)
        self.assertAlmostEqual(r['comparecimento_final_estimado']+
                               r['abstencoes_finais_estimadas'],1000)

    def test_comparecimento_maior_aumenta_volume_de_validos(self):
        obs={'lula':80,'flavio':60,'validos':140,'brancos':10,'nulos':10,
             'aptos':1200,'aptos_processados':200,
             'comparecimento':160,'abstencoes':40,'secoes':2,'secoes_total':12}
        previsto=estimar_volume_zona(self.part[self.z],obs)
        # A variação de comparecimento na parcial aumenta a taxa projetada,
        # mas com peso conservador devido a possível viés na ordem das seções.
        self.assertGreater(previsto['taxa_comparecimento_estimada_restante'],
                           previsto['taxa_comparecimento_historica'])
        self.assertGreater(previsto['validos_restantes_estimados'],
                           1000*.575*.9375)
        self.assertAlmostEqual(previsto['comparecimento_final_estimado']+
                               previsto['abstencoes_finais_estimadas'],1200)
        self.assertAlmostEqual(
            previsto['comparecimento_final_estimado'],
            (previsto['validos_finais_estimados']+
             previsto['brancos_finais_estimados']+
             previsto['nulos_finais_estimados']+
             previsto['outros_invalidos_finais_estimados']),places=5)

    def test_brancos_nulos_afetam_validos_com_comparecimento_fixo(self):
        normal={'aptos':1000,'aptos_processados':0,'comparecimento':0,
                'abstencoes':0,'brancos':0,'nulos':0,
                'validos':0,'secoes':0,'secoes_total':10}
        prev=estimar_volume_zona(self.part[self.z],normal)
        self.assertLess(prev['validos_finais_estimados'],
                        prev['comparecimento_final_estimado'])
        self.assertGreater(prev['brancos_finais_estimados'],0)
        self.assertGreater(prev['nulos_finais_estimados'],0)

    def test_zona_completa_converge_votos_comparecimento_e_invalidos(self):
        x={'lula':300,'flavio':200,'validos':500,
           'brancos':10,'nulos':20,
           'aptos':800,'aptos_processados':800,
           'comparecimento':530,'abstencoes':270,
           'secoes':10,'secoes_total':10}
        previsto=estimar_volume_zona(self.part[self.z],x)
        self.assertEqual(previsto['validos_finais_estimados'],500)
        self.assertEqual(previsto['brancos_finais_estimados'],10)
        self.assertEqual(previsto['nulos_finais_estimados'],20)
        self.assertEqual(previsto['comparecimento_final_estimado'],530)
        self.assertEqual(previsto['abstencoes_finais_estimadas'],270)

    def test_nao_imputa_turnout_a_parcial_sem_eleitorado_apurado(self):
        r=estimar_volume_zona(self.part[self.z],
               {'validos':100,'lula':60,'flavio':40,'secoes':1,'secoes_total':3})
        self.assertIsNone(r)

    def test_modelo_zonal_usa_participacao_se_disponivel(self):
        x=projetar_zonas({},self.hist,universo={self.z},
                        participacao=self.part,intensidade=.35)
        linha=x['linhas'][0]
        self.assertEqual(linha['modelo_volume'],'participacao')
        self.assertAlmostEqual(linha['validos_projetados'],1000*.575*.9375)
        self.assertIsNotNone(linha['abstencoes_finais_estimadas'])
        y=projetar_zonas({},self.hist,universo={self.z})
        self.assertEqual(y['linhas'][0]['modelo_volume'],'validos_historicos')

    def test_sensibilidade_marginal_nao_inventa_preferencia(self):
        obs={'lula':80,'flavio':60,'validos':140,'brancos':10,'nulos':10,
             'aptos':1200,'aptos_processados':200,
             'comparecimento':160,'abstencoes':40,'secoes':2,'secoes_total':12}
        r=estimar_volume_zona(self.part[self.z],obs)
        cenarios=cenarios_eleitores_marginais(r,p_lula=.6)
        self.assertEqual(len(cenarios),3)
        self.assertLess(cenarios[0]['efeito_lula_vs_distribuicao_base'],0)
        self.assertGreater(cenarios[-1]['efeito_lula_vs_distribuicao_base'],0)

    def test_schema_oficial_e_eleitorado(self):
        payload={'dg':'04/10/2026','hg':'18:19:59',
          's':{'st':'10','ts':'100'},
          'e':{'te':'1000','est':'100','c':'80','a':'20'},
          'v':{'vv':'75','tv':'80','vb':'2','tvn':'3'},
          'carg':[{'cd':'1','agr':[{'par':[{'cand':[
            {'n':'13','vap':'40'}, {'n':'22','vap':'35'}]}]}]}]}
        r=normalizar_ea20(payload,'SP')
        for chave,valor in [('aptos',1000),('aptos_processados',100),
                            ('comparecimento',80),('abstencoes',20),
                            ('brancos',2),('nulos',3)]:
            self.assertEqual(r[chave],valor)
        payload['e']['est']='50'
        with self.assertRaisesRegex(ValueError,'supera eleitorado processado'):
            normalizar_ea20(payload,'SP')

    def test_zip_filtra_cargo_e_turno_e_nao_duplica(self):
        cab='NR_TURNO;SG_UF;CD_MUNICIPIO;NR_ZONA;CD_CARGO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES;QT_VOTOS_VALIDOS;QT_VOTOS_BRANCOS;QT_VOTOS_NULOS\n'
        row='1;SP;71072;1;1;100;80;20;75;2;3\n'
        with tempfile.TemporaryDirectory() as tmp:
            caminho=Path(tmp)/'dados.zip'
            with zipfile.ZipFile(caminho,'w') as z:
                z.writestr('detalhe_munzona_2026_BRASIL.csv',
                            cab+row+'1;SP;71072;1;3;100;80;20;70;5;5\n')
            mapa=ler_zip(caminho,2026,1)
            self.assertEqual(len(mapa),1)
            self.assertEqual(mapa[('SP','71072','0001',2026,1)],
                             (100,80,20,2,3,75))
            destino=Path(tmp)/'historico.csv'
            salvar_historico(mapa,destino,2026,1,exigir_cobertura=False)
            self.assertEqual(carregar_participacao(destino)[self.z][(2026,1)]['aptos'],100)


if __name__=='__main__':
    unittest.main()
