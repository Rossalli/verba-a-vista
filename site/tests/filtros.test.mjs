import assert from "node:assert/strict";
import { test } from "node:test";

import { contarPorStatus, corresponde, lerFiltros, normalizar, ordenarLista, paraParametros } from "../src/lib/filtros.js";

const linha = (status, extra = {}) => ({ status, risco: false, tipo: "voluntaria", busca: normalizar("Ambulância Ministério da Saúde 12345/2024"), ...extra });
const TIPOS = ["voluntaria", "emenda_finalidade"];

test("normalizar tira acento e caixa", () => {
  assert.equal(normalizar("  Saúde É Ação "), "saude e acao");
  assert.equal(normalizar(null), "");
});

test("lê filtros da URL e ignora valores desconhecidos", () => {
  const f = lerFiltros(new URLSearchParams("status=perdida&risco=1&tipo=voluntaria&q=ambulancia"), TIPOS);
  assert.deepEqual(f, { status: "perdida", risco: true, tipo: "voluntaria", q: "ambulancia" });
  assert.deepEqual(lerFiltros(new URLSearchParams("status=xxx&risco=0&tipo=inventado"), TIPOS), { status: "todas", risco: false, tipo: "", q: "" });
});

test("a URL só leva o que difere do padrão, e ida e volta preserva o estado", () => {
  assert.equal(paraParametros({ status: "todas", risco: false, tipo: "", q: "  " }).toString(), "");
  const f = { status: "execucao", risco: true, tipo: "voluntaria", q: "quadra coberta" };
  assert.deepEqual(lerFiltros(paraParametros(f), TIPOS), f);
});

test("filtra por situação, risco, tipo e busca sem acento (todos os termos)", () => {
  const base = { status: "todas", risco: false, tipo: "", q: "" };
  assert.ok(corresponde(linha("aprovada"), base));
  assert.ok(!corresponde(linha("aprovada"), { ...base, status: "perdida" }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, risco: true }));
  assert.ok(corresponde(linha("aprovada", { risco: true }), { ...base, risco: true }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, tipo: "emenda_finalidade" }));
  assert.ok(corresponde(linha("aprovada"), { ...base, q: "SAUDE ambulancia" }));
  assert.ok(corresponde(linha("aprovada"), { ...base, q: "12345/2024" }));
  assert.ok(!corresponde(linha("aprovada"), { ...base, q: "ambulancia escola" }));
});

test("contagem dos chips respeita os outros filtros, não o de situação", () => {
  const linhas = [linha("aprovada", { risco: true }), linha("aprovada"), linha("perdida", { risco: true }), linha("perdida")];
  const c = contarPorStatus(linhas, { status: "perdida", risco: true, tipo: "", q: "" });
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
