# 13 — Server and container metrics (stages 56 and 61)

Status: done (stage 56 on 2026-11-05; stage 61, server details, load average and disk I/O, added to it). The collector ([`12-collector.md`](12-collector.md)) can send the load of a server and of its
Docker containers next to the logs; the Servers page shows it (section 10).

## 1. What is collected, and what never is

| Option | Platforms | Receiver | What |
|---|---|---|---|
| `host_metrics` | Linux, Windows, Docker hosts, Kubernetes nodes | `host_metrics` | CPU utilization per state and the number of logical CPUs, memory (used and total), load average 1, 5 and 15 minutes, used and free space per mount point, bytes read from and written to the disks, network bytes sent and received, uptime |
| `container_metrics` | Docker hosts | `docker_stats` | per container: CPU %, memory used and limit, network bytes sent and received, restart count |

Never collected: the `process` and `processes` scrapers (process names and command lines are personal data), packets, errors,
connections, inodes, disk operations and times (only the bytes read and written are kept). Only the metrics MoniShield uses are switched on in the written configuration, so a scrape is a few
dozen points. The collector scrapes every 30 seconds.

New collectors have the options on. A collector registered before this stage has both off: turn them on in the Collectors page, then run
`install.sh --upgrade` (Windows: `install.ps1 -Upgrade`) on the server.

A collector configured before stage 61 sends no load 5 and 15 minutes, core count, disk traffic or uptime. Its server page shows a muted line
asking for the upgrade, and the new tiles and charts stay empty until then: run `install.sh --upgrade` (Windows: `install.ps1 -Upgrade`, Kubernetes:
`helm upgrade` with the values file downloaded again). Nothing has to be changed in the Collectors page; the written configuration already holds the scrapers.

## 2. The configuration (`domain/collector_config.py`)

- A `metrics` pipeline: receivers, `resource_detection` (host name, OS type and description), `metrics_transform/monishield` (keeps one
  CPU value per state), `batch/metrics` (no maximum size, so one scrape is never split) and the same `otlp_http/monishield` exporter with
  `metrics_endpoint` set to `<address>/api/v1/collector/metrics`. Same key, gzip, retry and disk queue as the logs.
- Linux, Docker and Windows: the `host_metrics` receiver with the scrapers `cpu` (utilization and `system.cpu.logical.count`), `memory` (with
  `system.memory.limit`), `load` (1, 5 and 15 minutes), `filesystem`, `disk` (only `system.disk.io`: every other disk metric is switched off),
  `network` and `system` (only `system.uptime`). The disk scraper leaves out the devices `loop*`, `ram*`, `sr*`, `fd*`, `zram*`, `dm-*` and the
  partitions (`sdXN`, `nvmeXnYpZ`, `vdXN`, `xvdXN`), so the traffic of a disk is not counted twice; Windows has no device excludes. File systems of type tmpfs, overlay, squashfs and the like and the mounts `/run`, `/snap`,
  `/var/lib/docker` and `/boot/efi` are left out; network devices `lo`, `veth*`, `br-*`, `docker*`, `cali*`, `flannel*`, `cni*` and
  `vxlan*` are left out. Windows has no mount excludes.
- Docker hosts: the `docker_stats` receiver on `unix:///var/run/docker.sock` (the collector already runs as root there).
- Kubernetes: the Helm values mount the node's root file system read-only at `/hostfs`, set `root_path` of the `host_metrics` receiver and
  take the node name from the downward API (`K8S_NODE_NAME`, written to `k8s.node.name`). The chart's `hostMetrics` preset is not used:
  it also switches on the network scraper, which in a pod reads the pod's own interface, not the node's, and it does not let us choose the
  metrics. So a Kubernetes node has no network values. The disk scraper works there: with `root_path` it reads `/hostfs/proc/diskstats`.

The component names are the current ones (`otlp_http`, `host_metrics`, `resource_detection`, `metrics_transform`, `file_log`, `windows_event_log`): 0.163.2 still accepts the old
spellings but logs `alias is deprecated` for each at start. `install.sh --upgrade` fetches the new configuration from the server, so a collector installed with the old
names is moved to the new ones by the upgrade (the Docker host is told from `docker_stats:` and the container link folder, which did not change).

Checked with the real `otelcol-contrib` 0.163.2 (`tools/fetch_otelcol.py`; the tests skip only when the binary is absent).

## 3. Receiver and storage

`POST /api/v1/collector/metrics` (`interfaces/api/collector_logs.py`, next to the log receiver) uses the same key, content-type and
encoding checks, rate window, request slots, size limits before and after gunzip and 503 answers (`disk_full`, `busy`,
`storage_error`) as the log receiver, and the same `S4_COLLECTOR_*` limits and `S4_COLLECTOR_MAX_AGE_HOURS`.

- `domain/otlp_metrics.py` reads only the metric names in the table above (everything else is ignored and only counted, histograms
  too). A broken point is rejected with a reason (`malformed point`, `invalid time`, `too old`, `invalid name`, …) in the OTLP answer
  (`partialSuccess.rejectedDataPoints`); the collector does not retry it. Kept from the resource: host name (the node name on
  Kubernetes), OS description, container name and image name. Dropped: everything else, so no IP address, container id or process
  data is ever stored.
- Values: `cpu` = 100 x (1 - mean idle share); `mem_used`, `mem_total` (the `system.memory.limit` metric, else the sum of the states
  except `inactive`); `disk_used`, `disk_total` per mount point (at most 10, `/` first; total = used + free, like `df`, the
  reserved blocks are not counted); `net_rx`, `net_tx` in bytes per second summed over the devices; `load1`, `load5`, `load15`; `cores` (logical CPUs);
  `uptime` (seconds since boot); `disk_read`, `disk_write` in bytes per second summed over the disks. Containers: `cpu` as
  Docker reports it, `mem_used`, `mem_limit`, `net_rx`, `net_tx`, `restarts`.
- Network and disk values (`system.network.io`, `system.disk.io`) are counters. `application/metrics_feed.py` keeps the last sample of every device in memory and sends no rate for
  the first sample, after a counter reset or a changed start time, or after a gap of more than 5 minutes. A restart of MoniShield
  loses one point per series.
- `infrastructure/metrics_store.py`: its own file `<data dir>/metrics.duckdb`, one connection, one lock; tables `metric_point`,
  `metric_hour`, `metric_target`; a request inserts its points in one statement.

## 4. Roll-up and retention

`application/metrics_service.py` runs from a thread started and stopped in the app's `lifespan`, first 30 seconds after start and then
every 5 minutes:

1. **Roll-up.** Every finished hour becomes one row per series in `metric_hour` (average, maximum, number of points). The roll-up starts
   25 hours before the newest hour already there, so points that arrived late (a collector that was offline and sent its queue; at most
   `S4_COLLECTOR_MAX_AGE_HOURS` old) are counted; an hour rolled up again gets the same numbers plus the late points.
2. **Retention.** Points older than `S4_METRICS_RAW_DAYS` (default 7), hours and targets older than `S4_METRICS_HOUR_DAYS`
   (default 90) are deleted. The delete always follows the roll-up, so a point is never removed before it is in its hour.

Deleting a collector deletes its metrics too (the id may be given to a new collector).

## 5. Unusual values

`domain/metric_anomaly.py`, used by `POST /api/v1/servers`. For the CPU and the memory in use of every server and container:

- **current** = the mean of the last 10 minutes (at least 4 points);
- **baseline** = the hourly averages of the same hour of the day on each of the previous 7 days (a day counts when that hour has at least
  30 points); at least 5 days are needed, otherwise there is no verdict (a new server is never called unusual);
- **z** = (current - mean) / max(std, floor), with the sample standard deviation. Floor: CPU 2 percentage points; memory 2 % of the
  total (of the limit for a container) but at least 50 MB. The floor keeps a very steady server from turning small changes into big numbers;
- **unusual** when z is 3 or more (only higher than usual). The usual band shown is mean +- max(std, floor);
- **started**: the earliest 5-minute bucket of the last 6 hours after which every bucket stayed above mean + 3 x max(std, floor);
  none when the newest bucket is already back below it.

Disks have no z-score: a mount point that is 90 % full or more is listed under `disk_full`.

## 6. Read API

For every signed-in user (like the Pods page). Host and container names are site data, so both reads are POST: the parameters travel in the JSON body, which the web UI encrypts, and no host name stands in a URL, a proxy log or the network panel (there is no GET form).

- `POST /api/v1/servers` with `{range: 1h|24h|7d|30d}` (default 24h) -> `hosts` (collector id and name, platform, collector status `online` / `late` /
  `offline` / `revoked`, host, OS, last seen, number of containers, current cpu, mem_used, mem_total, load1, net_rx, net_tx, and the
  `disks` with used, total and percent; `os` is the short operating system name), `unusual` (worst first: kind, host, container, name, z, current, usual low and high, started) and
  `disk_full`. "Current" is the newest point of the last hour, else null.
- `POST /api/v1/servers/host` with `{cid, host, range}` -> the series for the charts (`cpu`, `mem_used` and `mem_total`, `disk_used` and `disk_total`
  of `/` or else the first mount point, `net_rx` and `net_tx`, `load1`, `load` = `{m1, m5, m15, cores}` and `disk_io` = `{read, write}` in bytes per second),
  `details` (`uptime_s`, `booted_at`, `cores`, `load` {m1, m5, m15}, `disk_io` {read, write}, `memory` {used, total}, `disk` {mount, used, total}, `containers`
  {running, stopped, restarts_24h} on Docker hosts and `null` elsewhere, `collector` {version, name, group, last_seen}, `os` {name, kernel, arch}; every part is
  `null` when the collector does not send it), `needs_upgrade` (true when the server sends metrics but none of load 5, uptime, disk traffic or cores:
  a configuration from before stage 61) and the `containers` (name, image, running = seen in the last 2
  minutes, last seen, current values, restarts, a memory sparkline of 24 hourly averages, and `logs_today`: the container's name is a service
  with log lines in today's folder of the collector source, as the sidebar lists it; when false the page shows "No log lines today" instead of the link to Raw Logs). Containers last seen before the range
  (at least 24 hours) are left out.
- Buckets: 1h = the points (every 30 s); 24h = 30-minute averages of the points; 7d = 3-hour and 30d = 12-hour averages of the hourly
  rows, weighted by their number of points, with the hour in progress added from the points. Times are ISO 8601 UTC with a Z.
- Errors: `invalid_parameter` (400) for a range that is not one of the four, `not_found` (404) for an unknown collector or server.

The two read calls are used by the Servers page through `api.js`, so their answers are encrypted like every other browser call
(`tests/test_wire_collectors.py`). The receiver `POST /api/v1/collector/metrics` is a machine endpoint used by `otelcol-contrib`: it is
protected by HTTPS on the ingest subdomain and the collector key, not by the page key.

## 7. Storage size (measured)

Simulated with `MetricsStore` on this code: 1 server (3 mount points) and 20 containers, one point of every value each 30 seconds for
one day. That is 132 points per request and 380,160 points per day. Random-walk values compress badly, so a real server should be
smaller.

| | Size |
|---|---|
| One day of points (`metric_point`) | 4.5 MB |
| The hourly rows of that day (`metric_hour`, 3,168 rows) | 0.5 MB |
| Steady state with the defaults (7 days of points + 90 days of hours) | about 31 MB + 47 MB = about 80 MB |
| Growth per month once the points are at their 7 days | about 16 MB (the hourly rows only) |

An insert of one request (132 points) takes about 33 ms; the roll-up of the whole day took 0.07 s. A server alone (no containers) is
about 12 points per request, so 20 times less. DuckDB does not shrink its file when rows are deleted, it reuses the space.

`metrics.duckdb` is part of the daily backup (`metrics.duckdb.gz`, next to the three source databases) and is put back by `monishield restore`.

## 8. Docker API version

The `docker_stats` receiver of 0.163.2 talks to the Docker Engine with API version 1.44. If the collector's log says
`client version ... is too old`, the Docker Engine raised its minimum API version: add `api_version: "<version>"` to the `docker_stats`
block of `/etc/otelcol-contrib/config.yaml` by hand (an upgrade overwrites the file, so the setting must then be added to the configuration writer in `domain/collector_config.py`).

## 9. Next

- Network values of a Kubernetes node (the pod's interface is not the node's) and the CPU architecture when the OS text does not name it.
- Kubernetes per-container metrics (`kubeletstats`) and node network values.
- Notifications for unusual values and almost-full disks.
- Endpoint and SSL checks.
- Process metrics: never (command lines are personal data).

## 10. The Servers page

`web/src/pages/Servers.svelte`, helpers in `web/src/servers.js` (tested by `tests/test_servers.mjs`), route `/servers`, sidebar entry in
the Analysis group after Raw Logs. No folder and no data source: the header hides the source switch. Reads `POST /api/v1/servers` and
`POST /api/v1/servers/host` through `api.js` every 30 seconds (the answers are encrypted like every browser call).

- **Banner**: `unusual` items (a container gets "Open Its Logs", Raw Logs of the collector source at `#pod=<host>&svc=<container>`; a
  server has no link) then `disk_full`; at most 3, then "and N more".
- **Cards**: the short OS name and the container count, CPU, memory (used of total), the disk of `/` (else the first mount point) and "Last data N seconds ago". Bar colour: teal below 70 %, amber 70 to 85, red
  from 85, with the number next to it. Status: the collector's own state first (Late, Offline, Revoked), then Disk Almost Full (90 %), Memory
  High and CPU High (70 %), No Data.
- **Server Details** (stage 61): eight tiles in a 4 x 2 grid, each with a label, a value and one line below (all on one line, an ellipsis and a
  `title` when too long): Uptime (since date and time in the configured zone), Load 1 / 5 / 15 min (of N cores), CPU (cores, architecture), Memory, Disk /,
  Containers (running, stopped and restarts in 24 hours; only on Docker hosts, then the last tile is two columns wide), Collector (version, name and
  group), Operating System (name, kernel). A missing value is a muted dash; with `needs_upgrade` one muted line names the upgrade command of the platform.
  The operating system text (`os.description`) is split by `domain/host_info.py` (Linux distribution and kernel, Windows name and build, any other
  text as the name). **Layout**: when one server is on show (a one-server site, or a group filter that leaves one), its card (one third) and the Server Details card
  (two thirds) sit side by side at one height; with several servers the cards keep their grid and groups, and the Server Details card of the chosen server
  sits below them, full width, 4 tiles per row (2 below 1100 px, 1 on phones).
- **Charts** (Chart.js, `lib/MetricChart.svelte`, with the pointer fix of `scale.js`): six cards in a 3-column grid (2 columns below 1180 px, 1 below 760 px):
  CPU, memory used and total, disk of `/` in percent, network received and sent, Load Average (1, 5 and 15 minutes and the dashed core count; above the dashed line
  the server is overloaded) and Disk I/O (read and written per second, all disks); times in the configured time zone (`axisLabel`). Every card has a
  title row, a legend row (always reserved), the chart and a one-line caption, so all have one height.
- **Containers table**: container, image, CPU, memory used of the limit, network in and out, restarts and a 24-hour memory sparkline; a container
  not seen for 2 minutes is greyed with "Last seen"; at 480 px and below a list of cards.
- **Groups**: hosts carry the `group` of their collector; cards sit under the group headings (alphabetical, No Group last) with the filter buttons.
- Sample data for the smoke test and for screenshots: `tools/seed_metrics.py` (seven servers in three groups and one without, one container
  with a jump in memory, one disk at 93 %, and one server on an older collector configuration that asks for the upgrade).
