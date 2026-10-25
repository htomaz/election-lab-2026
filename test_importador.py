"""Não permitir que uma importação inválida destrua históricos corretos."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from importar_historico import importar_zip


class TestImportador(unittest.TestCase):
    def test_zip_parcial_nao_sobrescreve_historicos(self):
        with tempfile.TemporaryDirectory() as pasta:
            base=Path(pasta)
            zona=base/'zonas.csv';uf=base/'ufs.csv'
            zona.write_text('HISTORICO_OK\n',encoding='utf-8')
            uf.write_text('HISTORICO_OK\n',encoding='utf-8')
            cabecalho='NR_TURNO;SG_UF;NR_CANDIDATO;CD_CARGO;CD_MUNICIPIO;NR_ZONA;QT_VOTOS_NOMINAIS\n'
            registro='2;SP;13;1;71072;1;100\n'
            zip_path=base/'historico2022.zip'
            with zipfile.ZipFile(zip_path,'w') as arquivo:
                arquivo.writestr('votacao_candidato_munzona_2022_BRASIL.csv',
                                 cabecalho+registro)
            with self.assertRaisesRegex(ValueError,'incompleta'):
                importar_zip(zip_path,2022,2,arquivo_saida=uf,arquivo_zonas=zona)
            self.assertEqual(zona.read_text(encoding='utf-8'),'HISTORICO_OK\n')
            self.assertEqual(uf.read_text(encoding='utf-8'),'HISTORICO_OK\n')


if __name__=='__main__':
    unittest.main()
