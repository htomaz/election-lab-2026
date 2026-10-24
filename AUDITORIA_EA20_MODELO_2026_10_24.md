# Auditoria independente do Election Lab — 24/10/2026

**Escopo:** código experimental na branch `fix/auditoria-pre-segundo-turno`,
PR #1. Nenhum merge na `main` e nenhuma atualização automática do
Streamlit de produção.

**Referência normativa:** TSE, *EA20 — Arquivo de resultado unificado*,
versão 13/10/2026, especialmente elementos `s`, `e` e `v`,
https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados/tse-ea20-arquivo-de-resultado-unificado

## Verificações concluídas

1. A identificação de `v.tvn` já estava correta. O EA20 usa
   `tvn=vn+vnt` como **total de votos nulos**, inclusive técnicos.
   A auditoria não alterou esse campo.
2. **Erro encontrado e corrigido:** em seções não instaladas, `e.est`
   inclui o eleitorado não instalado (`e.esni`). Dividir o comparecimento
   `e.c` por `e.est` subestimava a taxa. O denominador de participação
   observado foi alterado para `e.esi` (eleitorado de seções instaladas),
   mantendo `e.est` para retirar do universo restante o eleitorado
   das seções totalizadas. A alteração vale tanto para a zona quanto
   para a atualização conservadora das taxas agregadas por UF.
   Quando não houver `e.esi` e houver `e.esni>0`, a atualização da taxa
   é omitida e mantém-se o histórico. Dados de não instalação e
   não apuração foram propagados ao motor.
3. **Erro de integração corrigido:** o normalizador não verificava
   explicitamente eleição, turno, fase e abrangência. A coleta ao vivo
   exige `ele=6258`, `t=2`, `f=o`,
   `tpabr` correspondente ao arquivo (BR/UF/zona), código de
   abrangência, data/hora de geração válida e blocos obrigatórios de
   votos/seções. Arquivos simulados e do primeiro turno são rejeitados,
   inclusive quando esses marcadores aparecem em JSON importado.
   O upload manual CONTINUA sem autenticação criptográfica JWS.
4. **Erro de integridade corrigido:** valores de votos malformados
   não são mais silenciosamente truncados/convertidos a zero.
   E a divergência de um voto entre a soma dos candidatos e `v.vv`
   não é tolerada (contagem é inteira).
5. **Risco operacional corrigido:** duas execuções do coletor em
   runners separados do GitHub Actions eram capazes de restaurar
   o mesmo cache desatualizado. O workflow manual passou a
   serializar execuções, mantendo o bloqueio por arquivo no PC/Streamlit.
6. **Rotulagem corrigida:** arquivo JSON enviado manualmente que
   declara EA16/EA20 não é chamado de autenticado/oficial apenas
   com base em texto dentro do próprio JSON.

## Testes novos

- Eleitorado de seções instaladas (100) e totalizadas (120) com 20
  eleitores de seções não instaladas: os 20 não entram na base de
  comparecimento nem são automaticamente tratados como abstenções.
- Coincidência da contagem oficial após a totalização de todas as
  seções, inclusive seções não instaladas.
- Atualização de turnout por UF com denominador correto.
- Rejeição de simulado, arquivo de 1º turno, código de zona divergente,
  ausência de identidade, números malformados, horário de geração
  inválido e discrepância de um voto.
- Bloqueio de snapshots marcados com fase simulada/turno errado.

## Não alterado

- Percentual histórico Lula/Flávio, pesos e intensidade heurística.
  Não há nova evidência de calibração temporal independente que
  justifique mudar esses hiperparâmetros.
- Lógica de votos já apurados como parcela fixa e projeção
  apenas dos votos ainda não observados.
- Cenários de estresse continuam SEM significado de
  intervalo de confiança ou probabilidade de vitória.
- Identificação de `v.tvn` como total de nulos, já correta.

## Riscos e pendências

- Nenhum EA20 **real de 2026T2** estava totalizado na data da auditoria;
  os ensaios usam cenários sintéticos, arquivos oficiais antigos,
  cadastros EA16 publicados e a documentação técnica de 2026.
- Sem autenticação criptográfica JWS do TSE dos uploads manuais.
  A origem do arquivo precisa continuar explicitamente auditada.
- A diferença entre seções totalizadas, instaladas e apuradas
  pode incluir seções não instaladas, anuladas e marcadas não apuradas;
  é obrigatório revalidar contas e campos na primeira parcial real.
- Os parâmetros de preferência dos eleitores marginais e da
  propagação de swing UF/município continuam exploratórios:
  backtest espacial de 2022 não valida generalização em 2026.
- GitHub Actions preserva snapshots por cache/artefato, sem
  armazenamento transacional persistente compartilhado.
- Não promover para a branch principal antes da homologação
  com EA20 oficial e autorização explícita.

**Critério de aceite:** suite automatizada verde no último commit
da PR e confronto EA20 real 6258 após início da totalização.
