import { describe, expect, it } from 'vitest';

import { extractApiErrorMessage } from '../services/api';

describe('extractApiErrorMessage', () => {
  it('reads the unified backend error envelope', () => {
    expect(
      extractApiErrorMessage({
        response: {
          data: {
            error: {
              code: 'http_error',
              message: 'Agent part not found',
            },
          },
        },
      }),
    ).toBe('Agent part not found');
  });

  it('keeps compatibility with legacy detail responses', () => {
    expect(extractApiErrorMessage({ response: { data: { detail: 'project_path does not exist' } } })).toBe(
      'project_path does not exist',
    );
  });
});
