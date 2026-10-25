# Election Lab 2026 — entrega pré-apuração (24/10/2026)

**Escopo:** candidato a publicação, sem merge nem deploy definitivo. A apuração do segundo turno está prevista para 25/10/2026, às 17h de Brasília.

## Funcionalidade construída na branch de auditoria

- Fonte EA11 (3221/6258), catálogo EA16 oficial, EA20 com validações de eleição, turno, fase, abrangência, votos e seções.
- Coletor de zonas com throttle global de 12 GET/s, 8 workers, checkpoints atômicos e bloqueio após 403/404/429 ou 20 falhas consecutivas.
- Impedimento de misturar dados artificiais e oficiais; rejeição de zona trocada e votos incompatíveis.
- Recuperação por união conservadora dos 12 artifacts mais recentes válidos da branch selecionada, com SHA-256 e retenção de snapshots já obtidos.
- Auditoria automática BR/UF versus zonas, sem exigir igualdade de snapshots assíncronos.
- Histórico BR oficial registrado no mesmo snapshot recuperável, sem incluir projeções; restauração da série local do gráfico no Streamlit quando recuperado.
- Agendamento de coleta a cada 15 minutos de 25/10, 17h a 23h59 BRT, **somente depois de publicar a infraestrutura na branch padrão**. É sujeito a atrasos/cancelamentos do GitHub.
- Sincronização opcional a cada 3 minutos no Streamlit enquanto uma sessão estiver aberta e houver credencial Actions somente leitura.
- CI com testes unitários, importação histórica, 6.292 zonas simuladas em vários estágios, backtests, navegador desktop/mobile, manifesto SHA-256.

## Dependências não resolvíveis apenas por commits na branch experimental

1. **Permissão para produção:** workflow `on.schedule` e `workflow_dispatch` precisam existir na `main`. O PR #1 é rascunho e NÃO deve ser mesclado sem aprovação explícita. Fazer merge isolado só de YAML não funciona sem seus módulos.
2. **Credencial de leitura:** em Streamlit Community Cloud > aplicação **de testes** > Settings > Secrets, configurar em segurança um token fine-grained do GitHub com Actions: Read no repositório, sem colar token em chat ou arquivos públicos:
   ```toml
   GITHUB_SNAPSHOT_TOKEN = "COLOQUE_O_TOKEN_SO_NO_STREAMLIT_SECRETS"
   ELECTION_LAB_SNAPSHOT_BRANCH = "fix/auditoria-pre-segundo-turno"
   ```
   O token é opcional para navegar, mas necessário para baixar artifacts automaticamente. Quando futuramente configurar o app de produção, usar `ELECTION_LAB_SNAPSHOT_BRANCH = "main"`.
3. **Coleta real 2026T2:** após 17h, validar primeira resposta positiva EA20, catálogo EA16, JWS quando disponível e conciliação de gerações por UF/BR. Nenhum backtest sintético substitui esse teste.
4. **Retenção permanente:** caches e artifacts (30 dias) não são banco transacional. Definir armazenamento externo/autorização se precisar retenção superior ao período eleitoral ou operação fora dos limites do GitHub.
5. **Publicado no Streamlit:** conferir o mesmo commit do release candidate no rodapé da aplicação após autorização de deploy; versão de testes não é automaticamente versão de produção.

## Procedimento de ativação controlada — sujeito à aprovação

1. Certificar que os **três jobs** de `Validacao Election Lab` estão verdes no SHA exato da versão candidata.
2. Fazer backup do commit atual da `main` e das configurações de implantação.
3. Revisar diferenças do PR #1; assegurar que a integração na `main` não apague seu único commit divergente.
4. Receber autorização explícita antes de qualquer merge/deploy; só então ativar o workflow na `main`.
5. Na primeira execução: verificar consulta EA11/EA16, logs, contagem de zonas, totais oficiais, SHA-256 do snapshot e auditoria.
6. Configurar token de leitura do Streamlit no ambiente correspondente; testar recuperação automática e preservação do gráfico após reinício.
7. Se houver divergência com o TSE, suspender consumo da projeção, guardar artifact para diagnóstico e revisar; nunca substituir números oficiais por simulados.

**Regra de segurança:** a aplicação principal e a branch `main` permanecem inalteradas nesta preparação.
