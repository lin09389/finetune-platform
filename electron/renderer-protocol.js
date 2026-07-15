'use strict';

const path = require('node:path');

function resolveRendererAsset(rendererRoot, requestUrl) {
  try {
    const url = new URL(requestUrl);
    if (url.protocol !== 'app:' || url.hostname !== 'renderer') return null;
    const decoded = decodeURIComponent(url.pathname);
    let relative = decoded.replace(/^\/+/, '');
    if (!relative || path.extname(relative) === '') relative = 'index.html';
    const candidate = path.resolve(rendererRoot, relative);
    const relation = path.relative(rendererRoot, candidate);
    if (relation.startsWith('..') || path.isAbsolute(relation)) return null;
    return candidate;
  } catch (_error) {
    return null;
  }
}

module.exports = { resolveRendererAsset };
