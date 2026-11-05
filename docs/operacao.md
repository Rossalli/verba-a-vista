# Operação

O que configurar no GitHub para o workflow diário funcionar, e o que fazer no dia a dia. O comportamento do workflow está em `docs/spec.md` §9.

## Configuração do repositório (uma vez)

Em **Settings** do repositório:

1. **Pages → Build and deployment → Source: GitHub Actions.** Sem isso o passo `configure-pages` falha. (GitHub Pages em repositório privado exige plano pago; em repositório público é gratuito.)
2. **Secrets and variables → Actions → Secrets:**
   - `PORTAL_TRANSPARENCIA_KEY`: a chave do Portal da Transparência (a mesma do `.env`).
   - `ANTHROPIC_API_KEY`: só se for ligar a curadoria com IA (abaixo).
   - A chave precisa estar **vinculada a um workspace** da Anthropic. Chave sem workspace faz a API devolver `400` ("not scoped to a workspace") e nenhum rascunho é gerado; nesse caso o dia segue sem a IA e o log mostra um aviso. Crie a chave no Console escolhendo o workspace e atualize o secret.
3. **Secrets and variables → Actions → Variables:**
   - `CURADORIA_IA`: deixe **sem criar** (ou diferente de `true`) para a IA ficar desligada. Com `true`, o workflow chama a IA (cobrado) para as perdas sem rascunho. É cobrado só por perda nova; perda que já tem rascunho ou erro em `dados/fila/` não é enviada de novo.
4. **Actions → General → Workflow permissions:** "Read and write permissions" (o workflow já pede `contents`, `issues` e `pages` em `permissions:`; em alguns repositórios o padrão do projeto precisa ser liberado aqui).
5. Se o branch `main` tiver proteção, permita que `github-actions[bot]` faça push nele, ou o commit dos dados falha.

Primeira execução: **Actions → Coleta diária → Run workflow**. Ela coleta, publica, abre as issues de aviso que couberem, implanta o site e mostra a URL no passo `deploy`.

## Dia a dia

- **Issue "Rascunhos de curadoria para revisar":** abra o arquivo em `dados/fila/<id>.yaml`, confira os trechos contra os documentos que estão no próprio arquivo, edite o `rascunho` se precisar e rode `python -m curadoria.aprovar <id> --por "<seu nome>"`. Faça commit de `dados/curadoria/<id>.yaml`: o push republica o site sozinho.
- **Issue "Situações de fonte sem mapeamento":** decida o status do site de cada situação, acrescente em `config/status_map.yaml` e registre a fonte da definição em `docs/fontes.md`. Até lá, a verba aparece como "situação em análise".
- **Issue "Fonte sem retrato de hoje":** veja o log da execução e `dados/brutos/<fonte>/<data>.log.json`. O site continua no ar com o último retrato válido e mostra a data dele.
- **Falha do workflow (e-mail do GitHub):** erro no pipeline (por exemplo, arquivo de curadoria inválido) para tudo e nada é publicado nem implantado; o site fica como estava.

## Lançamento: liberar a indexação

Até o lançamento o site é público mas pede aos buscadores para **não** indexá-lo (`noindex` em todas as páginas). Depois da revisão de credibilidade (spec §12), crie a variável em **Settings → Secrets and variables → Actions → Variables**: `SITE_INDEXAR` = `true`, e rode o workflow (Actions → Coleta diária → Run workflow). O `noindex` só some no deploy seguinte. Para voltar a bloquear, apague a variável ou mude o valor e rode de novo.

O `noindex` é um pedido, não uma trava: quem tem o link abre o site normalmente.

## Domínio próprio (quando houver)

Configure em **Settings → Pages → Custom domain**. O `base` do site vem da configuração do Pages (`configure-pages`), então nada muda no código. O e-mail de contato fica em `site/src/config.js`.
