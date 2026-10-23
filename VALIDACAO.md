# Validação e liberação do Election Lab 2026

## Estado em 23/10/2026

- **Históricos**: `historico_ufs.csv` e `historico_zonas.csv` devem
  reconciliar exatamente; 2022T2 = 118.552.353 votos válidos; 2026T1 =
  119.300.788 votos válidos. `python validar_historicos.py --ufs historico_ufs.csv --zonas historico_zonas.csv`.
- **Teste retrospectivo**: `python backtest_comparativo.py --zonas historico_zonas.csv`.
  Simula divulgação de zonas de 2026T1, usando como votos históricos apenas
  2022T2. **NÃO** é backtest do 2º turno de 2026.
- **Testes determinísticos**: `python -m unittest discover -p 'test_*.py' -v`.
- **TSE EA20**: `v.vv` = votos válidos; `v.tvn` = votos nulos.
- **Integração oficial do 1º turno**:
  `python teste_integracao_tse.py --turno 1` consulta **uma** zona
  (SP, município TSE 71072, zona 0001, eleição 6257) e compara os votos
  finais com os históricos locais. Um erro de rede, 403 ou 404 significa
  **integração não validada**, mesmo que testes unitários passem.
- **Integração do 2º turno**: não é possível concluí-la antes de 25/10/2026
  às 17h (Brasília). Após essa hora, executar
  `python teste_integracao_tse.py --turno 2`. O código não fabrica resultados
  nem presume que as URLs já estejam disponíveis.

## Regras de apresentação ao vivo

1. Arquivo nacional e arquivos estaduais são **resultados oficiais**, nunca
   calculados somando amostras zonais.
2. Resultados `BR` e UFs só são declarados conciliados se todos os 28
   arquivos estiverem disponíveis **na mesma geração** e os votos e seções
   coincidirem; gerações diferentes significam *aguardar sincronização*.
3. A soma de uma amostra de município/zonas só é **compatível**, não equivale
   a uma UF. Uma zona atualizada antes do arquivo estadual não pode gerar
   falso diagnóstico de inconsistência.
4. O monitor amostra até 48 município/zonas por UF, com no máximo oito
   consultas por atualização. Outras zonas permanecem representadas apenas
   pelo histórico; a amostra não é aleatória.
5. Sem conciliação parcial possível, a **projeção zonal fica suspensa**.
   Dados antigos ou parciais com regressão de seções não substituem
   snapshots mais recentes.
6. A estimativa principal nacional permanece por UF. O híbrido de backtest
   **não está calibrado fora da amostra** e não é publicado como projeção
   eleitoral verificada.
7. A série de consultas em memória do Streamlit pode desaparecer após
   reinício, portanto não constitui armazenamento auditável permanente.

## Checklist de liberação pós-início da totalização em 25/10/2026

- [ ] Confirmar eleição 6258 na configuração de eleições EA11 do TSE.
- [ ] Consultar EA20 oficial BR, uma UF e uma zona. Checar `vv`, `vap`,
  `st`, `ts` e `dg/hg`. Sem votação, não há aprovação de integração.
- [ ] Rodar `python teste_integracao_tse.py --turno 2` e guardar saída.
- [ ] Confirmar que o TSE não mudou o esquema da URL zonal e que a zona
  está no cadastro oficial EA12 do **segundo turno**.
- [ ] Verificar atualização sucessiva sem regressão de seções.
- [ ] Obter duas gerações comparáveis de BR/UF/zonas; verificar o diagnóstico
  sem exigir igualdade entre amostra e UF.
- [ ] Confirmar que a projeção é suspensa diante de inconsistência real e
  rotulada como experimental se a cobertura for parcial.
- [ ] Após os passos anteriores e testes de CI aprovados, revisar o
  pull request antes de mesclar na `main`; publicação do Streamlit
  somente após verificação no ambiente de destino.

## Fontes

Documentação técnica oficial do TSE:
https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados

EA20 federal: `https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json`.

**Atenção**: o 2º turno não possui resultado oficial antes de 25/10/2026 às
17h de Brasília. A disponibilidade da URL e a consistência de sua resposta
só podem ser verificadas a partir da totalização.
