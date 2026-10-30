# Decisões

Registro curto de decisões tomadas. Uma nova decisão entra no topo.

## D13 — Regras de risco: oportunidades fora, CAUC só no Siconv, impedimento desligado (30/10/2026)
(1) `em_risco` só nas etapas proposta, aprovada, execução e prestação; as 10 oportunidades (prazo de adesão em 31/12/2026, que entraria na janela de 60 dias em 01/11) mostram o prazo à parte e não entram em "Em risco agora". (2) O alerta de CAUC vale só para verbas do Transferegov Discricionárias e Legais (transferências voluntárias): evita pôr "item 4.2 sem comprovação" nas 12 propostas de fundo a fundo de Saúde e Assistência de `parcerias`. Que o fundo a fundo seja dispensado do CAUC está só como nota minha em `docs/fontes.md`, sem fonte oficial: conferir na revisão de credibilidade (spec §12). (3) `impedimento_emenda` está implementada e **desligada** (`risco.desligadas`): o campo `motivo_impedimento_plano_acao` existe no OpenAPI de `especiais` mas o município não tem registros ali (T1.1), então não há como confirmá-lo; os testes usam dados de exemplo. (4) Prazo já vencido não dispara `prazo_proximo`: os 11 prazos vencidos de hoje são de instrumentos parados há anos (2009 a 2024), não de prazos chegando.

## D12 — Normalização: tipo das verbas do Siconv, valor nulo e Novo PAC adiado (29/10/2026)
(1) Convênio, contrato de repasse, termo de compromisso e termo de fomento viram `voluntaria`; `emenda_finalidade` só quando há emenda registrada; a modalidade original fica visível. Motivo: 9 das 22 verbas do recorte são termo de compromisso, a spec não os cobria e não há prova de que sejam outro tipo. (2) `valor_total` pode ser nulo (oportunidades não têm valor), para não publicar R$ 0. (3) As propostas do Novo PAC Seleções ficam só no bruto, sem virar verbas, até haver a chave que as liga ao Siconv: elas parecem repetir verbas já formalizadas (mesmo repasse de R$ 2,8 mi e R$ 3,25 mi), e a tabela de ligação (`proposta_formalizacao_pac`) estava no servidor que saiu do ar. (4) Junção Siconv-Portal por `NR_PROPOSTA`↔`numero` **ou** `NR_PROCESSO`↔`numeroProcesso`, ignorando zeros à esquerda: casa 26 dos 28 convênios do Siconv (os 2 restantes não têm convênio assinado).

## D11 — Portal da Transparência é fonte de complemento: valores e pagamentos, não status (29/10/2026)
O status do site continua vindo do Transferegov/Siconv. O Portal atualiza `valor_liberado` (está à frente da carga do Siconv: o convênio 33961/2024 tem R$ 650 mil pagos em 23/07/2026 que a carga de 17/07 não tem), lista pagamentos recebidos pelos CNPJs da prefeitura e dos fundos (incluindo estornos, candidatos a `valor_devolvido`), liga pagamento a emenda pelo código do autor e serve de conferência. A emenda no Portal vem agregada (`MÚLTIPLO`), então não dá o valor que o município recebeu, e `recursos-recebidos` só funciona por CNPJ, não por `codigoIBGE`. Nos 19 instrumentos que casam (dos 28 do Siconv) a situação é consistente entre as fontes. Mesma linha do Obrasgov (D8).

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
- **Fonte do Siconv em lote fora do ar (29/10/2026).** O diretório `repositorio.dados.gov.br/seges/detru/` passou a dar 404 (docs/fontes.md §Discricionárias, alerta). Dele dependem os convênios com o detalhe das regras de risco (cláusula suspensiva, prazos de prestação de contas, histórico), as oportunidades (D10) e a ponte Obrasgov-Siconv. Caminhos possíveis: esperar e monitorar o retorno; achar o novo endereço; ou usar o Portal da Transparência como fonte de convênios (63 registros, mais atual, mas sem o detalhe do Siconv). Decidir antes da T2.2.
- Quem revisa os rascunhos da IA (só a autora, voluntários ou parceria). Define se a fila fica em YAML/PR no GitHub ou numa planilha.
- Onde roda a coleta (GitHub Actions ou servidor no Brasil). A T1.0 (29/10/2026) não encontrou bloqueio do Actions nos hosts testados, então a tendência é GitHub Actions. Fica em aberto até as POCs confirmarem os endpoints reais a partir do Actions (T1.1 e T1.4).
- Domínio do site.
- E-mail de contato do projeto.
