// Penyimpanan per browser untuk kenyamanan (bahasa, tema). Gagal simpan/baca tidak masalah (mode privat, dll.).
export function load(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
export function save(key, value) {
  try { localStorage.setItem(key, value); } catch { /* abaikan */ }
}
