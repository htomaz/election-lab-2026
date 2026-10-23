"""Valida códigos TSE preservados e nomes humanos vindos do EA12 oficial."""
import csv
import tempfile
import unittest
from pathlib import Path

from municipios_tse import (
    URL_MUNICIPIOS, interpretar_ea12, ler_csv_local,
    nome_municipio, normalizar_codigo, ordenar_municipios,
)


class TestMunicipios(unittest.TestCase):
    def setUp(self):
        self.payload={'abr':[
            {'cd':'SP','mu':[
                {'cd':'71072','nm':'SÃO PAULO','cdi':'3550308'},
                {'cd':'62910','nm':'CAMPINAS','cdi':'3509502'},
                {'cd':'00435','nm':'ABACAXI'}]},
            {'cd':'RJ','mu':[{'cd':'71072','nm':'NOME DISTINTO'}]},
            {'cd':'ZZ','mu':[{'cd':'00999','nm':'EXTERIOR - TESTE'}]}
        ]}

    def test_mapa_tse_e_ibge_nao_se_confundem(self):
        nomes=interpretar_ea12(self.payload)
        self.assertEqual(nomes[('SP','71072')],'SÃO PAULO')
        self.assertEqual(nome_municipio('SP','71072',nomes),'SÃO PAULO')
        self.assertEqual(nome_municipio('RJ','71072',nomes),'NOME DISTINTO')
        self.assertNotIn(('SP','3550308'),nomes)
        self.assertIn('/6257/config/mun-e006257-cm.json',URL_MUNICIPIOS)

    def test_ordenacao_alfabetica_preserva_codigo_original(self):
        nomes=interpretar_ea12(self.payload)
        opcoes=ordenar_municipios('SP',['71072','62910','00435'],nomes)
        self.assertEqual(opcoes,['00435','62910','71072'])
        self.assertEqual(normalizar_codigo('435'),'00435')

    def test_fallback_explicito_sem_inventar_nome(self):
        self.assertEqual(nome_municipio('SP','71072',{}),
                         'Município 71072 (nome indisponível)')

    def test_rejeita_formato_invalido_e_ambiguo(self):
        with self.assertRaises(ValueError):
            interpretar_ea12({'mu':[]})
        with self.assertRaisesRegex(ValueError,'duplicado'):
            interpretar_ea12({'abr':[{'cd':'SP','mu':[
                {'cd':'71072','nm':'SÃO PAULO'},
                {'cd':'71072','nm':'SANTO ANDRÉ'}]}]})

    def test_snapshot_oficial_versionado_cobre_historico(self):
        from municipios_tse import obter_municipios
        import csv
        from pathlib import Path
        mapa=obter_municipios('municipios_2026.csv')
        self.assertEqual(len(mapa),5757)
        self.assertEqual(mapa[('SP','71072')],'SÃO PAULO')
        with Path('historico_zonas.csv').open(newline='',encoding='utf-8-sig') as f:
            codigos={(r['uf'],r['municipio']) for r in csv.DictReader(f)}
        ausentes=codigos-set(mapa)
        # Uma localidade ZZ de eleições passadas já não consta no EA12 2026.
        self.assertEqual(ausentes,{('ZZ','99252')})

    def test_csv_local_valida_e_preserva_zeros(self):
        with tempfile.TemporaryDirectory() as pasta:
            path=Path(pasta)/'municipios_2026.csv'
            with path.open('w',newline='',encoding='utf-8') as f:
                w=csv.writer(f)
                w.writerow(['uf','municipio','nome'])
                w.writerow(['SP','00435','ABACAXI'])
            self.assertEqual(ler_csv_local(path)[('SP','00435')],'ABACAXI')


if __name__=='__main__':
    unittest.main()
