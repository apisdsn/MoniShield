// Pemformat tampilan: padanan tWIB, dur, tRange, dLabel, fmt, dlt di dashboard_template.html (inv. §2.0).
// Fungsi murni: bahasa selalu lewat argumen `lang` ('id' | 'en'), supaya bisa diuji tanpa browser.
// Masukan waktu dari API sudah WIB dengan format lama: 'YYYY-MM-DD HH:MM' (menit) atau 'YYYY-MM-DD HH' (jam).

const BLN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const BLN_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const locale = (lang) => (lang === 'en' ? 'en-US' : 'id-ID');

/** Angka: 1.234 / 1,234; pecahan dibulatkan 3 digit seperti tabel lama. null -> '–' (U16). */
export function num(n, lang, digits) {
  if (n === null || n === undefined || Number.isNaN(n)) return '–';
  const v = digits === undefined ? +(+n).toFixed(3) : n;
  return v.toLocaleString(locale(lang), digits === undefined ? undefined : { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** '2026-09-28 06:03' -> '28 Sep 2026 06.03 WIB' (EN 06:03); '2026-09-28 06' -> '28 Sep 06.00'. */
export function tWIB(s, lang) {
  if (!s) return '-';
  const [d, hm = ''] = s.split(' ');
  const [y, m, dd] = d.split('-');
  const sep = lang === 'en' ? ':' : '.';
  const bulan = (lang === 'en' ? BLN_EN : BLN)[m - 1];
  return hm.length === 2 ? `${+dd} ${bulan} ${hm}${sep}00` : `${+dd} ${bulan} ${y} ${hm.replace(':', sep)} WIB`;
}

/** Tanggal saja: '2026-10-06' -> '6 Okt 2026'. */
export const dLabel = (d, lang) => tWIB(`${d} 00:00`, lang).replace(/ 00[.:]00 WIB$/, '');

/** Tanggal tanpa tahun: '2026-10-05 09:00' -> '5 Okt'. */
export function dShort(s, lang) {
  const [, m, dd] = s.slice(0, 10).split('-');
  return `${+dd} ${(lang === 'en' ? BLN_EN : BLN)[m - 1]}`;
}

/** Jam saja: '2026-10-05 09:00' -> '09.00' / '09:00'. */
export const hm = (s, lang) => s.slice(11, 16).replace(':', lang === 'en' ? ':' : '.');

/** Rentang waktu, digabung bila tanggalnya sama (lama). */
export function tRange(a, b, lang) {
  if (!a || !b) return tWIB(a || b, lang);
  if (a === b) return tWIB(a, lang);
  if (a.slice(0, 10) === b.slice(0, 10)) return `${tWIB(a, lang).replace(' WIB', '')} – ${hm(b, lang)} WIB`;
  return `${tWIB(a, lang)} – ${tWIB(b, lang)}`;
}

/** Rentang isi log untuk subjudul (U2): '5 Okt 09.00–6 Okt 00.59 WIB'; satu tanggal: '6 Okt 00.00–23.59 WIB'. */
export function logRange(a, b, lang) {
  if (!a || !b) return null;
  return a.slice(0, 10) === b.slice(0, 10)
    ? `${dShort(a, lang)} ${hm(a, lang)}–${hm(b, lang)} WIB`
    : `${dShort(a, lang)} ${hm(a, lang)}–${dShort(b, lang)} ${hm(b, lang)} WIB`;
}

/** Durasi dalam detik: '850 ms' / '2,35 dtk' / '1 mnt 52 dtk' (EN: s, min). */
export function dur(s, lang) {
  if (s === null || s === undefined) return '–';
  const en = lang === 'en';
  if (s < 1) return `${num(Math.round(s * 1000), lang)} ms`;
  if (s < 60) return `${(+s.toFixed(2)).toLocaleString(locale(lang))} ${en ? 's' : 'dtk'}`;
  return `${Math.floor(s / 60)} ${en ? 'min' : 'mnt'} ${Math.round(s % 60)} ${en ? 's' : 'dtk'}`;
}

/** Durasi dalam milidetik (bentuk data API). */
/** Waktu UTC dari server akun/ingest ('YYYY-MM-DD HH:MM[:SS]') -> 'YYYY-MM-DD HH:MM' WIB (UTC+7), untuk tWIB(). */
export function utcToWib(s) {
  if (!/^\d{4}-\d\d-\d\d[ T]\d\d:\d\d/.test(s || '')) return null;
  const d = new Date(s.slice(0, 16).replace(' ', 'T') + ':00Z');
  if (Number.isNaN(+d)) return null;
  return new Date(+d + 7 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
}

export const durMs = (ms, lang) => (ms === null || ms === undefined ? '–' : dur(ms / 1000, lang));

/** Ukuran berkas: 1.536 -> '1,5 KB'. */
export function bytes(n, lang) {
  if (n === null || n === undefined) return '–';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${(+n.toFixed(i ? 1 : 0)).toLocaleString(locale(lang))} ${u[i]}`;
}

/** Persen: 0,1234 -> '12,3%'. */
export const pct = (x, lang, digits = 1) =>
  x === null || x === undefined ? '–' : `${(x * 100).toLocaleString(locale(lang), { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;

/**
 * Perubahan vs folder sebelumnya (lama: dlt). Mengembalikan {kind, text, tone} atau null.
 * kind: 'up' | 'down' | 'same' | 'new' | 'incomplete'; tone: 'bad' | 'good' | null (warna bukan satu-satunya penanda: teks selalu ada).
 * `good`: naik itu baik. `comparable`: baris log folder sebelumnya >= 50 % folder ini (dihitung pemanggil).
 * `label`: nama pembanding selain tanggal folder (rata-rata N hari, 2026-10-07).
 */
export function delta(cur, prev, prevFolder, lang, { good = false, comparable = true, label = null } = {}) {
  if (prev === null || prev === undefined) return null;
  const en = lang === 'en', tgl = label || dLabel(prevFolder, lang);   // label: pembanding selain folder, mis. "rata-rata 7 hari"
  if (label && !comparable) return null;
  if (!comparable) return { kind: 'incomplete', tone: null, text: en ? `${tgl} log incomplete, not compared` : `Log ${tgl} tidak lengkap, tidak dibandingkan` };
  if (!prev) return cur ? { kind: 'new', tone: null, text: en ? `New (${tgl}: 0)` : `Baru (${tgl}: 0)`, short: en ? 'New' : 'Baru', rest: `${tgl}: 0` } : null;
  const p = ((cur - prev) / prev) * 100;
  if (Math.abs(p) < 0.5) return { kind: 'same', tone: null, text: en ? `≈ Same as ${tgl}` : `≈ Sama dengan ${tgl}` };
  const naik = p > 0;
  return {
    kind: naik ? 'up' : 'down',
    tone: naik !== good ? 'bad' : 'good',
    text: `${naik ? '▲' : '▼'} ${Math.abs(p).toFixed(0)}% vs ${tgl}`,
    short: `${naik ? '▲' : '▼'} ${Math.abs(p).toFixed(0)}%`,     // lencana di sebelah angka KPI (gaya referensi)
    rest: `vs ${tgl}`,
    spoken: en ? `${naik ? 'up' : 'down'} ${Math.abs(p).toFixed(0)}% vs ${tgl}` : `${naik ? 'naik' : 'turun'} ${Math.abs(p).toFixed(0)}% dibanding ${tgl}`,
  };
}

/** Nama sistem (layanan, pod, namespace, host, upstream, modul): selalu huruf kecil seperti di klaster, tidak ikut
 *  Capitalize Each Word teks antarmuka (keputusan pemilik 2026-10-06; lama: tc() mengkapitalkan nama layanan).
 *  Di elemen yang mengkapitalkan lewat CSS, bungkus dengan class "sys". */
export const sysName = (s) => String(s ?? '').toLowerCase();

/** Potong label (chart batang horizontal: 48, layar sempit 28). */
export const cut = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));
