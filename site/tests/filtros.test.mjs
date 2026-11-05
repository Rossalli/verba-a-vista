import assert from "node:assert/strict";
import { test } from "node:test";

import { SEM_DATA, anoDaVerba, contarPorStatus, corresponde, lerFiltros, normalizar, ordenarLista, paraParametros } from "../src/lib/filtros.js";

const linha = (status, extra = {}) => ({ status, risco: false, tipo: "voluntaria", busca: normalizar("Ambulância Ministério da Saúde 12345/2024"), ...extra });
const TIPOS = ["voluntaria", "emenda_finalidade"];
const ANOS = ["2026", "2025", SEM_DATA];

test("normalizar tira acento e caixa", () => {
  assert.equal(normalizar("  Saúde É Ação "), "saude e acao");
  assert.equal(normalizar(null), "");
});

test("lê filtros da URL e ignora valores desconhecidos", () => {
  const f = lerFiltros(new URLSearchParams("status=perdida&risco=1&tipo=voluntaria&ano=2025&q=ambulancia"), TIPOS, ANOS);
  assert.deepEqual(f, { status: "perdida", risco: true, tipo: "voluntaria", ano: "2025", q: "ambulancia" });
  assert.deepEqual(lerFiltros(new URLSearchParams("status=xxx&risco=0&tipo=inventado&ano=1999"), TIPOS, ANOS), { status: "todas", risco: false, tipo: "", ano: "", q: "" });
  assert.equal(lerFiltros(new URLSearchParams("ano=sem-data"), TIPOS, ANOS).ano, SEM_DATA);
});

test("a URL só leva o que difere do padrão, e ida e volta preserva o estado", () => {
  assert.equal(paraParametros({ status: "todas", risco: false, tipo: "", ano: "", q: "  " }).toString(), "");
  const f = { status: "execucao", risco: true, tipo: "voluntaria", ano: "2026", q: "quadra coberta" };
  assert.deepEqual(lerFiltros(paraParametros(f), TIPOS, ANOS), f);
});

test("filtra por situação, risco, tipo e busca sem acento (todos os termos)", () => {
  const base = { status: "todas", risco: false, tipo: "", ano: "", q: "" };
  assert.ok(corresponde(linha("aprovada"), base));
  assert.ok(!corresponde(linha("aprovada"), { ...base, status: "perdida" }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, risco: true }));
  assert.ok(corresponde(linha("aprovada", { risco: true }), { ...base, risco: true }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, tipo: "emenda_finalidade" }));
  assert.ok(corresponde(linha("aprovada", { ano: "2025" }), { ...base, ano: "2025" }));
  assert.ok(!corresponde(linha("aprovada", { ano: "2025" }), { ...base, ano: "2026" }));
  assert.ok(corresponde(linha("aprovada", { ano: SEM_DATA }), { ...base, ano: SEM_DATA }));
  assert.ok(corresponde(linha("aprovada"), { ...base, q: "SAUDE ambulancia" }));
  assert.ok(corresponde(linha("aprovada"), { ...base, q: "12345/2024" }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, q: "ambulancia escola" }));
});

test("contagem dos chips respeita os outros filtros, não o de situação", () => {
  const linhas = [linha("aprovada", { risco: true }), linha("aprovada"), linha("perdida", { risco: true }), linha("perdida")];
  const c = contarPorStatus(linhas, { status: "perdida", risco: true, tipo: "", ano: "", q: "" });
  assert.equal(c.todas, 2);
  assert.equal(c.aprovada, 1);
  assert.equal(c.perdida, 1);
  assert.equal(c.oportunidade, 0);
});

test("ordem da lista: em risco, depois etapa em andamento, depois maior valor", () => {
  const v = (id, status_site, valor_total, em_risco = false) => ({ id, status_site, valor_total, em_risco });
  const ordem = ordenarLista([v("a", "perdida", 900), v("b", "aprovada", 10), v("c", "execucao", 5), v("d", "proposta", 1, true), v("e", "aprovada", 50), v("f", "oportunidade", null)]);
  assert.deepEqual(ordem.map((x) => x.id), ["d", "c", "e", "b", "f", "a"]);
});

test("ano da verba: proposta, senão adesão, senão sem data", () => {
  assert.equal(anoDaVerba({ prazos: { proposta: "2025-05-22", adesao: "2026-12-01" } }), "2025");
  assert.equal(anoDaVerba({ prazos: { adesao: "2026-11-30" } }), "2026");
  assert.equal(anoDaVerba({ prazos: { fim_vigencia: "2027-01-01" } }), SEM_DATA);
  assert.equal(anoDaVerba({}), SEM_DATA);
  assert.equal(anoDaVerba({ prazos: {} }), SEM_DATA);
});

test("o ano combina com os outros filtros e com a contagem dos chips", () => {
  const linhas = [linha("perdida", { ano: "2025" }), linha("perdida", { ano: "2026" }), linha("aprovada", { ano: "2025" })];
  const c = contarPorStatus(linhas, { status: "todas", risco: false, tipo: "", ano: "2025", q: "" });
  assert.deepEqual([c.todas, c.perdida, c.aprovada], [2, 1, 1]);
});
