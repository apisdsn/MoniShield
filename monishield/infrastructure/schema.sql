-- Skema DuckDB (TRD §2). Aman dijalankan berulang: semua CREATE memakai IF NOT EXISTS / OR REPLACE.
-- Waktu disimpan UTC; WIB (+7 jam) dihitung saat menurunkan agregat. `folder` = nama folder ekspor.
-- Tabel mentah berkunci logis (file_id, line_no) TANPA PRIMARY KEY: indeks kunci pada puluhan juta baris
-- memperlambat muat massal; keunikan dijaga pola hapus-lalu-muat per file dan diperiksa uji ingest.

-- ------------------------------------------------------------------ kendali (TRD §2.1)
CREATE SEQUENCE IF NOT EXISTS seq_file_id;
CREATE SEQUENCE IF NOT EXISTS seq_run_id;

CREATE TABLE IF NOT EXISTS ingest_file (
    file_id       INTEGER PRIMARY KEY,
    relpath       VARCHAR NOT NULL UNIQUE,   -- tanpa akhiran .gz (identitas logis)
    source_ext    VARCHAR NOT NULL,          -- '.log' | '.log.gz': berkas yang dibaca
    folder        DATE NOT NULL,
    ns            VARCHAR NOT NULL,
    service       VARCHAR NOT NULL,
    pod           VARCHAR NOT NULL,
    size_bytes    BIGINT NOT NULL,
    mtime_ns      BIGINT NOT NULL,
    sha256        VARCHAR NOT NULL,          -- isi setelah didekompresi
    lines         BIGINT NOT NULL,
    err           INTEGER NOT NULL,
    warn          INTEGER NOT NULL,
    corrupt_lines INTEGER NOT NULL,
    status        VARCHAR NOT NULL,          -- ok | empty | corrupt | failed
    rules_version INTEGER NOT NULL,
    ingested_at   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS file_counter (
    file_id INTEGER NOT NULL,
    kind    VARCHAR NOT NULL,                -- level | biz | mail
    key     VARCHAR NOT NULL,
    n       BIGINT NOT NULL,
    PRIMARY KEY (file_id, kind, key)
);

CREATE TABLE IF NOT EXISTS folder_state (
    folder          DATE PRIMARY KEY,
    derived_at      TIMESTAMP,
    rules_version   INTEGER,
    range_start_utc TIMESTAMP,
    range_end_utc   TIMESTAMP,
    lines           BIGINT,
    files           INTEGER,
    files_empty     INTEGER,
    files_corrupt   INTEGER
);

CREATE TABLE IF NOT EXISTS ip_info (
    ip          VARCHAR PRIMARY KEY,
    asn         INTEGER,
    cc          VARCHAR,
    org         VARCHAR,
    is_private  BOOLEAN,
    city        VARCHAR,
    region      VARCHAR,
    country     VARCHAR,
    lat         DOUBLE,
    lon         DOUBLE,
    geo_checked BOOLEAN,
    asn_db_date DATE,
    geo_db_date DATE
);

CREATE TABLE IF NOT EXISTS ingest_run (
    run_id        INTEGER PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    status        VARCHAR NOT NULL,
    files_seen    INTEGER,
    files_changed INTEGER,
    message       VARCHAR
);

-- ------------------------------------------------------------------ mentah (TRD §2.2)
CREATE TABLE IF NOT EXISTS nginx_access (
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    ts_utc         TIMESTAMP NOT NULL,
    ip             VARCHAR NOT NULL,
    method         VARCHAR NOT NULL,
    path           VARCHAR NOT NULL,         -- path + query, mentah
    path_key       VARCHAR NOT NULL,
    status         SMALLINT NOT NULL,
    bytes          BIGINT NOT NULL,
    ua             VARCHAR NOT NULL,         -- utuh; pemotongan 90/100/120 saat menurunkan agregat
    request_time   DOUBLE NOT NULL,
    upstream       VARCHAR NOT NULL,         -- tanpa awalan; '-' bila kosong
    request_id     VARCHAR,                  -- NULL bila ekor baris tidak cocok
    pod_final      VARCHAR NOT NULL,         -- pod yang menjawab; '-' bila tidak ada
    up_addrs       VARCHAR[],                -- NULL bila ekor tidak berisi 4 bagian
    up_statuses    VARCHAR[],
    attack_cat     VARCHAR,
    is_uptime_kuma BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS nginx_error (
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    service       VARCHAR NOT NULL,          -- nginx-ingress-controller | om-fe-inhouse
    ts_utc        TIMESTAMP NOT NULL,
    level         VARCHAR NOT NULL,
    message       VARCHAR NOT NULL,
    upstream_host VARCHAR,
    kind          VARCHAR,
    request       VARCHAR
);

CREATE TABLE IF NOT EXISTS fe_access (
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    ts_utc   TIMESTAMP NOT NULL,
    ip       VARCHAR NOT NULL,               -- entri pertama X-Forwarded-For
    method   VARCHAR NOT NULL,
    path     VARCHAR NOT NULL,
    path_key VARCHAR NOT NULL,
    status   SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS sl_event (       -- tanpa kolom waktu: log simpel-loop tidak bercap waktu
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    level       VARCHAR NOT NULL,
    request_id  VARCHAR,
    event       VARCHAR,
    method      VARCHAR NOT NULL,            -- str(method): 'None' bila tidak ada, seperti kunci di sistem lama
    path        VARCHAR NOT NULL,
    path_key    VARCHAR NOT NULL,
    status      SMALLINT NOT NULL,
    ip          VARCHAR,                     -- NULL pada event tanpa ipAddress
    duration_ms DOUBLE NOT NULL,
    failed      BOOLEAN NOT NULL,
    err_name    VARCHAR,
    err_message VARCHAR
);

CREATE TABLE IF NOT EXISTS spring_line (
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    service         VARCHAR NOT NULL,
    ts_utc          TIMESTAMP NOT NULL,
    level           VARCHAR NOT NULL,
    thread          VARCHAR NOT NULL,
    logger          VARCHAR NOT NULL,
    restart_app     VARCHAR,
    restart_seconds DOUBLE,
    jwt_expired_ms  BIGINT,
    refresh_expired BOOLEAN NOT NULL,
    pdf_template    VARCHAR,                 -- diisi pada baris 'Jasper template path'
    pdf_failed      BOOLEAN,
    login_kind      VARCHAR,                 -- fail | lock | ok
    login_account   VARCHAR,
    login_ip        VARCHAR
);

CREATE TABLE IF NOT EXISTS coredns_error (
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    level   VARCHAR NOT NULL,
    domain  VARCHAR NOT NULL,
    rtype   VARCHAR NOT NULL,
    message VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS log_message (    -- satu baris per pemanggilan add_msg() sistem lama
    file_id INTEGER NOT NULL, line_no INTEGER NOT NULL, folder DATE NOT NULL,
    service VARCHAR NOT NULL,
    level   VARCHAR NOT NULL,                -- ERROR | WARN | EXC | level nginx huruf besar
    msg_key VARCHAR NOT NULL,                -- 'LEVEL | pesan ternormalisasi'
    raw     VARCHAR                          -- baris asli 600 karakter, hanya kemunculan pertama kunci dalam file
);

-- ------------------------------------------------------------------ agregat per folder (TRD §2.3)
CREATE TABLE IF NOT EXISTS agg_service (
    folder DATE, service VARCHAR,
    lines BIGINT, err BIGINT, warn BIGINT, err_http BIGINT, err_log BIGINT,
    files INTEGER, files_empty INTEGER, files_corrupt INTEGER,
    requests BIGINT, n4xx BIGINT, n5xx BIGINT, ip_unique BIGINT, users_ok BIGINT,
    PRIMARY KEY (folder, service));
CREATE TABLE IF NOT EXISTS agg_hour (
    folder DATE, service VARCHAR, hour_wib TIMESTAMP, total BIGINT, err BIGINT,
    PRIMARY KEY (folder, service, hour_wib));
CREATE TABLE IF NOT EXISTS agg_status (
    folder DATE, service VARCHAR, status SMALLINT, n BIGINT,
    PRIMARY KEY (folder, service, status));
CREATE TABLE IF NOT EXISTS agg_endpoint (
    folder DATE, service VARCHAR, key VARCHAR,
    requests BIGINT, n4xx BIGINT, n5xx BIGINT,
    dur_n BIGINT, dur_avg DOUBLE, dur_max DOUBLE, p50 DOUBLE, p95 DOUBLE, p99 DOUBLE,
    PRIMARY KEY (folder, service, key));
CREATE TABLE IF NOT EXISTS agg_endpoint_error (
    folder DATE, service VARCHAR, status SMALLINT, key VARCHAR, n BIGINT,
    PRIMARY KEY (folder, service, status, key));
CREATE TABLE IF NOT EXISTS agg_ip (
    folder DATE, service VARCHAR, ip VARCHAR, requests BIGINT, n4xx BIGINT, ua_first_4xx VARCHAR,
    PRIMARY KEY (folder, service, ip));
CREATE TABLE IF NOT EXISTS agg_upstream (
    folder DATE, upstream VARCHAR, requests BIGINT, n5xx BIGINT,
    PRIMARY KEY (folder, upstream));
CREATE TABLE IF NOT EXISTS agg_ua (
    folder DATE, ua90 VARCHAR, n BIGINT,
    PRIMARY KEY (folder, ua90));
CREATE TABLE IF NOT EXISTS agg_level (
    folder DATE, service VARCHAR, level VARCHAR, n BIGINT,
    PRIMARY KEY (folder, service, level));
CREATE TABLE IF NOT EXISTS agg_message (
    folder DATE, service VARCHAR, msg_key VARCHAR, level VARCHAR, n BIGINT, sample_raw VARCHAR,
    PRIMARY KEY (folder, service, msg_key));
CREATE TABLE IF NOT EXISTS agg_slow (
    folder DATE, seq INTEGER, duration_ms DOUBLE, key VARCHAR, status SMALLINT,
    PRIMARY KEY (folder, seq));
CREATE TABLE IF NOT EXISTS agg_attack_url (
    folder DATE, category VARCHAR, method_path VARCHAR,
    hits BIGINT, ip_count BIGINT, top_ip VARCHAR, status_counts MAP(VARCHAR, INTEGER),
    sizes BIGINT[], upstreams VARCHAR[], ua_first VARCHAR, first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, category, method_path));
CREATE TABLE IF NOT EXISTS agg_attack_ip (
    folder DATE, ip VARCHAR,
    hits BIGINT, cats MAP(VARCHAR, INTEGER), status_counts MAP(VARCHAR, INTEGER),
    ua_top VARCHAR, first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, ip));
CREATE TABLE IF NOT EXISTS agg_attack_hour (
    folder DATE, hour_wib TIMESTAMP, n BIGINT,
    PRIMARY KEY (folder, hour_wib));
CREATE TABLE IF NOT EXISTS agg_login_ip (
    folder DATE, ip VARCHAR, fail BIGINT, lock BIGINT, ok BIGINT, accounts VARCHAR[],
    first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, ip));
CREATE TABLE IF NOT EXISTS agg_login_hour (
    folder DATE, hour_wib TIMESTAMP, fail BIGINT, ok BIGINT,
    PRIMARY KEY (folder, hour_wib));
CREATE TABLE IF NOT EXISTS agg_account (
    folder DATE, account VARCHAR, fail BIGINT, lock BIGINT, ok BIGINT,
    fail_ips VARCHAR[], ok_ips VARCHAR[], flags VARCHAR[],
    first_wib TIMESTAMP, last_wib TIMESTAMP, notes VARCHAR[],
    PRIMARY KEY (folder, account));
CREATE TABLE IF NOT EXISTS agg_incident (
    folder DATE, seq INTEGER, start_wib TIMESTAMP, end_wib TIMESTAMP, n BIGINT,
    upstreams MAP(VARCHAR, INTEGER), statuses MAP(VARCHAR, INTEGER),
    PRIMARY KEY (folder, seq));
CREATE TABLE IF NOT EXISTS agg_c401 (
    folder DATE, ip VARCHAR, key VARCHAR, n BIGINT, peak_per_min BIGINT,
    first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, ip, key));
CREATE TABLE IF NOT EXISTS agg_uk_hour (
    folder DATE, hour_wib TIMESTAMP, n BIGINT, fail BIGINT,
    PRIMARY KEY (folder, hour_wib));
CREATE TABLE IF NOT EXISTS agg_uk_target (
    folder DATE, target VARCHAR, n BIGINT,
    PRIMARY KEY (folder, target));
CREATE TABLE IF NOT EXISTS agg_flow (
    folder DATE, ip VARCHAR, upstream VARCHAR, pod VARCHAR, n BIGINT,
    PRIMARY KEY (folder, ip, upstream, pod));
CREATE TABLE IF NOT EXISTS agg_pod (
    folder DATE, upstream VARCHAR, addr VARCHAR, attempts BIGINT, n5xx BIGINT,
    PRIMARY KEY (folder, upstream, addr));
CREATE TABLE IF NOT EXISTS agg_retry (
    folder DATE, upstream VARCHAR, addr_first VARCHAR, status_first VARCHAR, n BIGINT,
    PRIMARY KEY (folder, upstream, addr_first, status_first));
CREATE TABLE IF NOT EXISTS agg_corr (
    folder DATE PRIMARY KEY, matched BIGINT, total BIGINT);
CREATE TABLE IF NOT EXISTS agg_trace (
    folder DATE, ip VARCHAR, status SMALLINT, error VARCHAR, key VARCHAR,
    n BIGINT, url VARCHAR, upstream VARCHAR, ua VARCHAR,
    first_wib TIMESTAMP, last_wib TIMESTAMP, max_ms DOUBLE,
    PRIMARY KEY (folder, ip, status, error, key));
CREATE TABLE IF NOT EXISTS agg_biz (
    folder DATE, metric VARCHAR, n BIGINT,
    PRIMARY KEY (folder, metric));
CREATE TABLE IF NOT EXISTS agg_mail (
    folder DATE, kind VARCHAR, n BIGINT,
    PRIMARY KEY (folder, kind));
CREATE TABLE IF NOT EXISTS agg_activity (
    folder DATE, key VARCHAR, n BIGINT,
    PRIMARY KEY (folder, key));
CREATE TABLE IF NOT EXISTS agg_jwt (
    folder DATE, service VARCHAR, bucket VARCHAR, n BIGINT,
    PRIMARY KEY (folder, service, bucket));
CREATE TABLE IF NOT EXISTS agg_report (
    folder DATE, template VARCHAR, ok BIGINT, fail BIGINT,
    PRIMARY KEY (folder, template));

-- ------------------------------------------------------------------ view
CREATE OR REPLACE VIEW v_upstream_error AS
    SELECT folder, file_id, line_no, ts_utc, kind, upstream_host, request
    FROM nginx_error
    WHERE upstream_host IS NOT NULL AND service = 'nginx-ingress-controller';

CREATE OR REPLACE VIEW v_restart AS
    SELECT s.folder, s.service, s.ts_utc, f.pod, s.restart_app, s.restart_seconds
    FROM spring_line s JOIN ingest_file f USING (file_id)
    WHERE s.restart_app IS NOT NULL;

CREATE OR REPLACE VIEW v_attack_cat AS
    SELECT folder, category, sum(hits) AS n FROM agg_attack_url GROUP BY folder, category;

CREATE OR REPLACE VIEW v_dns AS
    SELECT folder, key AS domain, requests AS n FROM agg_endpoint WHERE service = 'coredns';

-- ---------------------------------------------------------------- Tahap 21: deteksi serangan OWASP CRS, kategori CAPEC (TRD §4.6)
-- Kolom lama attack_cat dan tabel agg_attack_* TETAP (aturan lama, uji kesetaraan). Klasifikasi CRS dihitung saat menurunkan
-- agregat dari path dan User-Agent yang tersimpan (tanpa parse ulang). ADD COLUMN IF NOT EXISTS: berlaku juga untuk database lama.
ALTER TABLE nginx_access ADD COLUMN IF NOT EXISTS crs_rules INTEGER[];      -- ID aturan CRS yang kena; NULL = bukan serangan
ALTER TABLE nginx_access ADD COLUMN IF NOT EXISTS capec VARCHAR;            -- ID CAPEC aturan berkeparahan tertinggi
ALTER TABLE nginx_access ADD COLUMN IF NOT EXISTS crs_attack VARCHAR;       -- keluarga serangan CRS (sqli, xss, rce, ...)
ALTER TABLE nginx_access ADD COLUMN IF NOT EXISTS crs_severity TINYINT;     -- 1..3 (tag tampilan)
ALTER TABLE nginx_access ADD COLUMN IF NOT EXISTS crs_score SMALLINT;       -- skor anomali (>= ambang 5)
ALTER TABLE folder_state ADD COLUMN IF NOT EXISTS crs_version VARCHAR;      -- versi CRS + tingkat paranoia saat agregat CRS diturunkan

CREATE TABLE IF NOT EXISTS agg_crs_url (
    folder DATE, category VARCHAR, method_path VARCHAR,          -- category = ID CAPEC
    attack VARCHAR, severity TINYINT, rules INTEGER[],
    hits BIGINT, ip_count BIGINT, top_ip VARCHAR, status_counts MAP(VARCHAR, INTEGER),
    sizes BIGINT[], upstreams VARCHAR[], ua_first VARCHAR, first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, category, method_path));
CREATE TABLE IF NOT EXISTS agg_crs_ip (
    folder DATE, ip VARCHAR,
    hits BIGINT, cats MAP(VARCHAR, INTEGER), max_severity TINYINT, status_counts MAP(VARCHAR, INTEGER),
    ua_top VARCHAR, first_wib TIMESTAMP, last_wib TIMESTAMP,
    PRIMARY KEY (folder, ip));
CREATE TABLE IF NOT EXISTS agg_crs_hour (
    folder DATE, hour_wib TIMESTAMP, n BIGINT,
    PRIMARY KEY (folder, hour_wib));

-- Folder yang dihapus admin dari dashboard tetapi filenya masih ada di folder log (hanya-baca) atau kotak masuk:
-- ingest/sinkronisasi melewatinya sampai dipulihkan. Kolom sengaja bukan "folder" agar tidak ikut terhapus oleh forget().
CREATE TABLE IF NOT EXISTS folder_ignored (
    ignored_folder VARCHAR PRIMARY KEY,
    by_user        VARCHAR,
    at_utc         TIMESTAMP
);
