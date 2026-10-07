# Berkontribusi ke MoniShield

## Branch

| Branch | Untuk | Masuk dari |
|---|---|---|
| `dev` | pengembangan sehari-hari; selalu bisa dijalankan | branch fitur (`feat/…`, `fix/…`) lewat pull request |
| `stg` | uji bersama / staging sebelum rilis | `dev` lewat pull request |
| `prd` | produksi (yang dipasang di VPS, `docs/07-deploy-vps.md`) | `stg` lewat pull request |

Alur: buat branch dari `dev` → pull request ke `dev` → setelah diuji di `dev`, PR `dev` → `stg` → setelah lolos uji
staging, PR `stg` → `prd`. Perbaikan darurat produksi: branch `fix/…` dari `prd`, PR ke `prd`, lalu gabungkan balik ke
`stg` dan `dev`. (`master` = salinan awal saat repo dibuat.)

Disarankan di GitHub → Settings → Branches: lindungi `stg` dan `prd` (wajib PR + CI hijau), dan jadikan `dev` branch bawaan.

## Pesan commit: Conventional Commits

Setiap commit memakai [Conventional Commits 1.0](https://www.conventionalcommits.org/id/v1.0.0/):

```
<tipe>[(<cakupan>)][!]: <ringkasan singkat>

[isi: apa dan mengapa, boleh beberapa paragraf]

[BREAKING CHANGE: … bila memutus kompatibilitas]
```

| Tipe | Kapan |
|---|---|
| `feat` | fitur baru untuk pengguna |
| `fix` | perbaikan bug |
| `docs` | dokumentasi saja |
| `style` | format kode tanpa mengubah perilaku |
| `refactor` | perubahan kode tanpa fitur/perbaikan baru |
| `perf` | percepatan |
| `test` | menambah/membetulkan uji |
| `build` | sistem build, dependensi, Docker |
| `ci` | GitHub Actions |
| `chore` | pemeliharaan lain |
| `revert` | membatalkan commit |

Cakupan yang lazim (huruf kecil): `api`, `ingest`, `kafka`, `s3`, `peta`, `ui`, `config`, `auth`, `alerts`, `docker`,
`deps`, `i18n`. Contoh:

```
feat(kafka): tulis pesan Rancher menjadi folder seperti ekspor S3
fix(peta): partikel berhenti saat tab disembunyikan
docs: panduan deploy VPS
build(deps)!: naikkan DuckDB ke 2.x

BREAKING CHANGE: berkas basis data lama harus di-ingest ulang.
```

Pemeriksaan otomatis:

```sh
git config core.hooksPath .githooks          # sekali per clone: commit yang tidak sesuai ditolak di komputer Anda
tools/cek_commit.sh origin/dev..HEAD          # periksa commit sebelum push
```

CI (`.github/workflows/ci.yml`) memeriksa pesan commit di setiap pull request dan push ke `dev`/`stg`/`prd`, lalu
menjalankan uji Python dan build tampilan.

## Sebelum membuat pull request

```sh
.venv/bin/pip install -e ".[test,s3,kafka]"
.venv/bin/python -m pytest -q                 # semua uji
(cd web && npm ci && npm run build) && node tools/cek_i18n.mjs   # build tampilan + kamus ID/EN lengkap
```

Di repo ini ±60 uji pembanding dengan sistem lama (`build_dashboard.py`, `dashboard.html`, folder log asli) otomatis
**dilewati**: berkas-berkas itu hanya ada di repo lama `apisdsn/dashboard-logging`. Uji lainnya harus lulus.

Jangan pernah meng-commit `.env` (berisi rahasia; sudah di `.gitignore`).
