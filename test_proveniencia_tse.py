"""Proveniência do EA20: HTTPS TSE, comparação por geração, hash e amostra."""
import unittest
from proveniencia_tse import validar_url_fonte,resumo_sha256,auditar_amostra
from tse import url_resultado_zona


class TestProveniencia(unittest.TestCase):
    def setUp(self):
        self.z=('SP','71072','0001')
        self.url=url_resultado_zona(*self.z)
        self.dados={'lula':60,'flavio':40,'validos':100,
                    'secoes':2,'secoes_total':10,
                    'geracao':'25/10/2026 18:10:00',
                    'url':self.url,'sha256_ea20':'a'*64}
        self.snap={'observacoes':{'SP|71072|0001':dict(self.dados)}}

    def test_url_host_falso_ou_sem_https(self):
        for url in ('http://resultados.tse.jus.br/a',
                    'https://resultados.tse.jus.br.evil.net/a',
                    'https://evil.net/a',
                    'https://resultados.tse.jus.br@evil.net/a',
                    self.url+'?file=evil'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                validar_url_fonte(url,self.url)
        self.assertTrue(validar_url_fonte(self.url,self.url))

    def test_hash_canonico_independe_ordem_chaves(self):
        self.assertEqual(resumo_sha256({'a':1,'b':2}),
                         resumo_sha256({'b':2,'a':1}))

    def test_amostra_valida_realmente_reconsulta(self):
        chamadas=[]
        def buscar(*k):
            chamadas.append(k)
            return dict(self.dados),None
        r=auditar_amostra(self.snap,buscar,max_zonas=5)
        self.assertEqual(r['confirmadas'],1)
        self.assertEqual(r['consultadas'],1)
        self.assertEqual(chamadas,[self.z])

    def test_divergencia_de_hash_ou_votos_bloqueia_amostra(self):
        for campo,valor in [('sha256_ea20','b'*64),('lula',61)]:
            def buscar(*k):
                return {**self.dados,campo:valor},None
            r=auditar_amostra(self.snap,buscar)
            self.assertEqual(r['divergentes'],1)

    def test_cdn_nova_nao_e_contradicao_automatizada(self):
        def buscar(*k):
            return {**self.dados,'geracao':'25/10/2026 18:11:00',
                    'lula':62},None
        r=auditar_amostra(self.snap,buscar)
        self.assertEqual(r['atualizadas'],1)
        self.assertEqual(r['divergentes'],0)

    def test_falta_hash_nao_conta_como_autenticacao(self):
        del self.snap['observacoes']['SP|71072|0001']['sha256_ea20']
        r=auditar_amostra(self.snap,lambda *k:(self.dados,None))
        self.assertEqual(r['confirmadas'],0)
        self.assertEqual(r['inconclusivas'],1)


if __name__=='__main__':
    unittest.main()
