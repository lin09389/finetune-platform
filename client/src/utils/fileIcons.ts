/**
 * File type icons for the workspace tree and editor tabs.
 * Returns a small string icon/emoji representing the file type.
 */

export interface FileIconConfig {
  icon: string;
  color: string;
}

const EXT_ICON_MAP: Record<string, FileIconConfig> = {
  // TypeScript
  ts:    { icon: 'TS', color: '#3178c6' },
  tsx:   { icon: 'TS', color: '#3178c6' },
  // JavaScript
  js:    { icon: 'JS', color: '#f0db4f' },
  jsx:   { icon: 'JS', color: '#f0db4f' },
  mjs:   { icon: 'JS', color: '#f0db4f' },
  cjs:   { icon: 'JS', color: '#f0db4f' },
  // Python
  py:    { icon: '🐍', color: '#3572A5' },
  pyw:   { icon: '🐍', color: '#3572A5' },
  // Web
  html:  { icon: '🌐', color: '#e34c26' },
  htm:   { icon: '🌐', color: '#e34c26' },
  css:   { icon: '🎨', color: '#264de4' },
  scss:  { icon: '🎨', color: '#c6538c' },
  sass:  { icon: '🎨', color: '#c6538c' },
  less:  { icon: '🎨', color: '#1d365d' },
  // Data
  json:  { icon: '{}', color: '#f1c40f' },
  jsonc: { icon: '{}', color: '#f1c40f' },
  yaml:  { icon: '📋', color: '#cb171e' },
  yml:   { icon: '📋', color: '#cb171e' },
  toml:  { icon: '📋', color: '#9c4221' },
  xml:   { icon: '📋', color: '#ff6600' },
  csv:   { icon: '📊', color: '#1d6f42' },
  // Docs
  md:    { icon: '📝', color: '#083fa1' },
  mdx:   { icon: '📝', color: '#083fa1' },
  txt:   { icon: '📄', color: '#8c8c8c' },
  rst:   { icon: '📄', color: '#8c8c8c' },
  pdf:   { icon: '📕', color: '#e03131' },
  // Config
  env:   { icon: '⚙️',  color: '#52c41a' },
  ini:   { icon: '⚙️',  color: '#52c41a' },
  conf:  { icon: '⚙️',  color: '#52c41a' },
  cfg:   { icon: '⚙️',  color: '#52c41a' },
  // Shell
  sh:    { icon: '$_', color: '#4EAA25' },
  bash:  { icon: '$_', color: '#4EAA25' },
  zsh:   { icon: '$_', color: '#4EAA25' },
  fish:  { icon: '$_', color: '#4EAA25' },
  bat:   { icon: '⬡',  color: '#4EAA25' },
  cmd:   { icon: '⬡',  color: '#4EAA25' },
  ps1:   { icon: '⬡',  color: '#012456' },
  // Systems
  rs:    { icon: '🦀', color: '#dea584' },
  go:    { icon: '🔵', color: '#00ADD8' },
  java:  { icon: '☕', color: '#f89820' },
  kt:    { icon: '🟣', color: '#7F52FF' },
  swift: { icon: '🍊', color: '#f05138' },
  c:     { icon: 'C',  color: '#555555' },
  h:     { icon: 'H',  color: '#555555' },
  cpp:   { icon: 'C++',color: '#f34b7d' },
  hpp:   { icon: 'C++',color: '#f34b7d' },
  cc:    { icon: 'C++',color: '#f34b7d' },
  cs:    { icon: 'C#', color: '#178600' },
  // Scripting
  rb:    { icon: '💎', color: '#701516' },
  php:   { icon: '🐘', color: '#4F5D95' },
  lua:   { icon: '🌙', color: '#000080' },
  r:     { icon: 'R',  color: '#198CE7' },
  // Images
  png:   { icon: '🖼️', color: '#8c8c8c' },
  jpg:   { icon: '🖼️', color: '#8c8c8c' },
  jpeg:  { icon: '🖼️', color: '#8c8c8c' },
  gif:   { icon: '🖼️', color: '#8c8c8c' },
  svg:   { icon: '🖼️', color: '#FFB13B' },
  webp:  { icon: '🖼️', color: '#8c8c8c' },
  ico:   { icon: '🖼️', color: '#8c8c8c' },
  // Build / Package
  lock:  { icon: '🔒', color: '#8c8c8c' },
  dockerfile: { icon: '🐳', color: '#2496ed' },
  // Fallback
  default: { icon: '📄', color: '#8c8c8c' },
};

// Special full-filename matches (e.g. Dockerfile, .env)
const FILENAME_ICON_MAP: Record<string, FileIconConfig> = {
  dockerfile:      { icon: '🐳', color: '#2496ed' },
  'docker-compose.yml':  { icon: '🐳', color: '#2496ed' },
  'docker-compose.yaml': { icon: '🐳', color: '#2496ed' },
  '.env':          { icon: '⚙️',  color: '#52c41a' },
  '.env.local':    { icon: '⚙️',  color: '#52c41a' },
  '.gitignore':    { icon: '🙈', color: '#8c8c8c' },
  '.gitattributes':{ icon: '🙈', color: '#8c8c8c' },
  'package.json':  { icon: '📦', color: '#f0db4f' },
  'package-lock.json': { icon: '🔒', color: '#8c8c8c' },
  'yarn.lock':     { icon: '🔒', color: '#2C8EBB' },
  'pnpm-lock.yaml':{ icon: '🔒', color: '#F69220' },
  'tsconfig.json': { icon: 'TS', color: '#3178c6' },
  'vite.config.ts':{ icon: '⚡', color: '#646CFF' },
  'vite.config.js':{ icon: '⚡', color: '#646CFF' },
  'requirements.txt': { icon: '📦', color: '#3572A5' },
  'makefile':      { icon: '🔧', color: '#427819' },
  'readme.md':     { icon: '📖', color: '#083fa1' },
  'readme':        { icon: '📖', color: '#083fa1' },
};

/**
 * Get file icon config for a given filename or path.
 */
export function getFileIcon(filename: string): FileIconConfig {
  const name = filename.replace(/\\/g, '/').split('/').pop() ?? filename;
  const nameLower = name.toLowerCase();

  // Check full filename first
  if (nameLower in FILENAME_ICON_MAP) {
    return FILENAME_ICON_MAP[nameLower]!;
  }

  // Fallback to extension
  const ext = nameLower.split('.').pop() ?? '';
  return EXT_ICON_MAP[ext] ?? EXT_ICON_MAP.default!;
}

/**
 * Whether the icon is a text badge (2-3 chars like "TS", "JS", "C++") vs emoji.
 */
export function isTextIcon(icon: string): boolean {
  return icon.length <= 3 && /^[A-Za-z#+_${}#!]+$/.test(icon.trim());
}
