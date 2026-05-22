/**
 * Utilities for parsing unified-diff text into navigable hunks and
 * rebuilding partial diffs from hunk decisions.
 */

export type HunkStatus = 'pending' | 'accepted' | 'rejected';

export interface DiffHunk {
  /** Stable id: `${filePath}:${hunkIndex}` */
  id: string;
  /** Raw @@ … @@ header line */
  header: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  /** Body lines of this hunk (excluding the @@ header) */
  lines: string[];
  status: HunkStatus;
}

/** Parse a unified diff string into an array of DiffHunk objects. */
export function parseDiffHunks(filePath: string, diff: string): DiffHunk[] {
  const raw = diff.split('\n');
  const hunks: DiffHunk[] = [];
  let current: Omit<DiffHunk, 'id' | 'status'> | null = null;
  let hunkIndex = 0;

  for (const line of raw) {
    const m = line.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
    if (m) {
      if (current) {
        hunks.push({ id: `${filePath}:${hunkIndex}`, status: 'pending', ...current });
        hunkIndex++;
      }
      current = {
        header: line,
        oldStart: parseInt(m[1] ?? '0', 10),
        oldLines: m[2] != null ? parseInt(m[2], 10) : 1,
        newStart: parseInt(m[3] ?? '0', 10),
        newLines: m[4] != null ? parseInt(m[4], 10) : 1,
        lines: [],
      };
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) {
    hunks.push({ id: `${filePath}:${hunkIndex}`, status: 'pending', ...current });
  }
  return hunks;
}

/**
 * Extract the `--- / +++` file header from a unified diff.
 * Returns an empty string if none found.
 */
export function extractDiffFileHeader(diff: string): string {
  const m = diff.match(/^(---[^\n]*\n\+\+\+[^\n]*\n)/m);
  return m?.[1] ?? '';
}

/**
 * Rebuild a filtered diff containing only the accepted hunks.
 * Returns an empty string when nothing is accepted.
 */
export function buildPartialDiff(originalDiff: string, hunks: DiffHunk[]): string {
  const accepted = hunks.filter((h) => h.status === 'accepted');
  if (!accepted.length) return '';
  const header = extractDiffFileHeader(originalDiff);
  return header + accepted.map((h) => [h.header, ...h.lines].join('\n')).join('\n');
}

/**
 * Return the total number of accepted + pending hunks
 * (i.e. all hunks that should still be applied).
 */
export function countEffectiveHunks(hunks: DiffHunk[]): number {
  return hunks.filter((h) => h.status !== 'rejected').length;
}
