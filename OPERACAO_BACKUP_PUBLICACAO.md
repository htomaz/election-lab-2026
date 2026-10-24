# Operação pré-apuração, backups e publicação controlada — 24/10/2026

**Branch de desenvolvimento:** `fix/auditoria-pre-segundo-turno` (PR #1).
**Não há autorização para merge em `main` nem deploy de produção.**

## 1. Testes funcionais e interface

A suíte de CI executa `python -m unittest discover -p 'test_*.py'`
(inclui `test_app_integracao.py`, `test_painel_zonal_smoke.py`)
e um job separado, em **Chromium real**, com:

- Painel de demonstração e rótulo explícito de votos fictícios;
- Três abas: Painel, Zonas e Históricos;
- Capturas de tela em **1440×900 (desktop)** e **390×844 (celular)**;
- Teste de rolagem horizontal no viewport móvel;
- Relatório `visual-auditoria/relatorio.json` e screenshots PNG;
- Sem cliques em apuração real antes do dia/horário oficial.

O CI publica o artifact **`ui-desktop-mobile-auditoria`**.
Fotos reais em Android/iOS e condições reais de conexão ainda
dependem de conferência humana; Chromium é o teste automatizado.

## 2. Persistência do snapshot zonal

A coleta `coletor_zonal.py` continua salvando atomicamente em
`dados_zonais_6258.json`, com lock de arquivo Linux/Windows,
checkpoint a cada 100 zonas ou 20 segundos e retenção de dados após
falhas. O GitHub Actions usa três camadas:

1. **Cache entre execuções** — retomada rápida, mas não garantida;
2. **Artifact por execução**, `snapshot-zonal-6258`, retido por 30 dias,
   contendo JSON e `snapshot.sha256`;
3. **Recuperação do artifact validado** por `backup_actions.py`.
   São aceitos somente artifacts não expirados da branch auditada,
   com SHA correto, eleição 6258, catalogação EA16 3221 e zonas válidas.
   A mesclagem impede que observações recentes sejam substituídas por
   gerações anteriores e preserva zonas acumuladas.

No Streamlit, a aba **Zonas > Backup e recuperação** permite download
do snapshot local. Para recuperar automaticamente um artifact em
repositório privado, configure no **Streamlit Secrets**
`GITHUB_SNAPSHOT_TOKEN`, um fine-grained PAT com permissão
**Actions: Read-only** para `htomaz/election-lab-2026`.
Não inclua o token no código, nas URLs, em logs ou no GitHub.
Sem esse segredo, use a importação manual do JSON obtido do Actions.

**Limite importante:** artifacts não são banco de dados transacional e
podem expirar; o SQLite de `registro.py` para evolução nacional
permanece local, com backup/restauração CSV explícito. Para retenção
automática e durável **mesmo sem o aplicativo ativo**, será preciso
provisionar armazenamento externo com permissão de leitura/escrita.
Nenhum token ou banco externo foi criado sem autorização.

## 3. Proveniência/autenticidade EA20

O coletor já exigia `ele=6258`, `t=2`, `f=o`, origem
HTTPS, abrangência correta, campos completos e conciliação numérica.
Agora registra `sha256_ea20`, calculado sobre o JSON recebido de
cada zona, e a URL exata esperada.

Na aba Zonas, após início da apuração, há uma verificação
**opcional de até cinco zonas por vez**, que consulta novamente as URLs
oficiais e compara horário de geração, votos/seções e SHA-256.
Gerações mais recentes são indicadas separadamente, para não produzir
falsas suspeitas de corrupção durante a apuração.

A assinatura criptográfica oficial **JWS** da publicação do TSE
ainda não é validada automaticamente pela aplicação. SHA-256 +
fonte HTTPS e uma amostra reconsultada **não** substituem assinatura
Ed25519/JWS e não autentica integralmente um upload arbitrário.
Portanto, não afirmar que um arquivo importado foi assinado
ou criptograficamente homologado. Manual oficial:
https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/divulgacao-de-resultados

## 4. Publicação reproduzível, SEM DEPLOY

`release_candidate.py` gera `release-candidate.json` com:
commit exato do Git, branch, versão de Python e hashes SHA-256
de códigos críticos, dependências e arquivos históricos.

O job `candidato` só é executado após o sucesso dos jobs **testes**
e **navegador** e somente em push para a branch de auditoria.
O artifact `release-candidate-sha256` permite verificar
os mesmos bytes em outra máquina antes de qualquer publicação.
Não há credenciais de escrita, nem deploy, nem `git merge` no CI.

**Critérios mínimos de aprovação posterior:**

1. Pipeline completo verde no commit exato da PR, inclusive screenshots;
2. Revisão visual das 3 abas e dos alertas oficiais versus simulação;
3. Backup do estado anterior da aplicação publicada;
4. Autorização explícita para merge/publicação;
5. Build utilizando commit igual ao manifesto SHA-256;
6. Verificação pós-deploy de URL, navegabilidade e funcionamento de backup;
7. Plano de rollback: restabelecer imediatamente o commit anterior da
   `main`/branch de deploy, sem apagar os dados e artifacts de auditoria.

**Antes da primeira parcial do segundo turno não é possível afirmar
que todas as integrações de voto real do EA20 estejam homologadas.**
