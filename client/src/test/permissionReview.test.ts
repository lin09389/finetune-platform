import { describe, expect, it } from 'vitest';
import {
  extractCommand,
  extractFilePath,
  formatArgsPreview,
  permissionReviewTitle,
  sessionTrustHint,
  singleActionTitle,
  toolLabel,
} from '../agent/permission/permissionReview';

describe('permissionReview helpers', () => {
  it('labels coding tools in Chinese', () => {
    expect(toolLabel('edit_file')).toBe('修改文件');
    expect(toolLabel('write_file')).toBe('创建文件');
    expect(toolLabel('execute')).toBe('运行命令');
  });

  it('extracts workspace-relative paths', () => {
    expect(extractFilePath({ file_path: '/workspace/src/app.ts' })).toBe('src/app.ts');
    expect(extractFilePath({ path: '/workspace/.env' })).toBe('.env');
    expect(extractFilePath({})).toBeNull();
  });

  it('builds natural single-action titles', () => {
    expect(
      singleActionTitle({
        name: 'edit_file',
        args: { file_path: '/workspace/client/src/App.tsx' },
      }),
    ).toBe('允许修改 `client/src/App.tsx`？');
    expect(
      singleActionTitle({
        name: 'execute',
        args: { command: 'npm run typecheck' },
      }),
    ).toContain('npm run typecheck');
  });

  it('summarizes multi-action batches', () => {
    const title = permissionReviewTitle({
      actions: [
        { name: 'edit_file', args: { file_path: '/workspace/a.ts' } },
        { name: 'edit_file', args: { file_path: '/workspace/b.ts' } },
      ],
    });
    expect(title).toContain('2');
    expect(title).toContain('修改文件');
  });

  it('formats args preview without dumping huge blobs', () => {
    const preview = formatArgsPreview({
      file_path: '/workspace/x.ts',
      content: 'a'.repeat(400),
    });
    expect(preview).toContain('file_path');
    expect(preview!.length).toBeLessThan(400);
  });

  it('extracts shell commands', () => {
    expect(extractCommand({ command: 'pytest -q' })).toBe('pytest -q');
  });

  it('explains session trust after approve', () => {
    const hint = sessionTrustHint([
      { name: 'edit_file', args: {} },
      { name: 'write_file', args: {} },
    ]);
    expect(hint).toMatch(/本会话/);
    expect(hint).toMatch(/修改文件|创建文件/);
  });
});
