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
