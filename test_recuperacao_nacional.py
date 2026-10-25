"""Recuperação do BR sem dependência de rede e sem votos fictícios."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from recuperacao_nacional import recuperar_serie_de_snapshot
import registro

class TestRecuperarNacional(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/'serie.sqlite'
        self.snapshot=self.root/'dados_zonais_6258.json'

    def tearDown(self):
        self.temp.cleanup()

    def dados(self):
        return {
            'versao':1,'eleicao':6258,'catalogo_origem':'EA16_TSE_3221',
            'catalogo':[], 'observacoes':{},
            'historico_br':[{
                'geracao':'25/10/2026 18:01:00',
                'capturado':'2026-10-25T18:01:30-03:00',
                'secoes':50,'secoes_total':100,
                'validos':1000,'lula':490,'flavio':510
            }]
        }

    def test_ausencia_nao_inventa_historico(self):
        self.assertFalse(recuperar_serie_de_snapshot(self.snapshot,self.db)['restaurado'])
        self.assertFalse(self.db.exists())

    def test_restauracao_e_reexecucao_nao_duplicam_geracoes(self):
        self.snapshot.write_text(json.dumps(self.dados()),encoding='utf-8')
        a=recuperar_serie_de_snapshot(self.snapshot,self.db)
        b=recuperar_serie_de_snapshot(self.snapshot,self.db)
        self.assertTrue(a['restaurado'])
        self.assertTrue(b['restaurado'])
        with patch.object(registro,'DB',self.db):
            serie=registro.serie()
        self.assertEqual(len(serie),1)
        self.assertEqual(int(serie.iloc[0]['lula']),490)
        self.assertEqual(int(serie.iloc[0]['secoes']),50)

    def test_rejeita_snapshot_malformado_ou_votos_invalidos(self):
        self.snapshot.write_text('not json',encoding='utf-8')
        self.assertFalse(recuperar_serie_de_snapshot(self.snapshot,self.db)['restaurado'])
        d=self.dados()
        d['historico_br'][0]['lula']=1500
        self.snapshot.write_text(json.dumps(d),encoding='utf-8')
        self.assertFalse(recuperar_serie_de_snapshot(self.snapshot,self.db)['restaurado'])
        self.assertFalse(self.db.exists())

if __name__=='__main__':
    unittest.main()
