"""Coletor zonal: limites de tráfego, persistência e erros HTTP."""
import json
import tempfile
import unittest
from pathlib import Path

from coletor_zonal import catalogar_ea12, coletar


class TestColetorZonal(unittest.TestCase):
    def setUp(self):
        self.a=('SP','71072','0001')
        self.b=('SP','71072','0002')
        self.catal={
            self.a:{'uf':'SP','municipio':'71072','zona':'0001','nome':'SÃO PAULO'},
            self.b:{'uf':'SP','municipio':'71072','zona':'0002','nome':'SÃO PAULO'}}
        self.tempo=1_800_000_000.
        self.leituras=[]

    def buscar(self,uf,municipio,zona):
        self.leituras.append((uf,municipio,zona))
        return {'uf':uf,'municipio':municipio,'zona':zona,
                'lula':60,'flavio':40,'validos':100,
                'secoes':1,'secoes_total':1,
                'geracao':'25/10/2026 18:00:00'},None

    def testar(self,caminho,**kwargs):
        return coletar(caminho,uf='SP',limite=50,origem=self.catal,
                       coletar_zona=self.buscar,permitir_antes=True,
                       clock=lambda:self.tempo,sleep=lambda s:None,
                       **kwargs)

    def test_persistencia_incremental_sem_reconsultar(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados_zonais_6258.json'
            a=self.testar(arq)
            self.assertEqual(a['requisicoes'],2)
            self.assertEqual(a['atualizadas'],2)
            dados=json.loads(arq.read_text(encoding='utf-8'))
            self.assertEqual(len(dados['observacoes']),2)
            self.assertTrue(dados['catalogo_origem']=='EA12_TSE_6258')
            b=self.testar(arq)
            self.assertEqual(b['requisicoes'],0)
            self.assertEqual(len(self.leituras),2)
            self.tempo+=200
            c=self.testar(arq)
            self.assertEqual(c['requisicoes'],2)

    def test_erro_404_interrompe_sem_apagar_snapshot(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados.json'
            self.testar(arq)
            self.tempo+=500

            def erro(*key):
                return None,'HTTPError: 404 Not Found'
            self.leituras=[]
            r=coletar(arq,uf='SP',limite=50,origem=self.catal,
                      coletar_zona=erro,permitir_antes=True,
                      concorrencia=1,clock=lambda:self.tempo,
                      sleep=lambda s:None)
            self.assertTrue(r['interrompido'])
            self.assertLessEqual(r['requisicoes'],1)
            dados=json.loads(arq.read_text(encoding='utf-8'))
            self.assertEqual(len(dados['observacoes']),2)

    def test_rejeita_execucao_antes_da_eleicao(self):
        with tempfile.TemporaryDirectory() as dir:
            with self.assertRaisesRegex(ValueError,'apuração oficial'):
                coletar(Path(dir)/'dados.json',uf='SP',
                        origem=self.catal,coletar_zona=self.buscar)

    def test_rejeita_excesso_taxa(self):
        with tempfile.TemporaryDirectory() as dir:
            with self.assertRaisesRegex(ValueError,'faixa segura'):
                self.testar(Path(dir)/'dados.json',taxa=150)

    def test_cat_ea12_uf_municipio_zona_com_zeros(self):
        p={'abr':[{'cd':'SP','mu':[{'cd':'71072','nm':'SÃO PAULO',
                                  'zon':[{'cd':'1'},{'cd':'0237'}]}]}]}
        x=catalogar_ea12(p)
        self.assertEqual(len(x),2)
        self.assertEqual(x[self.a]['nome'],'SÃO PAULO')
        self.assertEqual(x[('SP','71072','0237')]['zona'],'0237')
        with self.assertRaisesRegex(ValueError,'duplicada'):
            catalogar_ea12({'abr':[{'cd':'SP','mu':[{
                'cd':'71072','zon':[{'cd':'1'},{'cd':'0001'}]}]}]})


if __name__=='__main__':
    unittest.main()
