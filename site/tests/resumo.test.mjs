import assert from "node:assert/strict";
import { test } from "node:test";

import { carregarTaxonomia } from "../src/lib/taxonomia.js";
import { emRiscoAgora, evitaveis, formatarCompacto, formatarNomeProprio, formatarTitulo, perdasPorMotivo, resumir, rotuloInstrumento, rotuloRisco, ultimasMudancas } from "../src/lib/resumo.js";

const taxonomia = carregarTaxonomia();
const motivo = (codigo, texto = codigo) => ({ codigo, texto });
const verba = (id, status, valor, extra = {}) => ({ id, status_site: status, valor_total: valor, em_risco: false, historico: [], ...extra });
const perda = (categoria, valor, extra = {}) => ({ categoria, valor_perdido: valor, citacoes: categoria === "em_apuracao" ? [] : [{ n: 1 }], evitavel: "indeterminado", ...extra });

const verbas = [
  verba("a", "aprovada", 100_000_00),
  verba("b", "execucao", 200_000_00, { em_risco: true, motivos_risco: [motivo("cauc_sem_comprovacao")] }),
  verba("c", "prestacao", 50_000_00),
  verba("d", "concluida", 70_000_00),
  verba("e", "oportunidade", null),
  verba("f", "proposta", 900_000_00, { em_risco: true, motivos_risco: [motivo("prazo_proximo", "Prazo em 10 dias")] }),
  verba("g", "proposta", 300_000_00, { em_risco: true, motivos_risco: [motivo("cauc_sem_comprovacao")] }),
  verba("h", "perdida", 500_000_00, { perda: perda("em_apuracao", 400_000_00) }),
  verba("i", "perdida", 100_000_00, { perda: perda("cauc", 80_000_00, { evitavel: "sim" }) }),
  verba("j", "perdida", 100_000_00, { perda: perda("cauc", 20_000_00, { evitavel: "nao" }) }),
];

test("resumo: quatro números e oportunidades", () => {
  const r = resumir(verbas);
  assert.deepEqual(r.andamento, { n: 3, valor: 350_000_00 });
  assert.deepEqual(r.risco, { n: 3, valor: 1_400_000_00 });
  assert.deepEqual(r.perdidas, { n: 3, valor: 500_000_00, documentadas: 2 });
  assert.deepEqual(r.concluidas, { n: 1, valor: 70_000_00 });
  assert.equal(r.oportunidades.n, 1);
});

test("perdas por motivo: maior primeiro, barra proporcional, rótulo da taxonomia", () => {
  const lista = perdasPorMotivo(verbas, taxonomia);
  assert.deepEqual(lista.map((g) => [g.categoria, g.n, g.valor, g.largura]), [
    ["em_apuracao", 1, 400_000_00, 100],
    ["cauc", 2, 100_000_00, 25],
  ]);
  assert.equal(lista[0].rotulo, "Motivo em apuração");
  assert.deepEqual(lista[1].verbas.map((v) => v.id), ["i", "j"]); // do maior valor perdido para o menor
  assert.equal(lista[1].rotulo, taxonomia.categorias.cauc.rotulo);
});

test("evitáveis só contam perdas com motivo documentado", () => {
  assert.deepEqual(evitaveis(verbas), { total: 2, evitaveis: 1 });
  assert.deepEqual(evitaveis([verba("x", "perdida", 1, { perda: perda("em_apuracao", 1) })]), { total: 0, evitaveis: 0 });
});

test("em risco agora: prazo antes do CAUC, depois o maior valor; respeita o limite", () => {
  assert.deepEqual(emRiscoAgora(verbas).map((v) => v.id), ["f", "g", "b"]);
  assert.deepEqual(emRiscoAgora(verbas, 1).map((v) => v.id), ["f"]);
});

test("últimas mudanças ignoram a entrada inicial e vêm da mais recente", () => {
  const com = [
    verba("p", "execucao", 1, { historico: [{ data: "2026-10-01", de: null, para: "Aprovada" }, { data: "2026-10-20", de: "Aprovada", para: "Em execução" }] }),
    verba("q", "perdida", 1, { historico: [{ data: "2026-10-25", de: "Proposta enviada", para: "Perdida" }] }),
  ];
  assert.deepEqual(ultimasMudancas(com).map((m) => [m.verba.id, m.data]), [["q", "2026-10-25"], ["p", "2026-10-20"]]);
  assert.deepEqual(ultimasMudancas([verba("z", "aprovada", 1, { historico: [{ data: "2026-10-30", de: null, para: "Aprovada" }] })]), []);
});

test("formatação compacta de valores", () => {
  assert.equal(formatarCompacto(3_200_000_00), "R$ 3,2 mi");
  assert.equal(formatarCompacto(2_180_000_00), "R$ 2,18 mi");
  assert.equal(formatarCompacto(520_000_00), "R$ 520 mil");
  assert.equal(formatarCompacto(950_00), "R$ 950");
});

test("título em caixa alta vira frase, preservando siglas", () => {
  assert.equal(formatarTitulo("REFORMA DA UBS CENTRAL"), "Reforma da UBS central");
  assert.equal(formatarTitulo("Quadra poliesportiva coberta"), "Quadra poliesportiva coberta");
  assert.equal(formatarTitulo(null), null);
  assert.equal(formatarTitulo("EQUIPAMENTO PARA O MUNICIPIO DE NEVES PAULISTA - SP"), "Equipamento para o municipio de Neves Paulista - SP");
});

test("nome de órgão em caixa alta", () => {
  assert.equal(formatarNomeProprio("MINISTÉRIO DA AGRICULTURA E PECUÁRIA"), "Ministério da Agricultura e Pecuária");
  assert.equal(formatarNomeProprio("FUNDO NACIONAL DE SAÚDE"), "Fundo Nacional de Saúde");
  assert.equal(formatarNomeProprio("Ministério da Saúde"), "Ministério da Saúde");
  assert.equal(formatarNomeProprio(null), null);
});

test("rótulos de alerta e instrumento", () => {
  assert.equal(rotuloRisco(motivo("cauc_sem_comprovacao", "CAUC: item 4.2")), "Pendência no CAUC");
  assert.equal(rotuloRisco(motivo("prazo_proximo", "Prazo em 51 dias")), "Prazo em 51 dias");
  assert.equal(rotuloInstrumento({ instrumento: "CONTRATO DE REPASSE", tipo: "voluntaria" }), "Contrato de repasse");
  assert.equal(rotuloInstrumento({ instrumento: "CONVENIO", tipo: "voluntaria" }), "Convênio");
  assert.equal(rotuloInstrumento({ tipo: "programa_adesao" }), "Programa por adesão");
});
