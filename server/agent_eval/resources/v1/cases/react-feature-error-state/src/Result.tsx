export function Result({ error }: { error?: Error }) { return error ? null : <span>Ready</span>; }
