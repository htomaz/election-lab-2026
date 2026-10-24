# Checklist de preparação para 25/10/2026 — Election Lab

**Estado:** branch `fix/auditoria-pre-segundo-turno`, PR #1.
**PROIBIDO promover à `main` ou declarar produção homologada sem aprovação
expressa do responsável.** Apuração oficial começa em 25/10/2026,
às 17h de Brasília.

## Concluído no código (validação por CI, não por apuração 2026T2)

- Núcleo de projeção por município/zona e agregação por município, UF, BR.
- Histórico de 18.858 registros de participação (2022T1, 2022T2, 2026T1),
  cruzamento com 2026T1 candidatos e testes de consistência.
- Comparecimento, abstenção, votos válidos, brancos e nulos separados;
  fatores agregados estaduais e atualização limitada por parcial municipal.
- Desenviesamento de zonas observadas versus histórico, redução de
  intensidade quando poucas seções apuradas.
- Nove cenários de estresse por UF e Brasil. Não são intervalos de confiança.
- Pseudo-backtest territorial e backtest de participação 2022T1→2022T2.
  Correção estadual melhorou MAE percentual médio de válidos por UF
  de 1,2394% para 0,7452% em holdout espacial, NÃO temporal.
- Coletor EA16/EA20 com limite de consultas, timestamp, cache de
  catálogos, escopo por UF, reconsultas após expiração, escrita atômica,
  checkpoint a cada 100 atualizações/20 segundos e lock de escrita
  Linux/Windows. Interrompe em 403, 404, 429 ou pleito EA11 não confirmado.
- Evita descartar outros estados em coletas incrementais de uma UF.
- Recusa troca de catálogo EA16 que perca zonas já apuradas e bloqueia
  catálogo nacional com menos de 95% do universo zonal 2026T1.
- Auditoria BR/UF manual com horários de geração e suspensão das
  projeções quando há contradição relevante; o snapshot é versionado
  por hash e não é confundido com votos oficiais autenticados.
- Histórico nacional SQLite com exportação/restauração CSV explícita
  e preservação da projeção original em reconsultas sem estimativa.
- Streamlit tem aba de zonas, download de detalhamento, alerta
  para catálogo incompleto e distinção entre histórico, amostra UF e BR.
- CI tem simulação do motor sobre 6.292 zonas em 0/5/25/50/100%,
  inspeção de latência/memória e simulação de 6.292 consultas sem rede
  com interrupção/retomada e validação dos snapshots.
- GitHub Actions possui workflow de coleta **manual**, download de
  artefato e cache recuperável entre execuções. O cache é melhor
  esforço e NÃO equivale a banco persistente durável.

## Ações e verificações ANTES do horário oficial

1. Conferir `python preflight_tse.py` e observar se o EA11 oficial
   publicou pleito 3221/eleição 6258. A vinculação 6257→6258
   pode aparecer antes, mas não comprova que o 3221 está ativo.
2. Rodar `python preflight_catalogo_todas_ufs.py` para inspecionar
   o EA16 do 1º turno, inclusive ZZ, e `python teste_catalogo_zonas_tse.py`.
   Isso **não** garante que a configuração EA16 do segundo turno já exista.
3. Reexecutar GitHub Actions da branch e exigir pipeline verde completo;
   não considerar erro de teste UI como sucesso de homologação.
4. Conferir que os 6.292 registros históricos têm correspondência
   nas entradas de votação/participação (`python validar_participacao.py`).
5. Fazer `python simulacao_operacional.py` e
   `python simulacao_coletor.py` sem acessar votos do 2026T2.
6. Verificar layout visual da aba Zonas em navegador real no computador
   e telefone; smoke-test automático não substitui essa conferência.

## Após 17h de 25/10: obrigatoriamente pendente

1. EA11 deve confirmar pleito 3221, eleição federal 6258 e cargo
   Presidente antes de baixar EA16/EA20 zonais.
2. Confirmar que EA16 3221 lista 28 localidades e cobre o universo;
   comparar seções e códigos municipais (5 dígitos) e zonais (4).
3. Coletar pequena amostra por UF e conferir `e.te`, `e.est`,
   `e.c`, `e.a`, `v.vv`, `v.vb`, `v.tvn`, `v.tv`
   em parciais reais. Não confundir votos totais com válidos.
4. Auditar cada UF com `auditar_parciais`; sincronizar/identificar
   gerações e confrontar BR com todas as UFs **somente quando as
   gerações oficiais forem comparáveis**.
5. Verificar que votos já apurados não são subtraídos, previsões
   convergem quando seções estão 100%, contagens não duplicam e não
   há URLs inexistentes sendo repetidamente requisitadas.
6. Comparar a precisão preditiva com os resultados oficiais à medida
   que zonas e seções forem finalizadas, sem usar votos futuros.
7. Só após estabilizar coleta, integração, painel, recuperação de dados
   e reconciliação discutir merge para `main`.

## Operação recomendada (após liberação oficial)

```bash
python preflight_tse.py --exigir-segundo-turno
python coletor_zonal.py --uf SP --limite 100 --taxa 12
python coletor_zonal.py --todas --limite 10000 --taxa 12
```

O arquivo `dados_zonais_6258.json` é retomado nas execuções locais.
Duas tentativas simultâneas sobre o mesmo arquivo são bloqueadas.
No GitHub Actions use o workflow manual "Coleta experimental por zona EA20"
e baixe o artefato para carregar na aba Zonas. O workflow no ramo de
auditoria pode não estar disponível no menu de disparo até que o
GitHub o reconheça no ramo padrão; não modificar `main` sem autorização.

## Limitações não solucionáveis inteiramente antes da apuração

- Ausência de fluxos reais de 2026T2 para aferir latência, saturação,
  falhas de CDN ou aderência dos parâmetros à eleição.
- Não há preferência identificada dos eleitores marginais; cenários
  não equivalem a probabilidades.
- Backtest espacial de 2022 não demonstra generalização temporal.
- Dados por **seção individual** e ordem real de chegada não integram
  ainda a estimativa zonal completa.
- Sem serviço de coleta 24/7 com armazenamento próprio, sincronização
  multi-instância e retenção durável; caches e arquivos locais podem
  desaparecer. O usuário deve guardar artefatos e backups.
- A checagem de fonte por URL HTTPS/EA11 e as validações de layout não
  são verificação criptográfica de assinatura JWS do TSE. JSON
  enviado manualmente permanece não autenticado.
