import assert from "node:assert/strict";
import { test } from "node:test";

import { comoAchar, descricaoDaVerba, descricaoMeta, historicoOrdenado, partesComCitacoes, seloDaPerda, valoresDaVerba } from "../src/lib/verba.js";

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
    ["Valor da verba", "R$ 700.750"], ["Valor liberado", "R$ 0"], ["Contrapartida", "Não exige"], ["Data da proposta", "13/05/2024"], ["Situação desde", "21/01/2025"],
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

const taxonomia = {
  tipos: { voluntaria: "Convênio, contrato de repasse ou termo de compromisso", programa_adesao: "Programa por adesão ou seleção" },
  status: { perdida: "Perdida", oportunidade: "Oportunidade" },
  descricao_tipos: { voluntaria: "Acordo em que a União transfere dinheiro.", programa_adesao: "Programa federal aberto aos municípios." },
  descricao_status: { perdida: "Município não recebeu ou teve de devolver o recurso.", oportunidade: "Programa que o município pode pleitear." },
};

test("descrição da verba: só dados dela, mais o que o tipo e a etapa significam", () => {
  const d = descricaoDaVerba({ instrumento: "CONVENIO", tipo: "voluntaria", status_site: "perdida", nome: "AQUISIÇÃO DE PATRULHA AGRICOLA", objeto: "AQUISIÇÃO DE PATRULHA AGRICOLA", orgao_concedente: "MINISTÉRIO DA AGRICULTURA E PECUÁRIA", valor_total: 70075000 }, taxonomia);
  assert.equal(d.resumo, "Convênio: “Aquisição de patrulha agricola”, no valor de R$ 700.750 (concedente: Ministério da Agricultura e Pecuária).");
  assert.deepEqual(d.tipo, { rotulo: "Convênio, contrato de repasse ou termo de compromisso", texto: "Acordo em que a União transfere dinheiro." });
  assert.deepEqual(d.etapa, { rotulo: "Perdida", texto: "Município não recebeu ou teve de devolver o recurso." });
});

test("descrição da verba sem valor, sem concedente e sem etapa não inventa nada", () => {
  const d = descricaoDaVerba({ tipo: "programa_adesao", status_site: null, nome: "Novo PAC - Seleção", valor_total: null }, taxonomia);
  assert.equal(d.resumo, "Programa por adesão: “Novo PAC - Seleção”.");
  assert.equal(d.etapa, null);
});

test("como achar no Transferegov: o clique, o número e o que ele é em cada módulo", () => {
  assert.deepEqual(comoAchar({ fonte: "transferegov_discricionarias", numero_instrumento: "12684/2024" }), { numero: "12684/2024", rotulo: "número da proposta", onde: "clique em “Consultar Propostas”" });
  assert.deepEqual(comoAchar({ fonte: "transferegov_discricionarias", numero_instrumento: "970941" }), { numero: "970941", rotulo: "número do instrumento", onde: "clique em “Consultar Pré-Instrumentos/Instrumentos”" });
  assert.deepEqual(comoAchar({ fonte: "siconv_programa", numero_instrumento: "5600020260007" }), { numero: "5600020260007", rotulo: "código do programa", onde: "clique em “Consultar Programas”" });
  assert.equal(comoAchar({ fonte: "transferegov_fundoafundo", numero_instrumento: "30882120230006-013785" }).rotulo, "Código do Plano de Ação");
  assert.equal(comoAchar({ fonte: "transferegov_parcerias", numero_instrumento: "202500017102" }).rotulo, "código da parceria");
  assert.equal(comoAchar({ fonte: "obrasgov", numero_instrumento: "1" }), null);
  assert.equal(comoAchar({ fonte: "transferegov_parcerias" }), null);
});

test("a etapa perdida vira Cancelada, Rescindida ou Anulada conforme a situação na fonte; senão, Rejeitada", async () => {
  const { rotuloStatus } = await import("../src/lib/verba.js");
  const taxonomia = {
    sem_status: "Situação em análise",
    status: { perdida: "Rejeitada", execucao: "Em execução" },
    rotulos_perda: [{ contem: "cancelad", rotulo: "Cancelada" }, { contem: "rescindid", rotulo: "Rescindida" }, { contem: "anulad", rotulo: "Anulada" }],
  };
  const v = (status_site, status_fonte) => ({ status_site, status_fonte });
  assert.equal(rotuloStatus(v("perdida", "Proposta/Plano de Trabalho Cancelados"), taxonomia), "Cancelada");
  assert.equal(rotuloStatus(v("perdida", "Convênio Rescindido"), taxonomia), "Rescindida");
  assert.equal(rotuloStatus(v("perdida", "Convênio Anulado"), taxonomia), "Anulada");
  assert.equal(rotuloStatus(v("perdida", "Proposta/Plano de Trabalho Rejeitados por Impedimento técnico"), taxonomia), "Rejeitada");
  assert.equal(rotuloStatus(v("execucao", "Convênio Cancelado"), taxonomia), "Em execução"); // só a etapa perdida troca de rótulo
  assert.equal(rotuloStatus(v(null, "x"), taxonomia), "Situação em análise");
});
