// Teks yang dikirim SERVER dalam bahasa Indonesia (pesan galat, peringatan ingest, ringkasan job impor, alasan file
// dilewati, nama pemicu, rincian audit, label "Lambat N dtk") -> bahasa Inggris saat tampilan EN (permintaan pemilik
// 2026-10-07: "beberapa kalimat masih berbahasa Indonesia"). Server tetap satu bahasa (pesan lengkap untuk log dan
// CLI); penerjemahan dilakukan di sini, per potongan kalimat yang dikenal. Potongan yang tidak dikenal tampil apa adanya
// (lebih baik daripada hilang). Data log (pesan aplikasi, nama event bisnis) TIDAK diterjemahkan (DRD §6.3).
import { derived } from 'svelte/store';
import { lang, translate } from './i18n.js';

// [pola ID, pengganti EN] — diterapkan berurutan pada tiap potongan "; "-terpisah
const P = [
  // label agregat jejak (derive): "Lambat 5.2 dtk"
  [/^Lambat ([\d.,]+) dtk$/, 'Slow $1 s'],
  // peringatan ingest / refdata
  [/^refdata gagal: /, 'refdata failed: '],
  [/belum diunduh dan mode luring; dilewati/, 'not downloaded and offline mode; skipped'],
  [/belum diunduh dan mode luring/, 'not downloaded and offline mode'],
  [/tidak tersedia \(kunci MaxMind kosong atau unduhan gagal\)/, 'not available (MaxMind key empty or download failed)'],
  [/tidak tersedia$/, 'not available'],
  [/MAXMIND_ACCOUNT_ID\/MAXMIND_LICENSE_KEY belum diisi di \.env/, 'MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY not set in .env'],
  [/^lokasi IP dilewati$/, 'IP location skipped'],
  [/gagal diunduh/, 'download failed'], [/^memakai berkas lama bila ada$/, 'using the old file if any'],
  [/berkas peta gagal dibuat/, 'map files could not be built'],
  [/^refdata: daratan:/, 'refdata: land:'], [/^refdata: batas negara:/, 'refdata: country borders:'],
  [/^refdata: batas provinsi:/, 'refdata: province borders:'], [/^refdata: label negara:/, 'refdata: country labels:'],
  [/^refdata: label wilayah Indonesia:/, 'refdata: Indonesian region labels:'],
  [/^refdata: pemilik:/, 'refdata: IP owner:'], [/^refdata: lokasi:/, 'refdata: IP location:'],
  [/^folder (\S+) ada di (.+) dan (.+)$/, 'folder $1 is in $2 and $3'], [/^yang kedua diabaikan$/, 'the second one is ignored'],
  [/: layanan tak dikenal '([^']+)', diperlakukan sebagai Spring Boot$/, ": unknown service '$1', treated as Spring Boot"],
  [/: isi \.log dan \.log\.gz BERBEDA$/, ': .log and .log.gz contents DIFFER'], [/^\.log yang dipakai$/, 'the .log is used'],
  [/: (\S+) berbeda dari (\S+) yang sudah diproses$/, ': $1 differs from the $2 already processed'], [/^diproses ulang$/, 're-processed'],
  [/: GAGAL di-parse: /, ': FAILED to parse: '],
  [/: berisi pesan galat alat ekspor log, bukan log \('([^']*)'\)$/, ": contains an error message from the log export tool, not logs ('$1')"],
  [/^periksa pengiriman log ke S3$/, 'check the log delivery to S3'],
  [/^folder (\S+) juga ada di folder log lokal$/, 'folder $1 also exists in the local log folder'],
  [/^saat ingest versi lokal yang dipakai$/, 'the local version is used when ingesting'],
  // ringkasan job impor
  [/^(\d+) objek akan diambil, (\d+) dilewati/, '$1 objects would be fetched, $2 skipped'],
  [/^(\d+) objek diambil, (\d+) dilewati/, '$1 objects fetched, $2 skipped'],
  [/, (\d+) \.gz diekstrak menjadi \.log/, ', $1 .gz extracted to .log'],
  [/^ingest #(\d+): (\d+) file berubah$/, 'ingest #$1: $2 files changed'],
  // alasan file dilewati (impor S3 / unggah)
  [/^bukan file log$/, 'not a log file'], [/^\.gz berpasangan dengan \.log$/, '.gz paired with .log'],
  [/^sama dengan unduhan sebelumnya$/, 'same as the previous download'], [/^ganda$/, 'duplicate'],
  [/^tidak ada folder tanggal \(YYYY-MM-DD\) di jalurnya$/, 'no date folder (YYYY-MM-DD) in its path'], [/^isi tanggal folder$/, 'fill in the folder date'],
  [/^bukan <tanggal>\/<namespace>\/<layanan>\/<file>$/, 'not <date>/<namespace>/<service>/<file>'],
  [/^folder (\S+) sudah ada di folder log utama \(yang itu yang dipakai\)$/, 'folder $1 already exists in the main log folder (that one is used)'],
  // pemicu ingest / impor
  [/^\(mulai server\)$/, '(server start)'], [/^impor #(\d+)$/, 'import #$1'], [/^unggah oleh (.+)$/, 'upload by $1'],
  [/^\(token mesin\)$/, '(machine token)'], [/^\(sinkron S3 otomatis\)$/, '(automatic S3 sync)'],
  // rincian audit
  [/^folder=semua/, 'folder=all'], [/ oleh (\S+)$/, ' by $1'], [/\((\d+) file data/, '($1 data files'], [/\((\d+) file\)/, '($1 files)'],
  [/^kotak masuk dihapus$/, 'inbox deleted'], [/^diabaikan\)?/, (m) => m.replace('diabaikan', 'ignored')],
  [/^(\d+) file, (\d+) byte ke kotak masuk: /, '$1 files, $2 bytes to the inbox: '],
  [/^periksa folder baru di S3/, 'check S3 for new folders'],
  [/^aktif: (.*) tiap (\d+) menit/, 'on: $1 every $2 minutes'], [/^mati: (.*) tiap (\d+) menit/, 'off: $1 every $2 minutes'],
  [/^kredensial sementara ditempel \(memori\)/, 'temporary credentials pasted (memory)'], [/^kredensial sementara dihapus/, 'temporary credentials removed'],
  [/ \(coba\)/, ' (dry run)'], [/^akun dikunci$/, 'account locked'],
  [/^peran (\w+) -> (\w+)/, 'role $1 -> $2'], [/^nama$/, 'name'], [/^diaktifkan$/, 'activated'], [/^dinonaktifkan$/, 'deactivated'],
];

function toEn(s) {
  return s.split('; ').map((part) => {
    let out = part;
    for (const [re, rep] of P) out = out.replace(re, rep);
    return out;
  }).join('; ');
}

/** $srv(teks dari server): apa adanya di ID, diterjemahkan per potongan di EN. */
export const srv = derived(lang, (l) => (s) => (l === 'en' && typeof s === 'string' && s ? toEn(s) : s));

// Prefiks kamus yang memuat terjemahan kode galat API (EN), dicoba berurutan.
const ERR_KEYS = ['err.', 'imp.err.', 'adm.err.'];

/** Pesan galat untuk ditampilkan: ID = pesan server (memuat rincian); EN = kamus per kode, cadangan pesan umum + kode.
 *  Menerima ApiError ({status, code, message}), objek {code, message}, atau teks "[kode] pesan" (job impor). */
export const errText = derived(lang, (l) => (e) => {
  if (!e) return '';
  if (typeof e === 'string') {
    const m = /^\[([a-z_0-9]+)\] ([\s\S]*)$/.exec(e);
    e = m ? { code: m[1], message: m[2] } : { message: e };
  }
  if (e.status === 0 && e.code === 'network') return translate(l, 'state.error_network');
  if (l !== 'en') return e.message || translate(l, 'state.error_text');
  for (const p of ERR_KEYS) {
    const k = p + e.code;
    if (e.code && translate('en', k) !== k) return translate('en', k, { n: 12 });
  }
  return e.code ? `${translate('en', 'state.error_text')} (${e.code})` : toEn(e.message || '') || translate('en', 'state.error_text');
});
