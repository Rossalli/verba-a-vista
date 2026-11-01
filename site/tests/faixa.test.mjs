// Regra inegociável: a faixa de independência aparece em TODA página gerada (spec §10), inclusive a 404.
// Roda depois do build (`npm run build && npm test`); sem `dist/` o teste é pulado.
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { test } from "node:test";

const DIST = resolve(process.cwd(), "dist");
const FAIXA = "Iniciativa cidadã independente. Não é o site oficial da Prefeitura de Neves Paulista.";

function htmls(pasta) {
  return readdirSync(pasta, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? htmls(join(pasta, e.name)) : e.name.endsWith(".html") ? [join(pasta, e.name)] : []));
}

test("toda página gerada tem a faixa de independência", { skip: !existsSync(DIST) && "sem dist/ (rode npm run build)" }, () => {
  const paginas = htmls(DIST);
  assert.ok(paginas.length >= 6, `esperava as páginas do site, achei ${paginas.length}`);
  const sem = paginas.filter((p) => !readFileSync(p, "utf-8").includes(FAIXA));
  assert.deepEqual(sem, []);
});

test("a página 404 existe, tem a faixa e não é indexada", { skip: !existsSync(DIST) && "sem dist/ (rode npm run build)" }, () => {
  const caminho = join(DIST, "404.html");
  assert.ok(existsSync(caminho), "dist/404.html não foi gerado");
  const html = readFileSync(caminho, "utf-8");
  assert.ok(html.includes(FAIXA));
  assert.ok(html.includes('name="robots" content="noindex"'));
});
