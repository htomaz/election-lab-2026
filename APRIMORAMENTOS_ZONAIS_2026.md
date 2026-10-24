# Melhorias de estimação eleitoral zonal — 24/10/2026

**Ramo:** `fix/auditoria-pre-segundo-turno`. Alterações NÃO publicadas
na `main`; não há dados reais de 2026T2 antes de 25/10 às 17h BRT.

## 1. Teste separado para votos válidos, presença e inválidos

`backtest_participacao.py` prevê **2022T2** usando apenas 2022T1 como
referência prévia, os eleitores aptos do cadastro do alvo e as zonas
2022T2 já artificialmente reveladas. Não usa os votos de zonas futuras.

Compara:

- `historico`: histórico local de comparecimento e validade sem ajustes;
- `ajuste_uf`: corrige taxas com sinais apenas das zonas
  já reveladas da mesma UF, com limites e shrinkage;
- `hierarquico`: mistura 75% do sinal UF e 25% do sinal Brasil,
  sempre sem incorporar zonas ainda ocultas.

Cenários: quatro permutações aleatórias, maior/menor abstenção histórica,
menor taxa de válidos, maiores eleitorados primeiro. Essas ordens usam
apenas informação histórica ou cadastral, não os resultados futuros.
Estágios: 5%, 10%, 20%, 30%, 50%, 70%, 90%, 100% das zonas.
Variáveis de erro: comparecimento, válidos, brancos e nulos, além da
média do erro absoluto por UF. **Zonas inteiras** são reveladas; não
há histórico intrazona por seção e a simulação não reproduz a fila real
de divulgação.

`calibrar_participacao.py` testa intensidades
`0;0.15;0.30;0.50;0.75;1` em dois grupos de UFs:
um grupo escolhe pela média de erro em UFs de treino e o outro
mede o erro em UFs excluídas. Troca os grupos e repete.
**Importante:** essa validação é espacial, mas feita retrospectivamente
na MESMA eleição de 2022; não demonstra calibração temporal
independente nem valida eficácia específica para 2026.
Nenhum parâmetro de produção é alterado automaticamente pelo
vencedor do teste.

Artefatos de CI incluem
`backtest_participacao.csv`, `resumo_participacao.csv`,
`calibracao_ufs.csv`, `resumo_calibracao.csv`.

## 2. Desenviesamento da ordem de apuração

A correção estadual compara os votos efetivamente recebidos
com a preferência **histórica da própria zona observada**, evitando
comparar diretamente uma parcial enviesada com a média da UF.
A nova heurística reduz o peso informativo de uma zona parcial
por `sqrt(seções_totalizadas/seções_total)`, diminuindo
o impacto de uma zona que ainda não terminou. Um componente
municipal limitado a 25% complementa o estadual quando há
dados locais, com shrinkage próprio por volume esperado.

O painel apresenta o perfil histórico das zonas já observadas,
o perfil histórico agregado de todas as zonas da UF e a
diferença entre eles. Esses números **não** são resultados nem
diferenças de votos efetivamente apurados.

O parâmetro de intensidade da correção continua limitado e
exploratório; os pesos precisam de avaliação prospectiva.

## 3. Incerteza: cenários, NÃO probabilidades

`sensibilidade_zonal.py` calcula nove combinações de três níveis de
comparecimento e três de preferência eleitoral nos votos restantes.
Os votos já apurados permanecem intocados. A simulação
de comparecimento só altera zonas com históricos de aptos/válidos
completos; zonas com dados incompletos mantêm o volume original e
são explicitamente contadas como não cobertas.

O painel nacional e de UF mostra a amplitude dos resultados em
**faixas de estresse**, e nunca as rotula como intervalo de confiança,
probabilidade de vitória ou margem de erro calibrada.

## 4. Integração TSE / salvaguardas

Foi corrigido o rótulo de origem do painel: o universo oficial de
zonas usa EA16 pleito 3221, enquanto EA12 é usado para nomes e
EA20 eleição 6258 para votos/seções. Uma string de origem dentro
de um arquivo enviado **não autentica a integridade** desse arquivo;
a validação de proveniência do snapshot real continua obrigatória.

O coletor continua sob demanda, com limites de requisição e
armazenamento incremental; a persistência no Streamlit Cloud e a
sincronização de snapshots nacionais ainda necessitam homologação.

## 5. Critério para liberar o novo modelo

- Toda a suíte de testes, backtests e conciliações deve passar no CI.
- Os resumos devem declarar se o ganho em votos válidos é consistente
  em cenários extremos e nos grupos de UFs não utilizados na escolha.
- Não impor parâmetros retrospectivamente otimizados a 2026T2
  sem comprovar generalização para outro pleito.
- Incluir resultados reais oficiais de 2026T2, checar latência,
  completude do EA16, ausência de dupla contagem,
  desigualdades com EA20 BR/UF por geração, e confirmar
  interface no Streamlit antes do merge.
