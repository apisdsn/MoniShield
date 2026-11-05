# 13 — Server and container metrics (stage 56)

Status: backend in progress (2026-11-05). The collector ([`12-collector.md`](12-collector.md)) can send the load of a server and of its
Docker containers next to the logs. This page is completed when the Servers page is built.

## 1. What is collected, and what never is

| Option | Platforms | Receiver | What |
|---|---|---|---|
| `host_metrics` | Linux, Windows, Docker hosts, Kubernetes nodes | `hostmetrics` | CPU utilization per state, memory (used and total), load average 1 minute, used and free space per mount point, network bytes sent and received |
| `container_metrics` | Docker hosts | `docker_stats` | per container: CPU %, memory used and limit, network bytes sent and received, restart count |

Never collected: the `process` and `processes` scrapers (process names and command lines are personal data), packets, errors,
connections, inodes, disk I/O. Only the metrics MoniShield uses are switched on in the written configuration, so a scrape is a few
dozen points. The collector scrapes every 30 seconds.

New collectors have the options on. A collector registered before this stage has both off: turn them on in the Collectors page, then run
`install.sh --upgrade` (Windows: `install.ps1 -Upgrade`) on the server.

## 2. The configuration (`domain/collector_config.py`)

- A `metrics` pipeline: receivers, `resourcedetection` (host name, OS type and description), `metricstransform/monishield` (keeps one
  CPU value per state), `batch/metrics` (no maximum size, so one scrape is never split) and the same `otlphttp/monishield` exporter with
  `metrics_endpoint` set to `<address>/api/collector/v1/metrics`. Same key, gzip, retry and disk queue as the logs.
- Linux, Docker and Windows: the `hostmetrics` receiver with the scrapers `cpu`, `memory` (with `system.memory.limit`), `load`,
  `filesystem` and `network`. File systems of type tmpfs, overlay, squashfs and the like and the mounts `/run`, `/snap`,
  `/var/lib/docker` and `/boot/efi` are left out; network devices `lo`, `veth*`, `br-*`, `docker*`, `cali*`, `flannel*`, `cni*` and
  `vxlan*` are left out. Windows has no mount excludes.
- Docker hosts: the `docker_stats` receiver on `unix:///var/run/docker.sock` (the collector already runs as root there).
- Kubernetes: the Helm values mount the node's root file system read-only at `/hostfs`, set `root_path` of the `hostmetrics` receiver and
  take the node name from the downward API (`K8S_NODE_NAME`, written to `k8s.node.name`). The chart's `hostMetrics` preset is not used:
  it also switches on the disk and network scrapers, and the network scraper of a pod reads the pod's own interface, not the node's. So a
  Kubernetes node has no network values.

Checked with the real `otelcol-contrib` 0.163.2 (`tools/fetch_otelcol.py`; the tests skip only when the binary is absent).

## 3. Docker API version

The `docker_stats` receiver of 0.163.2 talks to the Docker Engine with API version 1.44. If the collector's log says
`client version ... is too old`, the Docker Engine raised its minimum API version: add `api_version: "<version>"` to the `docker_stats`
block of `/etc/otelcol-contrib/config.yaml` by hand (MoniShield does not write it; an upgrade overwrites the file, so also ask for it to be added to the configuration writer).
