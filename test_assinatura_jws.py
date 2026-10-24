"""Assinatura matemática JWS Ed25519 com chave independente; offline."""
import base64
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from assinatura_jws import verificar_jws,comparar_assinado_zona
from test_auditoria_ea20_2026 import payload_ea20
from tse import normalizar_ea20


def b64(x):
    if isinstance(x,dict):
        x=json.dumps(x,separators=(',',':'),ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(x).decode().rstrip('=')


class TestAssinaturaJWS(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.public=b64(self.key.public_key().public_bytes(
            Encoding.Raw,PublicFormat.Raw))
        self.payload=payload_ea20()

    def assinar(self,header=None,payload=None):
        h=b64(header or {'alg':'EdDSA'})
        p=b64(payload if payload is not None else self.payload)
        msg=(h+'.'+p).encode()
        return '.'.join((h,p,b64(self.key.sign(msg))))

    def test_compact_assinado_verifica_com_chave_fora_do_jws(self):
        token=self.assinar()
        self.assertEqual(verificar_jws(token,self.public)['ele'],'6258')

    def test_assinatura_json_flattened(self):
        h,p,s=self.assinar().split('.')
        flat=json.dumps({'protected':h,'payload':p,'signature':s})
        self.assertEqual(verificar_jws(flat,self.public)['ele'],'6258')

    def test_rejeita_voto_manipulado_ou_chave_errada(self):
        h,p,s=self.assinar().split('.')
        alterado=self.payload.copy()
        alterado['v']={'vv':'200'}
        with self.assertRaisesRegex(ValueError,'Assinatura'):
            verificar_jws('.'.join((h,b64(alterado),s)),self.public)
        outro=Ed25519PrivateKey.generate().public_key().public_bytes(
            Encoding.Raw,PublicFormat.Raw)
        with self.assertRaisesRegex(ValueError,'Assinatura'):
            verificar_jws('.'.join((h,p,s)),b64(outro))

    def test_rejeita_chave_injetada_no_cabecalho(self):
        token=self.assinar({'alg':'EdDSA','jwk':{'kty':'OKP'}})
        with self.assertRaisesRegex(ValueError,'embutido'):
            verificar_jws(token,self.public)

    def test_rejeita_algoritmo_none(self):
        token=self.assinar({'alg':'none'})
        with self.assertRaisesRegex(ValueError,'EdDSA'):
            verificar_jws(token,self.public)

    def test_confere_assinatura_e_votos_da_zona(self):
        dados=normalizar_ea20(self.payload,'SP')
        r=comparar_assinado_zona(self.assinar(),self.public,
                                'SP','71072','0001',dados)
        self.assertTrue(r['assinatura_valida'])
        dados['lula']+=1
        with self.assertRaisesRegex(ValueError,'snapshot'):
            comparar_assinado_zona(self.assinar(),self.public,
                                 'SP','71072','0001',dados)


if __name__=='__main__':
    unittest.main()
