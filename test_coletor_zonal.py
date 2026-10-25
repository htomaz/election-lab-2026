"""Coletor zonal: limites de tráfego, persistência e erros HTTP."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coletor_zonal import catalogar_ea16, coletar


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

    def _executar_teste(self,caminho,**kwargs):
        return coletar(caminho,uf='SP',limite=50,origem=self.catal,
                       coletar_zona=self.buscar,permitir_antes=True,
                       clock=lambda:self.tempo,sleep=lambda s:None,
                       **kwargs)

    def test_persistencia_incremental_sem_reconsultar(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados_zonais_6258.json'
            a=self._executar_teste(arq)
            self.assertEqual(a['requisicoes'],2)
            self.assertEqual(a['atualizadas'],2)
            dados=json.loads(arq.read_text(encoding='utf-8'))
            self.assertEqual(len(dados['observacoes']),2)
            self.assertTrue(dados['catalogo_origem']=='CATALOGO_INJETADO_TESTE')
            b=self._executar_teste(arq)
            self.assertEqual(b['requisicoes'],0)
            self.assertEqual(len(self.leituras),2)
            self.tempo+=200
            c=self._executar_teste(arq)
            self.assertEqual(c['requisicoes'],2)

    def test_erro_404_interrompe_sem_apagar_snapshot(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados.json'
            self._executar_teste(arq)
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

    def test_coleta_sp_e_rj_preserva_snapshot_entre_ufs(self):
        a=self.a
        rj=('RJ','60011','0001')
        catalogo_sp={a:self.catal[a]}
        catalogo_rj={rj:{'uf':'RJ','municipio':'60011','zona':'0001'}}
        chamadas=[]
        def remoto(*,abrangencias):
            chamadas.append(abrangencias)
            return catalogo_sp if abrangencias==['SP'] else catalogo_rj
        def buscar(uf,mun,zona):
            return {'uf':uf,'municipio':mun,'zona':zona,
                    'lula':40,'flavio':60,'validos':100,
                    'secoes':1,'secoes_total':1,
                    'geracao':'25/10/2026 18:00:00'},None
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'snap.json'
            with patch('coletor_zonal.consultar_config',
                       return_value={'pleito_2turno_confirmado':True}), \
                 patch('coletor_zonal.baixar_catalogo',side_effect=remoto):
                x=coletar(arq,uf='SP',limite=10,coletar_zona=buscar,
                         permitir_antes=True,clock=lambda:self.tempo,
                         sleep=lambda s:None)
                self.assertEqual(x['catalogo'],1)
                # Outra UF não pode descartar o catálogo nem os votos SP.
                y=coletar(arq,uf='RJ',limite=10,coletar_zona=buscar,
                         permitir_antes=True,clock=lambda:self.tempo,
                         sleep=lambda s:None)
                self.assertEqual(y['catalogo'],2)
                dados=json.loads(arq.read_text(encoding='utf-8'))
                self.assertEqual(len(dados['catalogo']),2)
                self.assertEqual(len(dados['observacoes']),2)
                self.assertEqual(chamadas,[['SP'],['RJ']])
                # Reconsulta SP aproveita EA16 salvo, sem HTTP para catálogo.
                self.tempo+=500
                coletar(arq,uf='SP',limite=10,coletar_zona=buscar,
                       permitir_antes=True,clock=lambda:self.tempo,
                       sleep=lambda s:None)
                self.assertEqual(chamadas,[['SP'],['RJ']])

    def test_preflight_bloqueia_urls_se_ea11_nao_publicou_3221(self):
        with tempfile.TemporaryDirectory() as dir:
            with patch('coletor_zonal.consultar_config',
                       return_value={'pleito_2turno_confirmado':False}), \
                 patch('coletor_zonal.baixar_catalogo') as baixar:
                with self.assertRaisesRegex(ValueError,'não publicou'):
                    coletar(Path(dir)/'dados.json',uf='SP',
                           permitir_antes=True,clock=lambda:self.tempo)
                baixar.assert_not_called()

    def test_bloqueio_da_escrita_concorrente(self):
        from coletor_zonal import _arquivo_bloqueado
        with tempfile.TemporaryDirectory() as dir:
            destino=Path(dir)/'dados.json'
            with _arquivo_bloqueado(destino):
                with self.assertRaisesRegex(RuntimeError,'Já existe uma coleta'):
                    self._executar_teste(destino)

    def test_rejeita_execucao_antes_da_eleicao(self):
        with tempfile.TemporaryDirectory() as dir:
            with self.assertRaisesRegex(ValueError,'apuração oficial'):
                coletar(Path(dir)/'dados.json',uf='SP',
                        origem=self.catal,coletar_zona=self.buscar,agora=1_760_000_000)

    def test_rejeita_excesso_taxa(self):
        with tempfile.TemporaryDirectory() as dir:
            with self.assertRaisesRegex(ValueError,'faixa segura'):
                self._executar_teste(Path(dir)/'dados.json',taxa=150)

    def test_snapshot_ficticio_nao_pode_virar_oficial(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados.json'
            self._executar_teste(arq)
            original=arq.read_bytes()
            with self.assertRaisesRegex(ValueError,'não misturar'):
                coletar(arq,uf='SP',permitir_antes=True,clock=lambda:self.tempo)
            self.assertEqual(arq.read_bytes(),original)

    def test_snapshot_oficial_nao_pode_virar_teste(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados.json'
            with patch('coletor_zonal.consultar_config',
                       return_value={'pleito_2turno_confirmado':True}), \
                 patch('coletor_zonal.baixar_catalogo',
                       return_value=self.catal):
                coletar(arq,uf='SP',limite=2,coletar_zona=self.buscar,
                       permitir_antes=True,clock=lambda:self.tempo,
                       sleep=lambda t:None)
            with self.assertRaisesRegex(ValueError,'não misturar'):
                self._executar_teste(arq)

    def test_rejeita_resposta_de_outra_zona_e_votos_invalidos(self):
        with tempfile.TemporaryDirectory() as dir:
            arq=Path(dir)/'dados.json'
            def buscar_errado(uf,municipio,zona):
                obs,_=self.buscar(uf,municipio,zona)
                obs['zona']='9999'
                return obs,None
            r=coletar(arq,uf='SP',limite=2,origem=self.catal,
                     coletar_zona=buscar_errado,permitir_antes=True,
                     clock=lambda:self.tempo,sleep=lambda t:None)
            self.assertEqual(r['atualizadas'],0)
            self.assertEqual(r['erros'],2)
            self.assertFalse(json.loads(arq.read_text())['observacoes'])
            def votos_errados(uf,municipio,zona):
                obs,_=self.buscar(uf,municipio,zona)
                obs['validos']=101
                return obs,None
            r=coletar(arq,uf='SP',limite=2,origem=self.catal,
                     coletar_zona=votos_errados,permitir_antes=True,
                     clock=lambda:self.tempo,sleep=lambda t:None)
            self.assertEqual(r['atualizadas'],0)

    def test_circuit_breaker_apos_20_timeouts(self):
        with tempfile.TemporaryDirectory() as dir:
            catalogo={}
            for i in range(1,46):
                k=('SP','71072',str(i).zfill(4))
                catalogo[k]={'uf':k[0],'municipio':k[1],'zona':k[2]}
            def timeout(*_):
                return None,'ReadTimeout: falha temporária'
            arq=Path(dir)/'dados.json'
            r=coletar(arq,uf='SP',limite=45,origem=catalogo,
                     coletar_zona=timeout,permitir_antes=True,
                     concorrencia=1,clock=lambda:self.tempo,
                     sleep=lambda s:None)
            self.assertTrue(r['interrompido'])
            self.assertEqual(r['requisicoes'],20)
            self.assertEqual(r['atualizadas'],0)
            self.assertEqual(len(json.loads(arq.read_text())['observacoes']),0)

    def test_cat_ea16_uf_municipio_zona_com_zeros(self):
        p={'abr':[{'cd':'SP','mu':[{'cd':'71072','nm':'SÃO PAULO',
                                  'zon':[{'cd':'1','sec':[{'ns':'0001'}]},{'cd':'0237','sec':[]}]}]}]}
        x=catalogar_ea16(p)
        self.assertEqual(len(x),2)
        self.assertEqual(x[self.a]['nome'],'SÃO PAULO')
        self.assertEqual(x[self.a]['secoes_cadastradas_ea16'],1)
        self.assertEqual(x[self.a]['secoes_agregadas_ea16'],0)
        self.assertEqual(x[('SP','71072','0237')]['zona'],'0237')
        with self.assertRaisesRegex(ValueError,'duplicada'):
            catalogar_ea16({'abr':[{'cd':'SP','mu':[{
                'cd':'71072','zon':[{'cd':'1','sec':[]},{'cd':'0001','sec':[]}]}]}]})

    def test_ea16_conta_principal_sem_duplicar_agregada(self):
        # nsp identifica a seção principal. nsa é apenas o vínculo reverso.
        p={'abr':[{'cd':'SP','mu':[{'cd':'71072','zon':[
            {'cd':'1','sec':[
                {'ns':'0001','nsa':['0002','0003']},
                {'ns':'0002','nsp':'0001'},
                {'ns':'0003','nsp':'0001'},
                {'ns':'0004'}]}
        ]}]}]}
        zona=catalogar_ea16(p)[self.a]
        self.assertEqual(zona['secoes_cadastradas_ea16'],2)
        self.assertEqual(zona['secoes_agregadas_ea16'],2)
        self.assertEqual(zona['secoes_listadas_ea16'],4)
        p['abr'][0]['mu'][0]['zon'][0]['sec'][1]['nsp']='9999'
        with self.assertRaisesRegex(ValueError,'nsp sem seção principal'):
            catalogar_ea16(p)


if __name__=='__main__':
    unittest.main()
