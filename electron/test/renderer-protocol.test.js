'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { resolveRendererAsset } = require('../renderer-protocol');

test('app protocol serves assets and falls BrowserRouter routes back to index.html', () => {
  const root = path.resolve('C:\\app\\client\\dist');
  assert.equal(
    resolveRendererAsset(root, 'app://renderer/assets/main.js'),
    path.join(root, 'assets', 'main.js'),
  );
  assert.equal(resolveRendererAsset(root, 'app://renderer/agent'), path.join(root, 'index.html'));
  assert.equal(resolveRendererAsset(root, 'app://renderer/'), path.join(root, 'index.html'));
});

test('app protocol rejects foreign hosts, traversal and malformed encoding', () => {
  const root = path.resolve('C:\\app\\client\\dist');
  assert.equal(resolveRendererAsset(root, 'app://evil/index.html'), null);
  assert.equal(resolveRendererAsset(root, 'app://renderer/%2e%2e%2fsecret.txt'), null);
  assert.equal(resolveRendererAsset(root, 'app://renderer/%E0%A4%A'), null);
});
