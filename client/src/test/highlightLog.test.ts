import { describe, expect, it } from 'vitest';

import { escapeHtml, highlightLog, type LogTokenClasses } from '../pages/Training/components/highlightLog';

const classes: LogTokenClasses = {
  tokenMetric: 'tok-metric',
  tokenError: 'tok-error',
  tokenWarn: 'tok-warn',
  tokenState: 'tok-state',
  tokenTime: 'tok-time',
};

describe('escapeHtml', () => {
  it('escapes all HTML special characters', () => {
    expect(escapeHtml('<img src=x onerror=alert(1)>')).toBe(
      '&lt;img src=x onerror=alert(1)&gt;',
    );
    expect(escapeHtml(`<script>alert("x")</script>`)).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    );
    expect(escapeHtml(`a & b 'c' "d"`)).toBe('a &amp; b &#39;c&#39; &quot;d&quot;');
  });

  it('leaves safe text unchanged', () => {
    expect(escapeHtml('loss=0.5 [METRIC] step=10')).toBe('loss=0.5 [METRIC] step=10');
  });
});

describe('highlightLog (XSS regression)', () => {
  it('renders injected <img onerror> as inert text, never as live markup', () => {
    const out = highlightLog('<img src=x onerror=alert(1)>', classes);
    // No live <img> tag may remain; the payload must appear escaped.
    expect(out).not.toMatch(/<img[^>]*onerror/);
    expect(out).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });

  it('renders injected <script> as inert text', () => {
    const out = highlightLog('<script>alert(1)</script>', classes);
    expect(out).not.toMatch(/<script>/i);
    expect(out).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
  });

  it('still highlights level tokens on safe log lines', () => {
    const out = highlightLog('[ERROR] something broke', classes);
    expect(out).toContain('<span class="tok-error">[ERROR]</span>');
    expect(out).toContain('something broke');
  });

  it('highlights timestamps without breaking on attacker-controlled content', () => {
    const out = highlightLog('2024-01-02 03:04:05 [WARN] <b>evil</b>', classes);
    expect(out).toContain('<span class="tok-time">2024-01-02 03:04:05</span>');
    expect(out).toContain('<span class="tok-warn">[WARN]</span>');
    // The raw <b> must be escaped, not passed through.
    expect(out).not.toMatch(/<b>evil<\/b>/);
    expect(out).toContain('&lt;b&gt;evil&lt;/b&gt;');
  });

  it('escapes ampersands that could form entities', () => {
    const out = highlightLog('loss &amp; metric', classes);
    expect(out).toContain('&amp;amp;');
    expect(out).not.toMatch(/<span[^>]*>&amp;<\/span>/);
  });
});
