# Avaliação retrospectiva dos aprimoramentos zonais — 24/10/2026

## Fonte e alvo da avaliação

- Treino histórico: participação eleitoral municipal/zonal do **1º turno de 2022**.
- Alvo ocultado progressivamente: comparecimento, válidos, brancos e nulos do
  **2º turno de 2022**.
- O cadastro de aptos do alvo 2022T2 é tratado como um dado
  pré-eleitoral (não como voto observado).
- O código só utiliza resultados do 2022T2 das zonas artificialmente
  **reveladas** para atualizar o sinal UF e Brasil. Não consulta votos
  de zonas ocultadas; há teste automatizado dessa propriedade.
- 6.283 zonas no alvo, oito ordens de revelação, oito níveis de
  cobertura (5 a 100% das zonas) e 13 configurações/variações
  agrupadas em três famílias de modelo. São **3.328 linhas de
  diagnóstico** contando separadamente quatro variáveis.
- Causas de incerteza NÃO cobertas: chegada intrazona por seção,
  alterações cadastrais ainda não divulgadas, transferência efetiva
  de votos e mudança comportamental específica de 2026.

## Seleção de hiperparâmetros fora do conjunto de avaliação por UF

Divisão determinística das 28 localidades (inclui ZZ) em dois blocos de
14. Em cada rodada, intensidades são escolhidas apenas comparando
os erros dos estados de **treino**. O erro reportado é avaliado
nos estados do bloco de **teste**; os blocos são invertidos na
segunda rodada. A variável de escolha é o erro absoluto de votos
válidos, medido por UF e estágio. Não escolhe pesos na mesma
UF em que reporta erro.

Resultado da execução GitHub Actions
[run #207](https://github.com/htomaz/election-lab-2026/actions/runs/40059226803):

| Família de modelo | Erro absoluto percentual médio por UF | Erro absoluto médio de votos válidos por UF | UFs no conjunto de teste |
|---|---:|---:|---:|
| Histórico sem correção | 1,2394% | 27.880,40 | 28 |
| Correção hierárquica UF + Brasil | 0,8431% | 15.067,54 | 28 |
| Correção por UF | **0,7452%** | **13.068,74** | 28 |

Redução relativa de aproximadamente **39,9%** no erro percentual
médio por UF para a correção UF contra histórico sem correção
(`1 - 0,7452 / 1,2394`).

No ajuste *in-sample* (SEM divisão geográfica), a combinação
`ajuste_uf`, intensidade `0.75` atingiu erro absoluto nacional
médio de **0,09039 milhão de votos válidos** entre etapas
incompletas, com erro máximo de 0,46749 milhão nos cenários
examinados. **Esse parâmetro não foi promovido automaticamente**
à previsão de 2026: valor escolhido no mesmo conjunto de
2022 é sujeito a sobreajuste.

### Limitação da expressão "fora da amostra"

A separação das UFs testa generalização **espacial** na eleição
de 2022, mas não generalização **temporal** para outro pleito.
São cenários de zonas concluídas artificialmente, sem histórico
da chegada temporal das seções. Os números representam erro de
votos válidos **por UF**, não erro em pontos percentuais do
candidato nem confiabilidade de eleição antecipada.

## Desenviesamento territorial

O sinal de preferência usado no motor de zonas é um residual
`participação_Lula_observada_zona - participação_Lula_histórica_zona`,
atenuado por `sqrt(seções_apuradas/seções_total)`. As zonas
observadas podem ter perfil histórico muito diferente do total
da UF; por isso a UI mostra a diferença explicitamente.
A camada municipal é submetida a shrinkage e participa com
no máximo 25% do desvio aplicado para os votos restantes.
Não há expectativa demonstrada de melhora preditiva desse
peso municipal específico; os resultados de comparação
de preferências no 2026T1 são pseudo-backtests e não
homologam o 2026T2.

## Cenários de estresse

`sensibilidade_zonal.py` calcula nove combinações dos
choques informados pelo usuário para comparecimento
restante e participação de Lula entre votos restantes.
O resultado brasileiro e por UF mostra mínimo e máximo
nessa grade de cenários e quantas zonas não permitem
choques de comparecimento. As faixas **não são
intervalos de confiança, probabilidades de vitória ou
margens de erro calibradas**.

## Liberação

A nova coleta de 2026T2 deve ser verificada com EA16 (pleito
3221) e EA20 (eleição 6258) oficiais e snapshots com horários
identificáveis após 25/10/2026 17h BRT. A `main` permanece
intacta; o projeto precisa de validação em produção e
serviço persistente para baixa latência nacional.
