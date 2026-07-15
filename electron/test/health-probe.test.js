'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const test = require('node:test');
const { probeHttp } = require('../process-supervisor');

test('HTTP probe accepts renderer HTML but service identity requires 200 JSON match', async (context) => {
  const server = http.createServer((request, response) => {
    if (request.url === '/renderer') {
      response.writeHead(200, { 'content-type': 'text/html' });
      response.end('<html></html>');
      return;
    }
    if (request.url === '/health') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ status: 'ok', service: 'local-inference' }));
      return;
    }
    response.writeHead(404, { 'content-type': 'application/json' });
    response.end('{}');
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  context.after(() => new Promise((resolve) => server.close(resolve)));
  const { port } = server.address();
  assert.equal(await probeHttp(`http://127.0.0.1:${port}/renderer`), true);
  assert.equal(
    await probeHttp(
      `http://127.0.0.1:${port}/health`,
      2_000,
      (payload) => payload.status === 'ok' && payload.service === 'local-inference',
    ),
    true,
  );
  assert.equal(await probeHttp(`http://127.0.0.1:${port}/missing`), false);
  assert.equal(
    await probeHttp(`http://127.0.0.1:${port}/health`, 2_000, (payload) => payload.service === 'wrong'),
    false,
  );
});
