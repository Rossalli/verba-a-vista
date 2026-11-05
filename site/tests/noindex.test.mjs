// Pré-lançamento (D19): sem SITE_INDEXAR=true, TODA página gerada pede para não ser indexada; com ele, só a 404.
// Roda depois do build; sem `dist/` o teste é pulado.
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { test } from "node:test";

const DIST = resolve(process.cwd(), "dist");
const NOINDEX = 'name="robots" content="noindex"';

function htmls(pasta) {
  return readdirSync(pasta, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? htmls(join(pasta, e.name)) : e.name.endsWith(".html") ? [join(pasta, e.name)] : []));
}

test("o noindex segue a variável SITE_INDEXAR do build", { skip: !existsSync(DIST) && "sem dist/ (rode npm run build)" }, () => {
  const paginas = htmls(DIST);
  const com = paginas.filter((p) => readFileSync(p, "utf-8").includes(NOINDEX));
  const indexavel = process.env.SITE_INDEXAR === "true";
  if (indexavel) {
    assert.deepEqual(com.map((p) => p.endsWith("404.html")), [true]); // com a liberação, só a 404 continua sem indexar
  } else {
    assert.deepEqual(paginas.filter((p) => !com.includes(p)), []); // todas as páginas pedem noindex
  }
});
