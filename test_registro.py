"""Persistência e recuperação operacional da série do TSE."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import registro


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'series.sqlite'
        self.original=registro.DB
        registro.DB=self.path

    def tearDown(self):
        registro.DB=self.original
        self.tmp.cleanup()

    def snapshot(self):
        return {'geracao':'25/10/2026 18:01:00','secoes':80,
                'secoes_total':100,'validos':4000,
                'lula':2100,'flavio':1900}

    def test_nao_apaga_projecao_se_reconsulta_sem_projetar(self):
        x=self.snapshot()
        registro.salvar(x,{'lula':5100,'flavio':4900,'completo':True})
        registro.salvar(x,None)
        df=registro.serie()
        self.assertEqual(len(df),1)
        self.assertAlmostEqual(df.iloc[0]['proj_lula'],5100)
        self.assertEqual(df.iloc[0]['secoes'],80)

    def test_restaurar_apos_recriar_banco_e_nao_regredir(self):
        registro.salvar(self.snapshot(),{'lula':5100,'flavio':4900,
                                         'completo':True})
        csv=registro.exportar_csv()
        self.assertIn('geracao,capturado',csv)
        self.path.unlink()
        r=registro.restaurar_csv(csv)
        self.assertEqual(r['linhas_recebidas'],1)
        self.assertAlmostEqual(registro.serie().iloc[0]['proj_flavio'],4900)
        antigo=csv.replace(',80,100,4000,2100,1900,',
                           ',2,100,4000,2100,1900,')
        registro.restaurar_csv(antigo)
        self.assertEqual(registro.serie().iloc[0]['secoes'],80)

    def test_nao_aceita_arquivo_malformado(self):
        with self.assertRaisesRegex(ValueError,'nove colunas'):
            registro.restaurar_csv('bad_header\n1\n')
        with self.assertRaisesRegex(ValueError,'5 MB'):
            registro.restaurar_csv(b'a'*(5*1024*1024+1))

    def test_mesma_geracao_mais_recente_pode_corrigir_votos(self):
        x=self.snapshot()
        registro.salvar(x,{'lula':5100,'flavio':4900,'completo':True})
        x['secoes']=81
        x['validos']=4050
        x['lula']=2120
        x['flavio']=1930
        registro.salvar(x,None)
        row=registro.serie().iloc[0]
        self.assertEqual(row['secoes'],81)
        self.assertEqual(row['validos'],4050)
        self.assertAlmostEqual(row['proj_lula'],5100)


if __name__=='__main__':
    unittest.main()
