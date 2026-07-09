/**
 * Pure log-highlighting utilities for the training terminal stream.
 *
 * Extracted from TrainingDashboard.tsx so the logic is unit-testable without
 * loading React / recharts / CSS modules, and so the XSS escaping is enforced
 * in one audited place.
 *
 * SECURITY: `highlightLog` ALWAYS HTML-escapes the raw log content first, then
 * injects our own trusted `<span>` markup. The result is safe to render via
 * `dangerouslySetInnerHTML`. Never bypass `escapeHtml` when adding new rules.
 */

export interface LogTokenClasses {
  tokenMetric: string;
  tokenError: string;
  tokenWarn: string;
  tokenState: string;
  tokenTime: string;
}

/** Escape HTML special characters in untrusted text. */
export const escapeHtml = (str: string): string =>
  str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

/**
 * Highlight training log tokens (levels, timestamps, pipe-delimited levels) with
 * `<span>` wrappers. The raw log is HTML-escaped first, so any `<img onerror>`
 * or `<script>` in the log is rendered as inert text.
 */
export const highlightLog = (log: string, classes: LogTokenClasses): string =>
  escapeHtml(log)
    .replace(/\[METRIC\]/g, `<span class="${classes.tokenMetric}">[METRIC]</span>`)
    .replace(/\[ERROR\]/g, `<span class="${classes.tokenError}">[ERROR]</span>`)
    .replace(/\[WARN\]/g, `<span class="${classes.tokenWarn}">[WARN]</span>`)
    .replace(/\[STATE\]/g, `<span class="${classes.tokenState}">[STATE]</span>`)
    .replace(/\[VRAM\]/g, `<span class="${classes.tokenMetric}">[VRAM]</span>`)
    .replace(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/g, `<span class="${classes.tokenTime}">$1</span>`)
    .replace(/(\|\s*(?:INFO|WARNING|ERROR|DEBUG)\s*\|)/g, (match) => {
      if (match.includes('ERROR')) return `<span class="${classes.tokenError}">${match}</span>`;
      if (match.includes('WARN')) return `<span class="${classes.tokenWarn}">${match}</span>`;
      return `<span class="${classes.tokenState}">${match}</span>`;
    })
    .replace(/(\[\d{2}:\d{2}:\d{2}\])/g, `<span class="${classes.tokenTime}">$1</span>`);
