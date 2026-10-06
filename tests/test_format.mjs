// node --test tests/test_format.mjs  (dari folder v2/)
// Pemformat v2 vs contoh di inventaris §2.0 dan keluaran fungsi lama di dashboard_template.html.
import test from 'node:test';
import assert from 'node:assert/strict';
import { tWIB, dur, durMs, tRange, dLabel, num, logRange, delta, bytes, pct, titleCase, cut } from '../web/src/format.js';

test('waktu WIB seperti lama', () => {
  assert.equal(tWIB('2026-09-28 06:03', 'id'), '28 Sep 2026 06.03 WIB');
  assert.equal(tWIB('2026-09-28 06:03', 'en'), '28 Sep 2026 06:03 WIB');
  assert.equal(tWIB('2026-09-28 06', 'id'), '28 Sep 06.00');
  assert.equal(tWIB('2026-09-28 06', 'en'), '28 Sep 06:00');
  assert.equal(tWIB('2026-10-05 09:00', 'id'), '5 Okt 2026 09.00 WIB');
  assert.equal(tWIB('2026-08-17 23:59', 'id'), '17 Agu 2026 23.59 WIB');
  assert.equal(tWIB('2026-08-17 23:59', 'en'), '17 Aug 2026 23:59 WIB');
  assert.equal(tWIB(null, 'id'), '-');
});

test('tanggal folder', () => {
  assert.equal(dLabel('2026-10-06', 'id'), '6 Okt 2026');
  assert.equal(dLabel('2026-10-06', 'en'), '6 Oct 2026');
  assert.equal(dLabel('2026-05-01', 'id'), '1 Mei 2026');
});

test('durasi seperti lama', () => {
  assert.equal(dur(0.85, 'id'), '850 ms');
  assert.equal(dur(2.35, 'id'), '2,35 dtk');
  assert.equal(dur(2.35, 'en'), '2.35 s');
  assert.equal(dur(112, 'id'), '1 mnt 52 dtk');
  assert.equal(dur(112, 'en'), '1 min 52 s');
  assert.equal(dur(5, 'id'), '5 dtk');
  assert.equal(dur(0.0004, 'id'), '0 ms');
  assert.equal(durMs(2350, 'id'), '2,35 dtk');
  assert.equal(durMs(1250, 'en'), '1.25 s');
});

test('rentang waktu digabung bila tanggal sama', () => {
  assert.equal(tRange('2026-09-28 06:03', '2026-09-28 07:15', 'id'), '28 Sep 2026 06.03 – 07.15 WIB');
  assert.equal(tRange('2026-09-28 06:03', '2026-09-28 07:15', 'en'), '28 Sep 2026 06:03 – 07:15 WIB');
  assert.equal(tRange('2026-09-28 06:03', '2026-09-28 06:03', 'id'), '28 Sep 2026 06.03 WIB');
  assert.equal(tRange('2026-09-28 23:50', '2026-09-29 00:10', 'id'), '28 Sep 2026 23.50 WIB – 29 Sep 2026 00.10 WIB');
});

test('rentang isi log untuk subjudul (U2)', () => {
  assert.equal(logRange('2026-10-05 09:00', '2026-10-06 00:59', 'id'), '5 Okt 09.00–6 Okt 00.59 WIB');
  assert.equal(logRange('2026-10-05 09:00', '2026-10-06 00:59', 'en'), '5 Oct 09:00–6 Oct 00:59 WIB');
  assert.equal(logRange('2026-10-06 00:00', '2026-10-06 23:59', 'id'), '6 Okt 00.00–23.59 WIB');
  assert.equal(logRange(null, null, 'id'), null);
});

test('angka', () => {
  assert.equal(num(124822, 'id'), '124.822');
  assert.equal(num(124822, 'en'), '124,822');
  assert.equal(num(0.12345, 'id'), '0,123');
  assert.equal(num(null, 'id'), '–');
  assert.equal(num(0, 'id'), '0');
  assert.equal(bytes(1536, 'id'), '1,5 KB');
  assert.equal(bytes(500, 'en'), '500 B');
  assert.equal(pct(0.1234, 'id'), '12,3%');
  assert.equal(pct(0.1234, 'en'), '12.3%');
});

test('perubahan vs folder sebelumnya (dlt lama: empat bentuk)', () => {
  assert.deepEqual(delta(64, 100, '2026-10-05', 'id'), { kind: 'down', tone: 'good', text: '▼ 36% vs 5 Okt 2026', spoken: 'turun 36% dibanding 5 Okt 2026' });
  assert.equal(delta(150, 100, '2026-10-05', 'id').tone, 'bad');                       // error naik = buruk
  assert.equal(delta(150, 100, '2026-10-05', 'id', { good: true }).tone, 'good');       // request naik = baik
  assert.equal(delta(100.2, 100, '2026-10-05', 'id').text, '≈ Sama dengan 5 Okt 2026');
  assert.equal(delta(100.2, 100, '2026-10-05', 'en').text, '≈ Same as 5 Oct 2026');
  assert.equal(delta(5, 0, '2026-10-05', 'id').text, 'Baru (5 Okt 2026: 0)');
  assert.equal(delta(0, 0, '2026-10-05', 'id'), null);
  assert.equal(delta(5, 3, '2026-10-05', 'id', { comparable: false }).text, 'Log 5 Okt 2026 tidak lengkap, tidak dibandingkan');
  assert.equal(delta(5, null, null, 'id'), null);
});

test('label', () => {
  assert.equal(titleCase('nginx-ingress-controller'), 'Nginx-Ingress-Controller');
  assert.equal(titleCase('om-be-simpel-loop'), 'Om-Be-Simpel-Loop');
  assert.equal(cut('a'.repeat(60), 48).length, 48);
  assert.equal(cut('pendek', 48), 'pendek');
});
