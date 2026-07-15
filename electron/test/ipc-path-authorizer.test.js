'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { IpcPathAuthorizer } = require('../ipc-path-authorizer');
const { sanitizeFilters } = require('../desktop-ipc');

test('file authorization only grants the exact picker-selected canonical file', async () => {
  const authorizer = new IpcPathAuthorizer({
    platform: 'win32',
    realpath: async (value) => path.resolve(value),
  });
  const selected = await authorizer.grantSelectedFile('C:\\project\\data.jsonl');
  assert.equal(
    (await authorizer.assertReadableFile('c:\\PROJECT\\data.jsonl')).toLowerCase(),
    selected.toLowerCase(),
  );
  await assert.rejects(
    authorizer.assertReadableFile('C:\\project\\secret.env'),
    (error) => error.code === 'FILE_ACCESS_DENIED',
  );
});

test('directory authorization does not grant sibling or parent directories', async () => {
  const authorizer = new IpcPathAuthorizer({
    platform: 'win32',
    realpath: async (value) => path.resolve(value),
  });
  await authorizer.grantSelectedDirectory('C:\\project\\workspace');
  await authorizer.assertOpenableDirectory('C:\\project\\workspace');
  await assert.rejects(
    authorizer.assertOpenableDirectory('C:\\project'),
    (error) => error.code === 'DIRECTORY_ACCESS_DENIED',
  );
});

test('dialog filters are bounded and extensions cannot retain a leading dot', () => {
  const filters = sanitizeFilters([{ name: 'Dataset', extensions: ['.jsonl', '.json'] }]);
  assert.deepEqual(filters, [{ name: 'Dataset', extensions: ['jsonl', 'json'] }]);
});
