// Per-browser storage for convenience (language, theme). Failing to save/read does not matter (private mode, etc.).
export function load(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
export function save(key, value) {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
}
