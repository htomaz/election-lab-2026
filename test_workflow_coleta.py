"""Contrato de validacao do workflow agendado na branch principal."""
import ast
import re
import unittest
from pathlib import Path


class TestWorkflowColeta(unittest.TestCase):
    def setUp(self):
        self.yaml=Path('.github/workflows/coleta_zonal.yml').read_text('utf-8')

    def test_agendamento_e_seguranca(self):
        w=self.yaml
        self.assertIn("schedule:",w)
        self.assertIn("*/15 20-23 25 10 *",w)
        self.assertIn("*/15 0-2 26 10 *",w)
        self.assertIn("date(2026,10,25)",w)
        self.assertIn("time(17,0)",w)
        self.assertIn("cancel-in-progress: false",w)
        self.assertIn("needs: janela",w)
        self.assertIn("permissions:\n  contents: read\n  actions: read",w)
        self.assertIn("Coletar EA16 e EA20 oficiais",w)
        self.assertIn("Conciliar zonas coletadas com EA20 oficial",w)
        self.assertIn("snapshot.sha256",w)
        self.assertIn("retention-days: 30",w)
        self.assertNotIn("pull_request:",w)

    def test_script_da_janela_compila(self):
        match=re.search(
            r"- name: Validar janela do segundo turno.*?run: \\|\\n"
            r"(?P<body>.*?)\\n  coleta:",self.yaml,re.S)
        self.assertIsNotNone(match)
        lines=match.group('body').splitlines()
        self.assertTrue(lines[0].strip().startswith("python - <<"))
        self.assertEqual(lines[-1].strip(),'PY')
        source='\\n'.join(row[10:] if row.startswith(' '*10) else row
                           for row in lines[1:-1])
        ast.parse(source)

    def test_evento_agendado_define_escopo_e_limite(self):
        self.assertEqual(self.yaml.count("ESCOPO: "),2)
        self.assertEqual(self.yaml.count("LIMITE: "),2)
        self.assertEqual(self.yaml.count("inputs.escopo"),2)
        self.assertEqual(self.yaml.count("inputs.limite"),2)


if __name__=='__main__':
    unittest.main()
