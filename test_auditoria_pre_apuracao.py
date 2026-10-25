"""EA11/EA16/EA20 pré-apuração: teste offline de conciliação e divergência."""
import unittest
from auditoria_pre_apuracao import comparar_catalogo
from tse import UFS


def amostra():
    catalogo={(uf,'00001','0001'):{
        'uf':uf,'municipio':'00001','zona':'0001',
        'secoes_cadastradas_ea16':2} for uf in UFS}
    hist={k:{(2026,1):{'validos':123}} for k in catalogo}
    oficiais={uf:{'secoes_total':2,'secoes':0,'validos':0,
                   'aptos':123,'geracao':'24/10/2026 19:19:13'}
              for uf in UFS}
    oficiais['BR']={'secoes_total':2*len(UFS),
                   'secoes':0,'validos':0,'aptos':123*len(UFS),
                   'geracao':'24/10/2026 19:19:13'}
    return catalogo,oficiais,hist


class TestAuditoriaPreApuracao(unittest.TestCase):
    def test_conciliacao_previa_deterministica(self):
        c,o,h=amostra()
        # 28 zonas do teste não passam na faixa nacional de produção.
        r=comparar_catalogo(c,o,h)
        self.assertIn('fora da faixa',repr(r['divergencias']))
        self.assertEqual(r['secoes_ea20_br'],56)
        self.assertEqual(r['eleitorado_ea20_ufs'],3444)

    def test_detecta_secoes_uf_divergentes(self):
        c,o,h=amostra()
        o['SP']['secoes_total']=3
        r=comparar_catalogo(c,o,h)
        self.assertIn('SP: EA16 possui 2 seções, EA20 informa 3',
                      r['divergencias'])
        self.assertEqual(r['status'],'divergente_ou_incompleto')

    def test_detecta_eleitorado_nacional_desalinhado(self):
        c,o,h=amostra()
        o['BR']['aptos']+=1
        r=comparar_catalogo(c,o,h)
        self.assertTrue(any('eleitores != soma UF' in e for e in r['divergencias']))

    def test_rejeita_dados_de_apuracao_antes_do_horario(self):
        c,o,h=amostra()
        o['SP'].update({'validos':2,'secoes':1})
        r=comparar_catalogo(c,o,h)
        self.assertTrue(any('pré-apuração não aplicável' in e for e in r['divergencias']))

    def test_nao_marca_falta_de_uf_como_reconciliado(self):
        c,o,h=amostra()
        del o['ZZ']
        r=comparar_catalogo(c,o,h)
        self.assertEqual(r['status'],'divergente_ou_incompleto')
        self.assertTrue(any('EA20 indisponível' in e for e in r['divergencias']))


if __name__=='__main__':
    unittest.main()
