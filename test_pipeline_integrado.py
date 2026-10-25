"""Ensaio de ponta a ponta sem rede: EA16 -> EA20 -> backup -> motor."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from coletor_zonal import coletar
from backup_actions import recuperar
from motor_zonal_completo import executar


class FakeResponse:
    def __init__(self, payload):
        self.payload=payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload
    @property
    def content(self):
        return self.payload


class FakeSession:
    def __init__(self, artifacts, backups):
        self.artifacts=artifacts
        self.backups=backups
    def get(self, url, **kwargs):
        if url.endswith('/actions/artifacts'):
            return FakeResponse({'artifacts':self.artifacts})
        numero=int(url.rsplit('/',2)[-2])
        return FakeResponse(self.backups[numero])


def compactado(dados):
    bruto=json.dumps(dados,ensure_ascii=False).encode('utf-8')
    memoria=io.BytesIO()
    with zipfile.ZipFile(memoria,'w') as z:
        z.writestr('dados_zonais_6258.json',bruto)
        z.writestr('snapshot.sha256',hashlib.sha256(bruto).hexdigest()+'\n')
    return memoria.getvalue()


class TestPipelineIntegrado(unittest.TestCase):
    def test_coleta_retomada_backup_parcial_e_projecao_final(self):
        z1=('SP','71072','0001')
        z2=('SP','71072','0002')
        catalogo={
            k:{'uf':k[0],'municipio':k[1],'zona':k[2],
               'secoes_cadastradas_ea16':1}
            for k in (z1,z2)}
        hist={
            z1:{(2022,2):{'lula':60,'direita':40,'validos':100},
                (2026,1):{'lula':70,'direita':30,'validos':100}},
            z2:{(2022,2):{'lula':30,'direita':70,'validos':100},
                (2026,1):{'lula':40,'direita':60,'validos':100}}}
        tempo=1800000000.
        contagem=[]
        def buscar(uf,mun,zona):
            chave=(uf,mun,zona)
            contagem.append(chave)
            l=55 if chave==z1 else 65
            return ({'uf':uf,'municipio':mun,'zona':zona,
                     'lula':l,'flavio':100-l,'validos':100,
                     'secoes':1,'secoes_total':1,
                     'geracao':'25/10/2026 18:00:00',
                     'fase':'o','turno':'2'},None)
        def coletar_teste(destino,limite):
            with patch('coletor_zonal.consultar_config',
                       return_value={'pleito_2turno_confirmado':True}), \
                 patch('coletor_zonal.baixar_catalogo',
                       return_value=catalogo):
                return coletar(destino,uf='SP',limite=limite,
                              coletar_zona=buscar,permitir_antes=True,
                              concorrencia=1,clock=lambda:tempo,
                              sleep=lambda x:None)
        with tempfile.TemporaryDirectory() as pasta:
            p=Path(pasta)/'snap.json'
            primeiro=coletar_teste(p,1)
            self.assertEqual(primeiro['atualizadas'],1)
            s1=json.loads(p.read_text('utf-8'))
            segundo=coletar_teste(p,2)
            self.assertEqual(segundo['atualizadas'],1)
            s2=json.loads(p.read_text('utf-8'))
            self.assertEqual(len(s2['observacoes']),2)
            terceiro=coletar_teste(p,2)
            self.assertEqual(terceiro['requisicoes'],0)
            self.assertEqual(len(contagem),2)
            # Simular perda do cache recente (apenas segunda zona no
            # backup novo). A recuperação deve reunir ambos os arquivos.
            s2['observacoes']={'SP|71072|0002':s2['observacoes']['SP|71072|0002']}
            artefatos=[
                {'id':2,'name':'snapshot-zonal-6258','expired':False,
                 'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':2}},
                {'id':1,'name':'snapshot-zonal-6258','expired':False,
                 'workflow_run':{'head_branch':'fix/auditoria-pre-segundo-turno','id':1}}]
            sessao=FakeSession(artefatos,{2:compactado(s2),1:compactado(s1)})
            p.unlink()
            restaurado=recuperar(p,token='fake',sess=sessao,
                branch='fix/auditoria-pre-segundo-turno')
            self.assertEqual(restaurado['artifacts_mesclados'],2)
            snap=json.loads(p.read_text('utf-8'))
            self.assertEqual(len(snap['observacoes']),2)
            resultado=executar(snap,hist,agora=tempo,
                               exigir_catalogo_nacional=False)
            br=resultado['brasil']
            self.assertTrue(br['apuracao_integral_zonas'])
            self.assertEqual(br['zonas_concluidas'],2)
            self.assertEqual(br['lula_apurado'],120)
            self.assertEqual(br['flavio_apurado'],80)
            self.assertAlmostEqual(br['lula_estimado'],120)
            self.assertAlmostEqual(br['flavio_estimado'],80)
            self.assertEqual(sum(x['lula_estimado'] for x in
                                 resultado['ufs'].values()),120)


if __name__=='__main__':
    unittest.main()
