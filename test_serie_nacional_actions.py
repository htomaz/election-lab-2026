"""Retomada de séries oficiais dentro de artefatos com partes diferentes."""
import unittest
from datetime import datetime, timezone
from serie_nacional_actions import incorporar, registrar_oficial
from backup_actions import mesclar


def item(hora, secoes, lula, flavio):
    return {'geracao':f'25/10/2026 {hora}:00',
            'capturado':'2026-10-25T21:00:00+00:00',
            'secoes':secoes,'secoes_total':200,'validos':lula+flavio,
            'lula':lula,'flavio':flavio}


def snap(historico):
    return {'versao':1,'eleicao':6258,'catalogo_origem':'EA16_TSE_3221',
            'catalogo':[{'uf':'SP','municipio':'71072','zona':'0001'}],
            'observacoes':{},'historico_br':historico}


class TestSerieNacionalActions(unittest.TestCase):
    def test_merge_preserva_todas_geracoes(self):
        a=snap([item('18:00',10,60,40),item('18:15',50,260,240)])
        b=snap([item('18:30',100,510,490)])
        t=mesclar(a,b)
        self.assertEqual([x['secoes'] for x in t['historico_br']],[10,50,100])
        self.assertEqual([x['validos'] for x in t['historico_br']],[100,500,1000])

    def test_rejeita_regressao_e_dados_ficticios(self):
        with self.assertRaisesRegex(ValueError,'regressão'):
            incorporar([item('18:00',100,600,400)],
                       [item('18:15',90,550,350)])
        s=snap([])
        s['catalogo_origem']='CATALOGO_INJETADO_TESTE'
        with self.assertRaisesRegex(ValueError,'não é'):
            registrar_oficial(s,item('18:00',10,60,40),
                              datetime.now(timezone.utc))

    def test_registra_sem_duplicar_geracao(self):
        s=snap([])
        registrar_oficial(s,item('18:00',10,60,40),
                          datetime(2026,10,25,tzinfo=timezone.utc))
        registrar_oficial(s,item('18:00',10,60,40),
                          datetime(2026,10,25,tzinfo=timezone.utc))
        self.assertEqual(len(s['historico_br']),1)
        registrar_oficial(s,item('18:15',50,260,240),
                          datetime(2026,10,25,tzinfo=timezone.utc))
        self.assertEqual(len(s['historico_br']),2)


if __name__=='__main__':
    unittest.main()
