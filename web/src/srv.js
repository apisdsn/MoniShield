// Text sent by the SERVER is English (error messages, ingest warnings, import job summaries, skipped-file reasons,
// trigger names, audit details, "Slow N s" labels). The UI is bilingual, so in Indonesian mode it is translated here,
// per known sentence fragment; unknown fragments are shown as they are (better than hiding them). Log data (application
// messages, business event names) is NOT translated (DRD §6.3).
// Rows stored before 2026-10-08 (old ingest warnings, job messages, audit details) are still Indonesian: in English
// mode they go through the LEGACY table below.
import { derived } from 'svelte/store';
import { lang, translate } from './i18n.js';

// [English pattern, Indonesian replacement] — applied in order to each "; "-separated fragment
const ID = [
  // derived trace label: "Slow 5.2 s"
  [/^Slow ([\d.,]+) s$/, 'Lambat $1 dtk'],
  // ingest / refdata warnings
  [/^refdata failed: /, 'refdata gagal: '],
  [/not downloaded and offline mode; skipped/, 'belum diunduh dan mode luring; dilewati'],
  [/not downloaded and offline mode/, 'belum diunduh dan mode luring'],
  [/not available \(MaxMind key empty or download failed\)/, 'tidak tersedia (kunci MaxMind kosong atau unduhan gagal)'],
  [/not available$/, 'tidak tersedia'],
  [/MAXMIND_ACCOUNT_ID\/MAXMIND_LICENSE_KEY not set in \.env/, 'MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY belum diisi di .env'],
  [/^IP location skipped$/, 'lokasi IP dilewati'],
  [/download failed/, 'gagal diunduh'], [/^using the old file if any$/, 'memakai berkas lama bila ada'],
  [/map files could not be built/, 'berkas peta gagal dibuat'],
  [/^refdata: land:/, 'refdata: daratan:'], [/^refdata: country borders:/, 'refdata: batas negara:'],
  [/^refdata: province borders:/, 'refdata: batas provinsi:'], [/^refdata: country labels:/, 'refdata: label negara:'],
  [/^refdata: Indonesian region labels:/, 'refdata: label wilayah Indonesia:'],
  [/^refdata: IP owner:/, 'refdata: pemilik:'], [/^refdata: IP location:/, 'refdata: lokasi:'],
  [/^folder (\S+) is in (.+) and (.+)$/, 'folder $1 ada di $2 dan $3'], [/^the second one is ignored$/, 'yang kedua diabaikan'],
  [/: unknown service '([^']+)', treated as Spring Boot$/, ": layanan tak dikenal '$1', diperlakukan sebagai Spring Boot"],
  [/: \.log and \.log\.gz contents DIFFER$/, ': isi .log dan .log.gz BERBEDA'], [/^the \.log is used$/, '.log yang dipakai'],
  [/: (\S+) differs from the (\S+) already processed$/, ': $1 berbeda dari $2 yang sudah diproses'], [/^re-processed$/, 'diproses ulang'],
  [/: FAILED to parse: /, ': GAGAL di-parse: '],
  [/: contains an error message from the log export tool, not logs \('([^']*)'\)$/, ": berisi pesan galat alat ekspor log, bukan log ('$1')"],
  [/^check the log delivery to S3$/, 'periksa pengiriman log ke S3'],
  [/^folder (\S+) also exists in the local log folder$/, 'folder $1 juga ada di folder log lokal'],
  [/^the local version is used when ingesting$/, 'saat ingest versi lokal yang dipakai'],
  [/^interrupted: the process stopped before the ingest finished$/, 'terputus: proses berhenti sebelum ingest selesai'],
  [/^data of unfinished folders is unchanged$/, 'data folder yang belum selesai tidak berubah'],
  [/: MaxMind key not set \(Configuration page or MAXMIND_ACCOUNT_ID\/MAXMIND_LICENSE_KEY in \.env\)$/,
    ': kunci MaxMind belum diisi (layar Konfigurasi atau MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY di .env)'],
  [/line (\d+): more than one login pattern matched/, 'baris $1: lebih dari satu pola login cocok'],
  [/^Another ingest is running\.$/, 'Ingest lain sedang berjalan.'],
  [/^Another ingest is taking too long to finish\.$/, 'Ingest lain tidak selesai-selesai.'],
  // Kafka messages that were skipped (reason) / could not be read
  [/^not JSON$/, 'bukan JSON'], [/^not a JSON object$/, 'bukan objek JSON'], [/^no 'log' field$/, "tanpa kolom 'log'"],
  [/^empty line$/, 'baris kosong'], [/^no kubernetes\.namespace_name\/container_name\/pod_name$/, 'tanpa kubernetes.namespace_name/container_name/pod_name'],
  [/^invalid namespace\/container\/pod name$/, 'nama namespace/container/pod tidak sah'],
  // import job summary
  [/^(\d+) objects would be fetched, (\d+) skipped/, '$1 objek akan diambil, $2 dilewati'],
  [/^(\d+) objects fetched, (\d+) skipped/, '$1 objek diambil, $2 dilewati'],
  [/, (\d+) \.gz extracted to \.log/, ', $1 .gz diekstrak menjadi .log'],
  [/^ingest #(\d+): (\d+) files changed$/, 'ingest #$1: $2 file berubah'],
  // skipped-file reasons (S3 import / upload)
  [/^not a log file$/, 'bukan file log'], [/^\.gz paired with \.log$/, '.gz berpasangan dengan .log'],
  [/^same as the previous download$/, 'sama dengan unduhan sebelumnya'], [/^duplicate$/, 'ganda'],
  [/^no date folder \(YYYY-MM-DD\) in its path$/, 'tidak ada folder tanggal (YYYY-MM-DD) di jalurnya'], [/^fill in the folder date$/, 'isi tanggal folder'],
  [/^not <date>\/<namespace>\/<service>\/<file>$/, 'bukan <tanggal>/<namespace>/<layanan>/<file>'],
  [/^folder (\S+) already exists in the main log folder \(that one is used\)$/, 'folder $1 sudah ada di folder log utama (yang itu yang dipakai)'],
  // ingest / import triggers
  [/^\(server start\)$/, '(mulai server)'], [/^\(daily\)$/, '(harian)'], [/^import #(\d+)$/, 'impor #$1'], [/^upload by (.+)$/, 'unggah oleh $1'],
  [/^\(machine token\)$/, '(token mesin)'], [/^\(automatic S3 sync\)$/, '(sinkron S3 otomatis)'], [/^\(kafka\)$/, '(kafka)'],
  // audit details
  [/^folder=all/, 'folder=semua'], [/ by (\S+)$/, ' oleh $1'], [/\((\d+) data files/, '($1 file data'], [/\((\d+) files\)/, '($1 file)'],
  [/^inbox deleted$/, 'kotak masuk dihapus'], [/^ignored\)?/, (m) => m.replace('ignored', 'diabaikan')],
  [/^(\d+) files, (\d+) bytes to the inbox: /, '$1 file, $2 byte ke kotak masuk: '],
  [/^check S3 for new folders/, 'periksa folder baru di S3'],
  [/^on: (.*) every (\d+) minutes/, 'aktif: $1 tiap $2 menit'], [/^off: (.*) every (\d+) minutes/, 'mati: $1 tiap $2 menit'],
  [/^temporary credentials pasted \(memory\)/, 'kredensial sementara ditempel (memori)'], [/^temporary credentials removed/, 'kredensial sementara dihapus'],
  [/ \(dry run\)/, ' (coba)'], [/^account locked$/, 'akun dikunci'],
  [/^role (\w+) -> (\w+)/, 'peran $1 -> $2'], [/^name$/, 'nama'], [/^activated$/, 'diaktifkan'], [/^deactivated$/, 'dinonaktifkan'],
  // user.update detail "<user>: name, role a -> b, activated"
  [/^(\S+): ((?:name|role \w+ -> \w+|activated|deactivated)(?:, (?:name|role \w+ -> \w+|activated|deactivated))*)$/,
    (m, u, list) => `${u}: ${list.split(', ').map((x) => ({ name: 'nama', activated: 'diaktifkan', deactivated: 'dinonaktifkan' })[x] || x.replace(/^role/, 'peran')).join(', ')}`],
];

// [Indonesian pattern, English replacement] — rows stored before the server switched to English
const LEGACY = [
  [/^Lambat ([\d.,]+) dtk$/, 'Slow $1 s'],
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
  [/^(\d+) objek akan diambil, (\d+) dilewati/, '$1 objects would be fetched, $2 skipped'],
  [/^(\d+) objek diambil, (\d+) dilewati/, '$1 objects fetched, $2 skipped'],
  [/, (\d+) \.gz diekstrak menjadi \.log/, ', $1 .gz extracted to .log'],
  [/^ingest #(\d+): (\d+) file berubah$/, 'ingest #$1: $2 files changed'],
  [/^bukan file log$/, 'not a log file'], [/^\.gz berpasangan dengan \.log$/, '.gz paired with .log'],
  [/^sama dengan unduhan sebelumnya$/, 'same as the previous download'], [/^ganda$/, 'duplicate'],
  [/^tidak ada folder tanggal \(YYYY-MM-DD\) di jalurnya$/, 'no date folder (YYYY-MM-DD) in its path'], [/^isi tanggal folder$/, 'fill in the folder date'],
  [/^bukan <tanggal>\/<namespace>\/<layanan>\/<file>$/, 'not <date>/<namespace>/<service>/<file>'],
  [/^folder (\S+) sudah ada di folder log utama \(yang itu yang dipakai\)$/, 'folder $1 already exists in the main log folder (that one is used)'],
  [/^\(mulai server\)$/, '(server start)'], [/^\(harian\)$/, '(daily)'], [/^impor #(\d+)$/, 'import #$1'], [/^unggah oleh (.+)$/, 'upload by $1'],
  [/^\(token mesin\)$/, '(machine token)'], [/^\(sinkron S3 otomatis\)$/, '(automatic S3 sync)'],
  [/^folder=semua/, 'folder=all'], [/ oleh (\S+)$/, ' by $1'], [/\((\d+) file data/, '($1 data files'], [/\((\d+) file\)/, '($1 files)'],
  [/^kotak masuk dihapus$/, 'inbox deleted'], [/^diabaikan\)?/, (m) => m.replace('diabaikan', 'ignored')],
  [/^(\d+) file, (\d+) byte ke kotak masuk: /, '$1 files, $2 bytes to the inbox: '],
  [/^periksa folder baru di S3/, 'check S3 for new folders'],
  [/^aktif: (.*) tiap (\d+) menit/, 'on: $1 every $2 minutes'], [/^mati: (.*) tiap (\d+) menit/, 'off: $1 every $2 minutes'],
  [/^kredensial sementara ditempel \(memori\)/, 'temporary credentials pasted (memory)'], [/^kredensial sementara dihapus/, 'temporary credentials removed'],
  [/ \(coba\)/, ' (dry run)'], [/^akun dikunci$/, 'account locked'],
  [/^peran (\w+) -> (\w+)/, 'role $1 -> $2'], [/^nama$/, 'name'], [/^diaktifkan$/, 'activated'], [/^dinonaktifkan$/, 'deactivated'],
];

function apply(table, s) {
  return s.split('; ').map((part) => {
    let out = part;
    for (const [re, rep] of table) out = out.replace(re, rep);
    return out;
  }).join('; ');
}

export const toId = (s) => apply(ID, s);
export const toEn = (s) => apply(LEGACY, s);

/** $srv(server text): translated per fragment to the UI language. */
export const srv = derived(lang, (l) => (s) => (typeof s !== 'string' || !s ? s : l === 'en' ? toEn(s) : toId(s)));

// Error messages that carry details (allowed buckets, limits, names): in Indonesian mode the whole sentence is translated
// so the details are kept; errors not listed here use the per-code dictionary. [English sentence, Indonesian]
const ERR_ID = [
  [/^Email cannot be changed here yet: the mail server is not set up\. Ask an admin\.$/, 'Email belum bisa diganti di sini: server email belum diatur. Minta bantuan admin.'],
  [/^Too many wrong codes\. Start again\.$/, 'Terlalu banyak kode salah. Ulangi dari awal.'],
  [/^The mail server rejected the username or password\.$/, 'Server email menolak nama pengguna atau kata sandi.'],
  [/^The mail server refused the recipient address\.$/, 'Server email menolak alamat penerima.'],
  [/^The mail server could not be reached or refused the message \((\w+)\)\.$/, 'Server email tidak bisa dihubungi atau menolak pesan ($1).'],
  [/^Port (\d+) does not match the security setting: use 465 with SSL\/TLS or 587 with STARTTLS \((\w+)\)\.$/,
    'Port $1 tidak cocok dengan pilihan keamanan: pakai 465 untuk SSL/TLS atau 587 untuk STARTTLS ($2).'],
  [/^The mail server \(SMTP\) is not set up: fill in Configuration → Mail server\.$/, 'Server email (SMTP) belum diatur: isi Konfigurasi → Server email.'],
  [/^Add an email address to your account \(Manage users\) or enter a recipient first\.$/, 'Tambahkan email ke akun Anda (Kelola user) atau isi penerima terlebih dahulu.'],
  [/^Invalid mail server address \(e\.g\. smtp\.example\.go\.id\)\.$/, 'Alamat server email tidak sah (contoh: smtp.contoh.go.id).'],
  [/^Mail server port must be 1–65535\.$/, 'Port server email harus 1–65535.'],
  [/^Sender must be an email address, e\.g\. .*$/, 'Pengirim harus alamat email, contoh: monishield@contoh.go.id atau MoniShield <monishield@contoh.go.id>.'],
  [/^Email is on but the SMTP server \/ port \/ sender \/ recipient is incomplete\.$/, 'Email aktif tetapi server / port / pengirim (bagian Server email) atau penerima belum lengkap.'],
  [/^Threshold for all services must look like 2:50 \(times the average : minimum increase\) or off\.$/, 'Ambang untuk semua layanan harus berbentuk 2:50 (kali rata-rata : naik minimal) atau off.'],
  [/^Threshold for all services: the factor must be above 1 and at most 100, the minimum increase 0 or more\.$/, 'Ambang untuk semua layanan: kelipatan harus di atas 1 dan paling banyak 100, naik minimal 0 atau lebih.'],
  [/^Threshold for (.+) must look like 2:50 \(times the average : minimum increase\) or off\.$/, 'Ambang untuk $1 harus berbentuk 2:50 (kali rata-rata : naik minimal) atau off.'],
  [/^Threshold for (.+): the factor must be above 1 and at most 100, the minimum increase 0 or more\.$/, 'Ambang untuk $1: kelipatan harus di atas 1 dan paling banyak 100, naik minimal 0 atau lebih.'],
  [/^"(.+)" is not a service name\.$/, '"$1" bukan nama layanan.'],
  [/^Database retention must be 0 \(keep forever\) or (\d+)–(\d+) days: .*$/,
    'Retensi database harus 0 (simpan selamanya) atau $1–$2 hari: dashboard membandingkan tiap folder dengan 7 folder sebelumnya.'],
  [/^Inbox retention must be 0 \(keep forever\) or (\d+)–(\d+) days\.$/, 'Retensi kotak masuk harus 0 (simpan selamanya) atau $1–$2 hari.'],
  [/^Retention cleanup is already running\.$/, 'Pembersihan retensi sedang berjalan.'],
  [/^This bucket is not allowed\. Allowed: (.*)$/, 'Bucket ini tidak diizinkan. Yang diizinkan: $1'],
  [/^This prefix is not allowed for bucket (\S+)\. Allowed: (.*)$/, 'Awalan ini tidak diizinkan untuk bucket $1. Yang diizinkan: $2'],
  [/^The last part of the link must be a valid YYYY-MM-DD date \(the folder name\), not "(.*)"\.$/,
    'Bagian terakhir tautan harus tanggal YYYY-MM-DD yang sah (nama folder), bukan "$1".'],
  [/^The link must look like (\S+) without "\.\.", "\." or double slashes\.$/, 'Tautan harus berbentuk $1 tanpa "..", "." atau garis miring ganda.'],
  [/^The link must look like (\S+)\.$/, 'Tautan harus berbentuk $1.'],
  [/^"(.*)" must look like s3:\/\/<bucket>\/<prefix>\/ \(a parent folder containing YYYY-MM-DD folders\)\.$/,
    '"$1" harus berbentuk s3://<bucket>/<awalan>/ (folder induk yang berisi folder YYYY-MM-DD).'],
  [/^Enter the PARENT folder without a date, e\.g\. (\S+) \(not folder (\S+)\)\.$/, 'Isi folder INDUK tanpa tanggal, mis. $1 (bukan folder $2).'],
  [/^(\S+) is not on the server allowlist \(S4_IMPORT_BUCKETS\)\. Allowed: (.*)$/, '$1 tidak ada di daftar izin server (S4_IMPORT_BUCKETS). Yang diizinkan: $2'],
  [/^No objects in (\S+)\.$/, 'Tidak ada objek di $1.'],
  [/^This prefix contains more than (\d+) objects; the limit is (\d+) log files\.$/, 'Awalan ini berisi lebih dari $1 objek; batasnya $2 file log.'],
  [/^(\d+) log files under this prefix exceed the limit of (\d+) objects\.$/, '$1 file log di awalan ini melebihi batas $2 objek.'],
  [/^Object (.+) (\d+) MB exceeds the limit of (\d+) MB per object\.$/, 'Objek $1 $2 MB melebihi batas $3 MB per objek.'],
  [/^Total download (\d+) MB exceeds the limit of (\d+) MB\.$/, 'Total unduhan $1 MB melebihi batas $2 MB.'],
  [/^The import exceeded the time limit of (\d+) minutes\.$/, 'Impor melewati batas waktu $1 menit.'],
  [/^Object (.+) is larger than listed; import cancelled\.$/, 'Objek $1 lebih besar dari daftar; impor dibatalkan.'],
  [/^Object (.+) downloaded (\d+) bytes, listed (\d+); import cancelled\.$/, 'Objek $1 terunduh $2 byte, di daftar $3; impor dibatalkan.'],
  [/^Object (.+) is not a complete gzip \(corrupt or truncated\); import cancelled\.$/, 'Objek $1 bukan gzip utuh (rusak atau terpotong); impor dibatalkan.'],
  [/^Extracted (.+) exceeds (\d+) MB; import cancelled\.$/, 'Hasil ekstrak $1 melebihi $2 MB; impor dibatalkan.'],
  [/^Unsafe object key, import cancelled: (.*)\.$/, 'Kunci objek tidak aman, impor dibatalkan: $1.'],
  [/^S3 denied access \(([^)]*)\): check the credentials and read permission on this bucket\/prefix\.$/,
    'S3 menolak akses ($1): periksa kredensial dan hak baca pada bucket/awalan ini.'],
  [/^S3: (\S+) \(bucket or object does not exist\)\.$/, 'S3: $1 (bucket atau objek tidak ada).'],
  [/^S3 answered with error (\S+)\.$/, 'S3 menjawab galat $1.'],
  [/^S3 is unreachable from the server \(([^)]*)\)\. .*$/, 'S3 tidak terjangkau dari server ($1). Periksa akses keluar server ke titik akhir S3 wilayah impor.'],
  [/^More than (\d+) files selected; limit is (\d+) log files per upload\.$/, 'Lebih dari $1 file dipilih; batasnya $2 file log per unggahan.'],
  [/^Invalid file name, upload cancelled: (.*)\.$/, 'Nama file tidak sah, unggahan dibatalkan: $1.'],
  [/^(.+) (\d+) MB exceeds the limit of (\d+) MB per file\.$/, '$1 $2 MB melebihi batas $3 MB per file.'],
  [/^(\d+) log files exceed the limit of (\d+) files per upload\.$/, '$1 file log melebihi batas $2 file per unggahan.'],
  [/^Total (\d+) MB exceeds the limit of (\d+) MB per upload\.$/, 'Total $1 MB melebihi batas $2 MB per unggahan.'],
  [/^(\d+) files not uploaded yet \(e\.g\. (.*)\)\.$/, '$1 file belum terunggah (mis. $2).'],
  [/^No log files in this folder can be uploaded\.(?: Example: (.*) — (.*)\.)?$/, (m, a, b) => 'Tidak ada file log yang bisa diunggah dari folder ini.' + (a ? ` Contoh: ${a} — ${toId(b)}.` : '')],
  [/^(.+) is larger than planned\.$/, '$1 lebih besar dari yang direncanakan.'],
  [/^(.+): received (\d+) bytes, planned (\d+)\.$/, '$1: diterima $2 byte, direncanakan $3.'],
  [/^Kafka broker unreachable from the server \(([^)]*)\)\. Check the broker address and firewall\.$/,
    'Broker Kafka tidak terjangkau dari server ($1). Periksa alamat broker dan firewall.'],
  [/^Kafka denied access \(([^)]*)\)\.$/, 'Kafka menolak akses ($1).'],
  [/^Topic "(.*)" does not exist \(or has never received messages\)\.$/, 'Topic "$1" tidak ada (atau belum pernah menerima pesan).'],
  [/^MaxMind is unreachable from the server \(([^)]*)\)\.$/, 'MaxMind tidak terjangkau dari server ($1).'],
  [/^MaxMind rejected the key \((\d+)\): check the Account ID and License key\.$/, 'MaxMind menolak kunci ($1): periksa Account ID dan License key.'],
  [/^MaxMind answered (\d+)\.$/, 'MaxMind menjawab $1.'],
  [/^Interval must be one of (.*) minutes\.$/, 'Jeda harus salah satu dari $1 menit.'],
  [/^Failed to send to (\S+): (.*)\.$/, 'Gagal mengirim ke $1: $2.'],
];

// Dictionary prefixes holding translations of API error codes, tried in order.
const ERR_KEYS = ['err.', 'imp.err.', 'adm.err.'];

/** Error text to display: EN = the server message (it carries the details); ID = the whole sentence translated when it
 *  carries details (ERR_ID), else the dictionary entry per error code, fallback the server message translated per fragment.
 *  Accepts ApiError ({status, code, message}), {code, message}, or "[code] message" text (import jobs). */
export const errText = derived(lang, (l) => (e) => {
  if (!e) return '';
  if (typeof e === 'string') {
    const m = /^\[([a-z_0-9]+)\] ([\s\S]*)$/.exec(e);
    e = m ? { code: m[1], message: m[2] } : { message: e };
  }
  if (e.status === 0 && e.code === 'network') return translate(l, 'state.error_network');
  if (l === 'en') return toEn(e.message || '') || (e.code ? `${translate('en', 'state.error_text')} (${e.code})` : translate('en', 'state.error_text'));
  const msg = e.message || '';
  for (const [re, rep] of ERR_ID) if (re.test(msg)) return msg.replace(re, rep);
  for (const p of ERR_KEYS) {
    const k = p + e.code;
    if (e.code && translate(l, k) !== k) return translate(l, k, { n: 12 });
  }
  return toId(e.message || '') || translate(l, 'state.error_text');
});
