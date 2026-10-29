# Decisões

Registro curto de decisões tomadas. Uma nova decisão entra no topo.

## D10 — Oportunidades vêm do Siconv: programas elegíveis e dirigidos à prefeitura (29/10/2026)
Entra como `oportunidade` o programa `DISPONIBILIZADO` do Siconv com janela de propostas aberta, natureza municipal e UF SP (ou sem UF), mais os programas dirigidos à prefeitura com alguma janela aberta; o fim da janela é o prazo `adesao`. Programas só para beneficiário de emenda, `CADASTRADO` e `INATIVO` ficam de fora. Motivo: é a única fonte automática que traz janelas, natureza elegível e UF; `parcerias/programa` não tem janela espontânea aberta e o Obrasgov não lista programas. Ressalva: a carga do Siconv é de 17/07/2026, então "aberto" é um mínimo e a data da carga aparece no site.

## D9 — Coleta diária às 09:00 (Brasília) e alerta de CAUC sem a palavra "irregular" (29/10/2026)
O CAUC é publicado em dias úteis por volta das 08:11 (Brasília), então a coleta passou de 06:00 para 09:00 (cron `0 12 * * *`). O `!` do CAUC significa "o Tesouro não conseguiu obter a comprovação do requisito", e 307 dos 645 municípios de SP têm algum; por isso o alerta se chama `cauc_sem_comprovacao`, vale para qualquer item `!` e diz o item (ex.: "CAUC: item 4.2 sem comprovação (Regularidade Previdenciária)"). Não afirma irregularidade que o arquivo não declara.

## D8 — Obrasgov é fonte auxiliar e não define o status do site (29/10/2026)
O status vem do Transferegov/Siconv. O Obrasgov só entra quando a prefeitura é executora e o projeto se liga a um instrumento (ponte `siconv_dados_obrasgov_geral`); alimenta o alerta `obra_parada`, o percentual físico e o dossiê da curadoria. Sem registro de execução física, não há alerta. Motivo: na POC da T1.3 as 3 obras da prefeitura estavam "Cadastrada" e sem medição enquanto os convênios estavam "Em execução" no Siconv (um com R$ 288 mil desembolsados); o cadastro dos gestores fica desatualizado.

## D7 — Curadoria assistida por IA, com revisão humana obrigatória na fase 1 (29/10/2026)
A IA lê os documentos oficiais e redige motivo, categoria e citações. Uma pessoa aprova antes de publicar. Publicação automática só depois, e só para casos em que o documento declara o motivo (spec §7.5). Motivo: velocidade sem risco de publicar causa inventada sobre gestão pública.

## D6 — Recorte da fase 1: só verbas federais desde 2024 (29/10/2026)
Estaduais (SP) na fase 2. Motivo: as federais têm APIs e documentação do "porquê"; lançar com dado verificável protege a credibilidade.

## D5 — Postura: iniciativa cidadã independente (29/10/2026)
Sem brasão ou identidade visual da prefeitura. Faixa de independência em toda página.

## D4 — Nome: Verba à Vista — Neves Paulista (29/10/2026)
Com crase ("à vista").

## D3 — Site estático + dados versionados no Git (29/10/2026)
Sem servidor nem banco. Astro + GitHub Actions + Pages. Os retratos brutos no Git são a trilha de auditoria.

## D2 — Status do site com 7 etapas + alerta "Em risco" (29/10/2026)
"Em risco" é alerta, não etapa. Status original da fonte sempre exibido ao lado.

## D1 — Motivo de perda só com documento citado (29/10/2026)
Sem documento: "motivo em apuração".

## Em aberto
- Quem revisa os rascunhos da IA (só a autora, voluntários ou parceria). Define se a fila fica em YAML/PR no GitHub ou numa planilha.
- Onde roda a coleta (GitHub Actions ou servidor no Brasil). A T1.0 (29/10/2026) não encontrou bloqueio do Actions nos hosts testados, então a tendência é GitHub Actions. Fica em aberto até as POCs confirmarem os endpoints reais a partir do Actions (T1.1 e T1.4).
- Domínio do site.
- E-mail de contato do projeto.
