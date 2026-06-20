import { gzipSync } from 'node:zlib';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

const assetsDir = path.resolve('dist/assets');
const budgets = [
  { pattern: /^vendor-ui-.*\.js$/, maxGzipKb: 430 },
  { pattern: /^AgentWorkbenchRoute-.*\.js$/, maxGzipKb: 45 },
  { pattern: /^ChatNew-.*\.js$/, maxGzipKb: 100 },
];

const files = await readdir(assetsDir);
const failures = [];

for (const budget of budgets) {
  const matches = files.filter((file) => budget.pattern.test(file));
  if (matches.length !== 1) {
    failures.push(`${budget.pattern}: expected one asset, found ${matches.length}`);
    continue;
  }
  const file = matches[0];
  const bytes = await readFile(path.join(assetsDir, file));
  const gzipKb = gzipSync(bytes).byteLength / 1024;
  if (gzipKb > budget.maxGzipKb) {
    failures.push(`${file}: ${gzipKb.toFixed(1)} KiB gzip exceeds ${budget.maxGzipKb} KiB`);
  } else {
    console.log(`[bundle-budget] ${file}: ${gzipKb.toFixed(1)} / ${budget.maxGzipKb} KiB gzip`);
  }
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
}
