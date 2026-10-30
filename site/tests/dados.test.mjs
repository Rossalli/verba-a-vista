import assert from "node:assert/strict";
import { test } from "node:test";

import { formatarData, formatarDataHora, formatarReais, url } from "../src/lib/dados.js";

test("data e hora no fuso de São Paulo", () => {
  assert.equal(formatarData("2026-10-29T18:19:41-03:00"), "29/10/2026");
  assert.equal(formatarDataHora("2026-10-29T18:19:41-03:00"), "29/10/2026 às 18:19");
  assert.equal(formatarDataHora("2026-10-30T01:05:00+00:00"), "29/10/2026 às 22:05"); // UTC vira horário local
});

test("reais a partir de centavos", () => {
  assert.equal(formatarReais(70075000), "R$ 700.750");
  assert.equal(formatarReais(0), "R$ 0");
});

test("url respeita o base do deploy", () => {
  assert.equal(url("/verbas/", "/"), "/verbas/");
  assert.equal(url("verbas/", "/verba-a-vista/"), "/verba-a-vista/verbas/");
  assert.equal(url("/", "/verba-a-vista/"), "/verba-a-vista/");
});
