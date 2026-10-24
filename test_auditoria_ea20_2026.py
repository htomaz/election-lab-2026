"""Regressões baseadas nos atributos EA20 oficial do TSE (13/10/2026).

Referência: https://www.tse.jus.br/eleicoes/eleicoes-2026-content/
arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado
As amostras abaixo são FICTÍCIAS, não resultados de 2026T2.
"""
import unittest
from unittest.mock import patch,Mock
from modelo_participacao import estimar_volume_zona
from modelo_zonas import projetar_zonas,calibrar_taxas_uf_observadas
from tse import baixar_zona, normalizar_ea20


def payload_ea20():
    return {
      'ele':'6258','t':'2','f':'o','tpabr':'zona','cdabr':'0001',
      'dg':'25/10/2026','hg':'18:00:00','idg':42,
      's':{'st':2,'ts':4},
      'e':{'te':220,'est':120,'esi':100,'esni':20,
           'esa':100,'esna':0,'esnt':100,
           'c':80,'a':20},
      'v':{'tv':80,'vv':75,'vb':2,'tvn':3,'vn':3,'vnt':0},
      'carg':[{'cd':'1','agr':[{'par':[{'cand':[
           {'n':'13','vap':40},{'n':'22','vap':35}]}]}]}]
    }


class TestAuditoriaOficialEA20(unittest.TestCase):
    def setUp(self):
        self.z=('SP','71072','0001')
        self.part={self.z:{
            (2026,1):{'aptos':220,'comparecimento':132,
                      'abstencoes':88,'validos':120,
                      'brancos':6,'nulos':6},
            (2022,2):{'aptos':220,'comparecimento':121,
                      'abstencoes':99,'validos':110,
                      'brancos':5,'nulos':6}}}
        self.historico={self.z:{
            (2026,1):{'lula':70,'direita':50,'validos':120},
            (2022,2):{'lula':60,'direita':50,'validos':110}}}

    def test_esi_diferente_est_sem_falso_erro(self):
        p=payload_ea20()
        out=normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                           exigir_metadados=True)
        self.assertEqual(out['aptos_processados'],120)
        self.assertEqual(out['aptos_instalados'],100)
        self.assertEqual(out['aptos_nao_instalados'],20)
        self.assertEqual(out['nulos'],3)  # tvn inclui nulos técnicos

    def test_taxa_comparecimento_usa_instalados_e_nao_totalizados(self):
        p=normalizar_ea20(payload_ea20(),'SP',abrangencia_esperada='zona',
                          exigir_metadados=True)
        p.update({'zona':'0001','secoes':2,'secoes_total':4})
        resultado=estimar_volume_zona(self.part[self.z],p,
                                      peso_2026=.75,intensidade=.35)
        self.assertAlmostEqual(resultado['aptos_restantes'],100)
        self.assertEqual(resultado['aptos_nao_instalados'],20)
        # 80/100 = 80% entre seções instaladas; 80/120 seria falso.
        self.assertGreater(resultado['taxa_comparecimento_estimada_restante'],
                           resultado['taxa_comparecimento_historica']+.02)

    def test_sinal_uf_usa_eleitorado_instalado(self):
        p=normalizar_ea20(payload_ea20(),'SP',abrangencia_esperada='zona',
                          exigir_metadados=True)
        sinais=calibrar_taxas_uf_observadas(
            {self.z:p},self.part,peso_2026=.75,intensidade=.8)
        self.assertGreater(sinais['SP']['turnout'],0)

    def test_fim_de_apuracao_com_secao_nao_instalada_preserva_votos(self):
        p=payload_ea20()
        p['s']={'st':4,'ts':4}
        p['e'].update({'te':120,'est':120,'esnt':0})
        obs=normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                           exigir_metadados=True)
        r=estimar_volume_zona(self.part[self.z],obs,intensidade=.35)
        self.assertEqual(r['validos_finais_estimados'],75)
        self.assertEqual(r['comparecimento_final_estimado'],80)
        self.assertEqual(r['abstencoes_finais_estimadas'],20)
        # Os 20 eleitores de seção não instalada NÃO são 20 abstenções.
        self.assertEqual(r['comparecimento_final_estimado']+
                         r['abstencoes_finais_estimadas'],100)

    def test_rejeita_primeiro_turno_e_simulado(self):
        for campo,valor in [('t','1'),('ele','6257'),('f','s')]:
            p=payload_ea20()
            p[campo]=valor
            with self.subTest(campo=campo),self.assertRaisesRegex(
                ValueError,'turno|eleição|simulado'):
                normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                               exigir_metadados=True)

    def test_rejeita_abrangencia_e_identidade_faltante(self):
        p=payload_ea20()
        p['tpabr']='uf'
        with self.assertRaisesRegex(ValueError,'abrangência'):
            normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                           exigir_metadados=True)
        p=payload_ea20()
        p.pop('ele')
        with self.assertRaisesRegex(ValueError,'identidade'):
            normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                           exigir_metadados=True)

    def test_rejeita_eleitorado_instalado_impossivel(self):
        p=payload_ea20()
        p['e']['esi']=80  # e.esi + e.esni != e.est
        with self.assertRaisesRegex(ValueError,'composição'):
            normalizar_ea20(p,'SP',abrangencia_esperada='zona',
                           exigir_metadados=True)

    def test_baixar_zona_rejeita_simulacao_com_http_200(self):
        p=payload_ea20()
        p['f']='s'
        resposta=Mock()
        resposta.raise_for_status.return_value=None
        resposta.json.return_value=p
        with patch('tse.requests.get',return_value=resposta):
            zona,erro=baixar_zona('SP','71072','0001')
        self.assertIsNone(zona)
        self.assertIn('simulado',erro)

    def test_baixar_zona_rejeita_zona_trocada(self):
        p=payload_ea20()
        p['cdabr']='0002'
        resposta=Mock()
        resposta.raise_for_status.return_value=None
        resposta.json.return_value=p
        with patch('tse.requests.get',return_value=resposta):
            zona,erro=baixar_zona('SP','71072','0001')
        self.assertIsNone(zona)
        self.assertIn('diferente',erro)


if __name__=='__main__':
    unittest.main()
