import assert from "node:assert/strict";
import { test } from "node:test";

import { descricaoMeta, historicoOrdenado, partesComCitacoes, seloDaPerda, valoresDaVerba } from "../src/lib/verba.js";

test("citações [n] viram pedaços, sem HTML cru", () => {
  assert.deepEqual(partesComCitacoes("A obra parou [1]. Houve prazo [2][3]."), [
    { texto: "A obra parou " }, { cita: 1 }, { texto: ". Houve prazo " }, { cita: 2 }, { cita: 3 }, { texto: "." },
  ]);
  assert.deepEqual(partesComCitacoes("Sem citação."), [{ texto: "Sem citação." }]);
  assert.deepEqual(partesComCitacoes("<b>x</b> [1]"), [{ texto: "<b>x</b> " }, { cita: 1 }]); // o Astro escapa o texto
});

test("valores: só o que existe, contrapartida zero é \"Não exige\", valor nulo é \"A definir\"", () => {
  const itens = valoresDaVerba({ valor_total: 70075000, valor_liberado: 0, valor_contrapartida: 0, prazos: { proposta: "2024-05-13" }, perda: { data: "2025-01-21" } });
  assert.deepEqual(itens.map((i) => [i.rotulo, i.valor]), [
    ["Valor da verba", "R$ 700.750"], ["Valor liberado", "R$ 0"], ["Contrapartida", "Não exige"], ["Proposta enviada em", "13/05/2024"], ["Perdida em", "21/01/2025"],
  ]);
  assert.deepEqual(valoresDaVerba({ valor_total: null }).map((i) => [i.rotulo, i.valor]), [["Valor da verba", "A definir"]]);
  assert.equal(valoresDaVerba({ valor_total: 1, parlamentar: "FULANO" }).find((i) => i.rotulo === "Autor da emenda").valor, "FULANO");
});

test("histórico: mais recente primeiro; no mesmo dia, o último gravado primeiro", () => {
  const h = historicoOrdenado({ historico: [{ data: "2026-10-01", para: "a" }, { data: "2026-10-05", para: "b" }, { data: "2026-10-05", para: "c" }] });
  assert.deepEqual(h.map((x) => x.para), ["c", "b", "a"]);
});

test("descrição do preview: curta e fiel ao que se sabe", () => {
  const base = { nome: "REFORMA DA UBS", valor_total: 85000000 };
  assert.equal(descricaoMeta({ ...base, perda: { categoria: "em_apuracao" } }, "Perdida"), "Reforma da UBS: Perdida, R$ 850.000. Motivo da perda em apuração. Com os documentos oficiais citados.");
  assert.match(descricaoMeta({ ...base, perda: { categoria: "cauc" } }, "Perdida", "Irregularidade no CAUC"), /Motivo da perda: Irregularidade no CAUC\./);
  assert.match(descricaoMeta({ ...base, em_risco: true, motivos_risco: [{ texto: "Prazo em 51 dias" }] }, "Em execução"), /Em risco: Prazo em 51 dias\./);
  assert.ok(descricaoMeta({ nome: "X".repeat(400), valor_total: null }, "Aprovada").length <= 200);
});

test("selo: com IA, só humano ou nenhum", () => {
  const perda = { revisado_por: "Revisora", revisado_em: "2026-10-30", gerado_por_ia: true };
  assert.equal(seloDaPerda(perda, "Explicação gerada com IA a partir dos documentos citados"), "Explicação gerada com IA a partir dos documentos citados · revisada por Revisora em 30/10/2026");
  assert.equal(seloDaPerda({ ...perda, gerado_por_ia: false }, "x"), "Explicação revisada por Revisora em 30/10/2026");
  assert.equal(seloDaPerda({ revisado_por: null, gerado_por_ia: false }, "x"), null);
});

test("rótulo da situação: chave do status vira o rótulo; texto da fonte passa direto", async () => {
  const { rotuloSituacao } = await import("../src/lib/verba.js");
  const taxonomia = { status: { perdida: "Perdida", execucao: "Em execução" } };
  assert.equal(rotuloSituacao("perdida", taxonomia), "Perdida");
  assert.equal(rotuloSituacao("Proposta enviada", taxonomia), "Proposta enviada");
});
