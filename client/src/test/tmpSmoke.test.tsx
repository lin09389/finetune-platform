// tmpSmoke.test.tsx - Temporary smoke test for type checking
import { describe, expect, it } from 'vitest';

export const tmpSmoke = (): string => 'tmp smoke test';

describe('tmpSmoke', () => {
  it('exports a string', () => {
    expect(tmpSmoke()).toBe('tmp smoke test');
  });
});
