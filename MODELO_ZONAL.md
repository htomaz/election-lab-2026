# Modelo nacional a partir de todas as zonas — Election Lab 2026

**Estado:** versão experimental na branch de auditoria. Não mesclar na `main`
antes de validar o 2º turno federal 6258 no dia 25/10/2026.

## O que foi desenvolvido

1. `motor_zonal_completo.py`: reconstrói **cada município/zona** do
   catálogo eleitoral, combina histórico 2026T1/2022T2 e a parcial da zona.
   Votos já observados são imutáveis. Somente os votos remanescentes são
   estimados. Retorna linhas zonais e agregações por município, UF e Brasil.
2. `coletor_zonal.py`: busca catálogos oficiais EA16 do pleito 3221 (municípios, zonas e seções);
   monta URLs EA20 válidas apenas para municípios/zonas do catálogo;
   consulta com limite padrão de **12 requisições/segundo**, 8 workers;
   interrompe a rodada em caso de 403, 404 ou 429 e persiste o snapshot
   incremental de forma atômica.
3. `painel_zonal_completo.py`: nova aba **Zonas**, com prévia *somente
   histórica* antes da eleição, upload de snapshot ou leitura de
   `dados_zonais_6258.json`, resultados por município/zona, e CSVs
   para análise. Permite coleta manual de até 100 zonas da UF selecionada
   após o início da apuração.
4. Testes `test_motor_zonal_completo.py` e `test_coletor_zonal.py`.
   Incluem um teste de reconstrução do resultado nacional conhecido do
   1º turno de 2026, simulando 100% das zonas contabilizadas. O teste
   NÃO antecipa o segundo turno.

## Participação, abstenção, brancos e nulos (revisão de 24/10)

O modelo deixa de utilizar apenas o volume histórico de votos válidos
nas zonas em que o histórico de participação e a apuração EA20 detalhada
estão completos. A base `historico_participacao_zonas.csv` contém
12.575 registros por município/zona e eleição: 6.283 do 2º turno de 2022
e 6.292 do 1º turno de 2026. A origem é
`detalhe_votacao_munzona_{ano}.zip`, do TSE, cargo Presidente.
Registros duplicados **somente são deduplicados quando idênticos**;
divergências interrompem a importação. `validar_participacao.py`
reconcilia os votos válidos com `historico_zonas.csv` zona a zona.

### Três fases, calculadas separadamente

```
Eleitores aptos para 2º turno na zona (EA20 e.te, se disponível)
  menos eleitores de seções já totalizadas (EA20 e.est)
= Eleitores ainda não processados

Eleitores ainda não processados
  × taxa estimada de comparecimento
= Comparecimentos restantes estimados

Comparecimentos restantes estimados
  × taxa estimada de votos válidos entre presentes
= Votos válidos restantes estimados

Votos apurados oficialmente (EA20 v.vv)
  + votos válidos restantes estimados
= Votos válidos finais da zona
```

O EA20 contém ainda `e.c` (comparecimento), `e.a` (abstenção),
`v.vb` (votos brancos), `v.tvn` (nulos, incluindo técnicos) e
`v.tv` (votos totais). Os dados da parcial **não** são redistribuídos
nem somados duas vezes; a previsão é aplicada ao eleitorado ainda
não processado. Uma zona concluída mantém os valores oficiais sem
acréscimo de votos, brancos ou nulos.

A taxa de comparecimento histórica pondera 2026T1 (75%) e 2022T2
(25%), mas poderá divergir no segundo turno. O código incorpora
de maneira conservadora um eventual desvio encontrado nas seções
apuradas: ajuste máximo por iteração de 12 p.p. no sinal bruto de
comparecimento e 8 p.p. no sinal bruto de validade, multiplicado
por um coeficiente de confiança que cresce com o eleitorado
processado, até a intensidade configurada (0,35 por padrão).
Esses limites são *heurísticos*, não resultados de calibração
estatística independente.

Votos brancos e nulos são modelados como frações **dos presentes**,
não dos aptos nem dos válidos. Outros tipos de votos inválidos
são conciliados como categoria residual; o modelo não força
votos inválidos a se tornarem votos dos candidatos.

Quando não há histórico de participação ou faltam campos EA20 de
eleitorado processado, a zona mantém o modelo antigo de volume,
com `modelo_volume=validos_historicos`. A interface explicita a
cobertura do novo método em vez de apresentar somas incompletas
de abstenção e votos inválidos como se fossem totais do Brasil.

### Preferência eleitoral dos eleitores marginais

Um comparecimento maior aumenta o volume potencial de votos válidos,
mas **não revela quem recebeu esses votos**. A função
`cenarios_eleitores_marginais` permite testar diferentes preferências
entre os novos comparecentes sem inferir seu candidato automaticamente
pela taxa de abstenção da zona. Os cenários não são previsões oficiais.

O TSE relata peculiaridades de cadastro, incluindo registros
duplicados por transferências temporárias; por isso a soma de
`QT_APTOS` dos registros da base não necessariamente corresponde ao
eleitorado efetivo nacional após todos os ajustes. Em tempo real,
a preferência é dada ao eleitorado `e.te` do pleito-alvo.

### Reprodução

```bash
python validar_participacao.py
python -m unittest discover -p 'test_*.py' -v
```

Para reconstruir a base de fontes públicas a partir dos ZIPs originais:

```bash
python obter_participacao_tse.py --ano 2022
python obter_participacao_tse.py --ano 2026
```

## Fluxo operacional

O coletor deve ser executado **apenas após 25/10/2026, às 17h BRT**.
Antes desse horário, a nova aba contém apenas prévia explicitamente
rotulada como histórica. Os arquivos fictícios do modo demonstração
não são confundidos com dados do TSE.

Preparação:

```bash
pip install -r requirements.txt
python -m unittest discover -p 'test_*.py' -v
python teste_catalogo_zonas_tse.py
```

Para consultar uma UF por lote (recomendada a primeira homologação):

```bash
python coletor_zonal.py --uf SP --limite 300
```

Para consultar **todas** as zonas registradas no EA16 (até 10.000
requisições, mas nunca mais do que o número de zonas no catálogo):

```bash
python coletor_zonal.py --todas --limite 10000 --taxa 12 --concorrencia 8
```

Uma nova execução reaproveita as zonas do snapshot anterior e atualiza
primeiro as que ainda não foram consultadas ou estão há mais tempo sem
consulta. Em caso de erro HTTP bloqueante, o programa encerra
novas requisições e preserva os dados já salvos.

O arquivo `dados_zonais_6258.json` é o registro operacional a ser lido
pelo Streamlit, localmente ou enviado pelo operador na aba **Zonas**.
Não contém credenciais. **Esse arquivo não é persistido automaticamente
entre reinícios do Streamlit Community Cloud**, e o upload pela interface
não garante atualização automática contínua. Um serviço de coleta
persistente deverá ser integrado para operação 24/7.

## Segurança e limites da interpretação

- O cadastro completo de 2026T2 deve vir do **EA16 do pleito 3221**, com um arquivo por UF. EA12 é utilizado para nomear municípios, não para enumerar zonas.
  A listagem do primeiro turno não prova as zonas do segundo.
- O motor identifica observações coletadas há mais de 15 minutos e as
  rotula como **desatualizadas**. Os votos oficiais anteriormente
  registrados permanecem como piso observado; não são apagados por
  falta de uma coleta recente. Apenas a métrica de cobertura recente
  deixa de contá-los como atualizados.
- **Cobertura de consultas** não é igual a **percentual de seções
  apuradas**. O primeiro mede zonas consultadas; o segundo depende do
  total de seções eleitorais.
- Somas de snapshots zonais capturados em horários diferentes **não
  equivalem** à totalização BR do TSE. Validar conciliação temporal antes
  de divulgar diferenças.
- O peso histórico é 75% para o confronto bilateral do 1º turno
  de 2026 e 25% para 2022. O voto de terceiros no 1º turno de 2026
  é parte do volume válido, não deve ser apresentado como voto
  de Flávio.
- O módulo faz **estimativas exploratórias**, não intervalos de
  confiança nem probabilidades de vitória validadas.
- O número de seções totalizadas só é conhecido para zonas com EA20
  consultado. Uma zona não consultada não é interpretada como
  tendo 0 seções no cadastro.
- Mantenha `main` intacta até concluir a homologação técnica,
  incluindo URLs reais 6258/3221, erros de coleta, snapshots temporais,
  reconciliação e teste visual no Streamlit.

## Próxima etapa necessária

Validação com parciais **reais do segundo turno** e avaliação de
tempo de coleta, cobertura efetiva do catálogo EA16, consistência
com os totais oficiais estaduais, comportamento quando uma zona
regride ou quando o TSE fornece revisão de votos, e implantação
de serviço de coleta persistente caso o usuário deseje cobertura
nacional automática de baixa latência.

Documentação oficial:
https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados
