# DRD — Design requirements for the SIMPEL4 log dashboard (v2)

Look and interaction of v2. Based on: [`00-inventaris.md`](00-inventaris.md) (contents of each tab), [`01-prd.md`](01-prd.md)
(priorities and assumptions), the CSS in `dashboard_template.html`, and screenshots of `dashboard.html` built on
2026-10-06 (Overview, IP Map, Security and Availability tabs and the ingress nginx page at 1440 px width; IP Map
at 390 px; all in the dark theme, Indonesian language).

Data and technical requirements (schema, endpoints, code component structure) are not part of this document.

**Principle**: the old look is good and familiar to its users. v2 keeps its layout, colours and
terminology; the only things that change are those that are (a) broken on narrow screens, (b) unreadable, (c) required by the PRD, or
(d) unavoidable because data is now loaded per tab. All changes are listed in [§10](#10-changes-from-the-old-look).

> **Revision 2026-10-06 (Stage 1 of the plan).** Aligned with the owner's decisions and [`03-trd.md`](03-trd.md):
> the dashboard is opened from many computers with a **login** (two roles: admin and user; a user sees the whole
> dashboard), the **phone view is done seriously**, odd definitions are fixed, and there is **import from S3**.
> Main additions: the Sign in, Change password, Manage users, and Ingest & import screens (§3.11), session behaviour (§6.9), and
> changes U28–U32 (§10).

References: "inv. §x" = inventory, "F/B/T/A/P-nn" = numbers in the PRD. **ASSUMPTIONS** are summarized in [§11](#11-assumptions-and-open-questions).

Not yet seen directly: the light theme and English (judged from the CSS and the dictionary, not from screenshots).

---

## 1. Navigation and page list

### 1.1 Structure

One application, one screen: a fixed frame (navigation + header) with changing content. There are no nested pages.

```
Analysis                         Services (those in the selected folder)
├─ Overview            /         ├─ Nginx-Ingress-Controller
├─ IP Map                        ├─ Coredns
├─ Trends    (across folders)    ├─ Om-Be-Appsmanager
├─ Security     [N IP]           ├─ Om-Be-Referensi
├─ Root Causes                   ├─ Om-Be-Report
├─ Availability                  ├─ Om-Be-Simpel-Loop
├─ Pods                          └─ Om-Fe-Inhouse
├─ Business                         (badge = error count)
└─ Request Tracing
```

Order, names, and badges are the same as in the old system (inv. §2.0). Nine analysis tabs + one service page
template = **10 data pages**. This sidebar is the same for admin and user.

Outside the sidebar there are **4 account and admin screens** (§3.11), reached from the Sign in screen or from the user menu in the
header:

```
(not signed in)  →  Sign in  →  [Change password, if required]  →  dashboard
User menu ▾ ├─ Change password
            ├─ Manage users       (admin only)
            ├─ Ingest & import    (admin only)
            └─ Sign out
```

### 1.2 Page list

| # | Page | Depends on folder | Needs log | Sketch |
|--:|---|:-:|---|---|
| 1 | Overview | yes | — | §3.1 |
| 2 | IP Map | yes | ingress nginx | §3.2 |
| 3 | Trends | **no** | — | §3.3 |
| 4 | Security | yes | nginx (attacks), appsmanager (login) | §3.4 |
| 5 | Root Causes | yes | nginx, Spring, coredns | §3.5 |
| 6 | Availability | yes | ingress nginx | §3.6 |
| 7 | Pods | yes | — | §3.7 |
| 8 | Business | yes | simpel-loop, report, appsmanager | §3.8 |
| 9 | Request Tracing | yes | simpel-loop + nginx | §3.9 |
| 10 | Service `<name>` | yes | that service | §3.10 |
| 11 | Sign in | — | — | §3.11 |
| 12 | Change password | — | — | §3.11 |
| 13 | Manage users (admin) | — | — | §3.11 |
| 14 | Ingest & import (admin) | — | — | §3.11 |

### 1.3 Address (URL)

The address stores the **tab, folder, and map module**, so a shared link opens the same view
and the browser back button works. In the old system only the tab was stored; the folder always went back to the
latest one (change U1). Language and theme remain per-browser choices and are not part of the address.

- No folder in the address → latest folder.
- Folder in the address does not exist → latest folder + a short notice.
- A service tab that does not exist in the selected folder → Overview (old behaviour).
- Not signed in → Sign in screen; after success, back to the address that was requested.
- Admin screens have their own addresses (`admin/user`, `admin/ingest`); opened by a regular user → the
  "No access" state (§6.6).

---

## 2. Frame

### 2.1 Wide screen (> 900 px)

```
┌────────────────┬──────────────────────────────────────────────────────────────────┐
│ [S4] SIMPEL4   │  Tab Title (38px, gradient)  [◀][Folder ▾][▶] [ID|EN] [☀|☾] [👤▾] │
│      Log       │  Log folder 6 Oct 2026 · contains logs 5 Oct 09:00–6 Oct 00:59   │
│                │  WIB · 7 services                                                │
│ ANALYSIS       │ ──────────────────────────────────────────────────────────────── │
│ ● Overview     │                                                                  │
│ ○ IP Map       │  <main>  page content:                                           │
│ ○ Trends       │    KPI row  → warnings/notes → 2-column card grid                │
│ ○ Security 14IP│    ("wide" cards span 2 columns)                                 │
│ ○ …            │                                                                  │
│ SERVICES       │                                                                  │
│ ○ Nginx-…  125 │                                                                  │
│ ○ Coredns  191 │                                                                  │
│ ○ …            │                                                                  │
│                │                                                                  │
│ All times      │                                                                  │
│ in WIB         │                                                                  │
└────────────────┴──────────────────────────────────────────────────────────────────┘
   236 px fixed     content max. 1560 px, padding 26/34 px, card grid min. 520 px
```

Kept: sidebar width 236 px, sidebar fixed while the content scrolls, the "Analysis"/"Services" groups, marker
dots, pink badges, gradient title, accent-coloured pill-shaped folder picker, card grid
`auto-fit` at least 520 px, KPI `auto-fit` at least 170 px.

Changed:

- **The subtitle shows the actual log time range** (B06, change U2). The folder name is not the date of its contents.
- **The header row sticks to the top** while scrolling (only the folder picker, language, theme; height 56 px), so
  the folder can be changed from the middle of a long page (U3).
- The text "All times in WIB (UTC+7)" appears once in the sidebar footer; it is not repeated in the subtitle.
- **User menu** at the right end of the header (U28): a button showing the display name; it opens into a list: name +
  role, "Change password", then for admins "Manage users" and "Ingest & import", then "Sign out". Standard menu
  pattern: `Enter`/`Space` opens, arrows move, `Esc` closes and returns focus.

### 2.2 Narrow screen (≤ 900 px)

See §8.

---

## 3. Sketch of each page

Notation: `[KPI]` number card · `╔ chart ╗` chart card · `┌ table ┐` table card · `(f)` has a filter ·
`▌warning` findings box · `┆note┆` dashed note card. The contents of each element and its data source are
in the inventory under the number given; only the layout is here.

### 3.1 Overview (inv. §2.1)

```
Log period: 5 Oct 2026 00:00 WIB – 6 Oct 2026 00:59 WIB
[Total log lines ▼36%] [Error ▼37%] [Warning/4xx] [HTTP requests] [4xx rate] [5xx rate]
[Services] [Log files] [Empty files] [Corrupt files*]
╔ Errors per hour per service (stacked bars)                       wide ╗
╔ Errors & warnings per service ╗    ╔ Log lines per service ╗
┌ Service summary ┐                  ┌ Log files ┐
┌ Top errors across services (25, proportion bars)                 wide ┐
── System-wide HTTP traffic ── (source: ingress nginx)
   … cards of the nginx service page, without the map and the messages card (§3.10 nos. 2–18)
```

\* B05: new KPI "Corrupt files", shown only when > 0.

### 3.2 IP Map (inv. §2.2)

```
[Module: All modules ▾]
[Unique source IPs] [Source locations] [Source countries] [Destination modules] [Unique destination IPs] [Total requests]
┌ Source IP → destination IP map                 [Indonesia | World]  wide ┐
│ ┌──────────────────────────────────────────────────────────── [+][−][⤢] │
│ │                 map (see §7)                                         │ │
│ └──────────────────────────────── © MaxMind · GeoNames · Natural Earth ─┘ │
│ ◉ Source IP location  ◉ Destination server  ⬤ Location cluster           │
│ 2,030 requests from outside Indonesia · 0 from internal / unlocated IPs  │
└──────────────────────────────────────────────────────────────────────────┘
┌ Source IP → destination IP flows (f)                                wide ┐
┆ Locations are city-level estimates … The destination IP is the pod IP …  ┆
```

### 3.3 Trends (inv. §2.3)

```
Comparison across log folders. Daily data is not always complete …
[Range: last 30 folders ▾]*
╔ Errors per day per service ╗       ╔ Warnings per day per service ╗
╔ HTTP requests per day ╗            ╔ Security per day ╗
╔ Business activity per day ╗        ╔ Log lines per day per service ╗
┌ Errors per service & change vs previous day                        wide ┐
┌ Data completeness (line count; Empty / Corrupt* / None)            wide ┐
```

\* Change U4: with 365 folders, bar charts and tables 365 columns wide are unreadable. A range picker
(last 14 / 30 / 90 folders / all; default 30). Both tables scroll horizontally with the "Service" column
locked on the left and the latest folder on the right. The folder picker in the header is **disabled** on this tab, with
the note "Trends show all folders".

### 3.4 Security (inv. §2.4)

```
[Attack requests] [Unique source IPs] [Critical attacks] [2xx endpoints]
[IPs with failed logins] [Accounts ok after ≥3 failures] [Success from a different IP] [Password resets]
▌Key findings: • Log4Shell attempts … • Rancher panel … • 62 2xx endpoints …
╔ Requests per attack category ╗     ╔ Suspected attacks per hour timeline ╗
╔ Top 10 attack source IPs ╗         ╔ Attack sources by network owner ╗
╔ Wrong passwords per hour ╗         ╔ Top 10 IPs with wrong passwords ╗
┌ Endpoints with suspected attacks (f)                               wide ┐
┌ Attack source IPs (f)                                              wide ┐
┌ Account analysis (f)                                               wide ┐
┌ Failed logins / brute force (f)                                    wide ┐
┌ IPs with most 4xx responses                                        wide ┐
Signature-based detection … (footnote)
```

The eight KPIs are laid out **4 + 4** on wide screens (currently 6 + 2, which leaves an orphan row; U5).

### 3.5 Root Causes (inv. §2.5)

```
▌Root cause summary: • repeated 401 … • JWT … • failed PDF … • DNS … • pod connection …
╔ Clients with repeated 401 ╗        ╔ Age of JWT when rejected ╗
╔ PDF reports per template ╗         ╔ nginx → pod connection errors by type ╗
┌ Clients with repeated 401 (f)                                      wide ┐
┌ PDF generation status per template (f) ┐   ┌ DNS timeouts per domain ┐
```

B07: the JWT age chart gets a caption below it, "Expired refresh tokens: N" (a number that is currently
computed but not shown).

### 3.6 Availability (inv. §2.6)

```
[Availability %] [Total 5xx] [5xx incidents] [Retries to another pod]
[Pod connection errors] [Uptime-Kuma checks] [Failed uptime checks]
╔ 5xx responses per hour                                             wide ╗
╔ 5xx responses per upstream ╗       ╔ Uptime-Kuma health checks per hour ╗
┌ Availability per upstream ┐        ┌ Uptime-Kuma health check targets ┐
┌ 5xx incidents                                                      wide ┐
┌ nginx → pod connection errors (f)                                  wide ┐
```

### 3.7 Pods (inv. §2.7)

```
[Pods (log files)] [Pods without logs] [Backend pods in nginx] [Pods with retries*] [Restarts]
┆ Pod names come from the log file names. Nginx only logs the pod IP …    ┆
╔ Errors per pod (15) ╗              ╔ Request distribution per pod (IP) (15) ╗
┌ Health per pod (f) — Status: Has logs / No logs / Corrupt*         wide ┐
┌ Traffic distribution per backend pod                               wide ┐
┌ Application restarts / starts                                      wide ┐
```

\* B10: label "Pods with retry 502" → "Pods with retries". B05: status "Corrupt".

### 3.8 Business (inv. §2.8)

```
[Reports created ▲] [Registrations ▲] [OTPs requested] [OTPs verified] [Files uploaded] [Uploads rejected]
[Emails sent] [PDFs generated] [PDFs failed] [Successful logins] [Unique users logged in]
┆ Counted from application events (2xx responses) … only pods with logs   ┆
╔ Public service activity summary ╗      ╔ Notification emails per type ╗
╔ Top report processing activities ╗     ╔ Successful logins per hour ╗
╔ PDF reports per template ╗
┌ Report processing activities ┐         ┌ PDF reports per template ┐
```

### 3.9 Request Tracing (inv. §2.9)

```
[Simpel-loop requestIds] [Matched with nginx] [Match rate]
[Traced failed requests] [Unique IPs (failed)] [Slow ≥ 5 s]
┆ Every simpel-loop app event has a requestId … X % did not match …       ┆
╔ Top 10 IPs with failed requests ╗  ╔ Failed requests per error type ╗
┌ Failed / slow request traces (f)                                   wide ┐
```

### 3.10 Service page (inv. §2.10)

One template; cards that do not apply to the service are not rendered (checklist table in inv. §2.10).

```
[Log lines] [Error] [Warning] [HTTP requests] [4xx rate] [5xx rate] [level 1..4]
 1 ┌ This module's map + ┌ flow table (f)                            wide ┐
 2 ╔ Activity per hour: Total & Error                                wide ╗
 3 ╔ HTTP status codes ╗              4 ╔ Traffic per upstream (donut) ╗
 5 ╔ Level distribution (donut) ╗     6 ╔ Top 10 endpoints ╗
 7 ╔ Top 10 endpoints 4xx/5xx ╗       8 ╔ Top 10 client IPs ╗
 9 ╔ Top 10 error/warning messages ╗
10 ┌ Top endpoints ┐                  11 ┌ Endpoints with 4xx/5xx ┐
12 ╔ P95 – 10 slowest endpoints ╗     13 ╔ Highest error rate ╗
14 ┌ Endpoint performance                                            wide ┐
15 ┌ Endpoints with the highest error rate                           wide ┐
16 ┌ Slow requests ≥ 1 s ┐            17 ┌ Top client IPs ┐
18 ┌ Top user agents ┐
19 ┌ Error / warning messages (grouped) (f)                          wide ┐
```

Change U6: the map on the service page is **collapsed by default** ("Show the map of this module's user origins").
Reason: the map is the heaviest element, it already exists on the IP Map tab with a module picker, and on the service page
it pushes the main charts below the fold. Its flow table is collapsed with it. The open/closed choice is remembered per browser.

### 3.11 Sign in and admin (TRD §8.2–§8.4)

These screens use the same tokens, cards, tables, and buttons as the data pages. All of them are bilingual
and support both themes. There is no sidebar on the Sign in screen and on the mandatory Change password screen.

**Sign in**

```
                         ┌────────────────────────────────────┐
        [ID|EN] [☀|☾]    │  [S4]  SIMPEL4 Log                 │
                         │                                    │
                         │  Username                          │
                         │  [______________________________]  │
                         │  Password                          │
                         │  [__________________________] [👁] │
                         │                                    │
                         │  ▌Wrong username or password.      │  ← only after a failure
                         │                                    │
                         │  [           Sign in            ]  │
                         │  Forgot your password? Contact an  │
                         └────────────────────────────────────┘
```

- One card in the centre, maximum width 380 px; on phones as wide as the screen with a 16 px margin.
- The failure message is **the same single sentence** for a wrong name and a wrong password. When rate-limited: "Too many
  attempts. Try again in N minutes." When the session has expired: a blue note above the form "Your session
  has ended. Please sign in again."
- Fields use a visible `<label>`, `autocomplete="username"` / `"current-password"`; `Enter` submits;
  the 👁 button shows the password and has an accessible name. The failure message uses `role="alert"` and focus
  returns to the password field.
- There is no "remember me", registration, or forgot-password link via email.
- While submitting: the button is disabled with the text "Checking…".

**Change password**

```
┌ Change password ──────────────────────────────────────┐
│ ┆ You must change your password before continuing. ┆  │  ← only when required
│ Current password     [_________________________]      │
│ New password         [_________________________]      │
│   At least 12 characters. A long sentence is better.  │
│ Repeat new password  [_________________________]      │
│ [ Save ]   [ Cancel ]                                 │  ← no "Cancel" when required
└───────────────────────────────────────────────────────┘
```

- Required at first sign-in and after the password was reset by an admin: this screen is shown on its own until done
  (the only other way out is "Sign out").
- The rules are written before the user types, not as an error afterwards. Errors per field, below
  the field, linked with `aria-describedby`.
- Success → short notice "Password changed"; sessions on other devices end.

**Manage users** (admin)

```
Manage Users                                                       [+ Add user]
┌──────────────────────────────────────────────────────────────────────────────┐
│ USERNAME    DISPLAY NAME    ROLE      STATUS      LAST SIGN-IN        ACTIONS│
│ admin       Administrator   ● Admin   ● Active    6 Oct 2026 18:40 WIB  [⋯]  │
│ rina        Rina            User      ● Active    5 Oct 2026 09:12 WIB  [⋯]  │
│ budi        Budi            User      ○ Inactive  –                     [⋯]  │
└──────────────────────────────────────────────────────────────────────────────┘
 [⋯] → Edit · Reset password · Deactivate / Activate · Delete

┌ Add user ───────────────────────────────────┐
│ Username        [______________]            │  lowercase letters, digits, dot, hyphen; 3–32
│ Display name    [______________]            │
│ Role            (•) User   ( ) Admin        │
│   Users see the whole dashboard.            │
│   Admins also manage users, ingest, imports.│
│ Initial password [_____________] [Generate] │
│   The user must change it at first sign-in  │
│ [ Save ]  [ Cancel ]                        │
└─────────────────────────────────────────────┘
```

- The table uses the table component (§4.3) with a filter. The admin role and the status use tags (§4.5): admin =
  neutral tag with a dot, active = ok tag, inactive = `muted` text.
- The add/edit form is shown as a dialog (on phones: full screen). Focus is trapped inside the dialog;
  `Esc` closes it; focus returns to the trigger button.
- **Reset password** shows the temporary password **once**, with a copy button and the warning "This password
  will not be shown again".
- **Delete** and **Deactivate** ask for a confirmation that names the user. Deleting yourself, or
  deleting/demoting/deactivating the last admin, is **not offered** (the menu item is disabled with a
  note explaining why).
- On phones the table becomes row cards (§8.2); the "+ Add user" button sticks to the bottom of the screen.
- Empty is impossible (there is always at least one admin).

**Ingest & import** (admin)

```
Ingest & Import
┌ Ingest ──────────────────────────────────────────────────────────────────────┐
│ Last: 6 Oct 2026 17:51 WIB · succeeded · 0 files changed           [Ingest now]
│ ▓▓▓▓▓▓▓▓░░░░  Folder 2026-10-06 · 12 of 18 files          ← only while running │
│ ▌2 warnings: differing .log/.log.gz pair (…); unknown service (…)             │
└──────────────────────────────────────────────────────────────────────────────┘
┌ Import from S3 ──────────────────────────────────────────────────────────────┐
│ AWS credentials: ● available (server configuration)                           │
│ Link    [ s3://simpel4-backup/k8s-logs/2026-10-07/            ]               │
│         Only s3://simpel4-backup/k8s-logs/<date>/                             │
│ [ Dry run ]  [ Import ]                                                       │
│ Dry run: 18 objects would be fetched (104 MB) · 19 skipped (paired .gz)       │
│ ┌ Import history: TIME · LINK · FOLDER · OBJECTS · SIZE · STATUS ───────────┐ │
└──────────────────────────────────────────────────────────────────────────────┘
┌ Audit log (f) ─ TIME · USER · ACTION · DETAILS · IP ─────────────────────────┐
```

- **Ingest**: last status, an "Ingest now" button (disabled while running), progress while running
  (updated every 2 seconds; announced politely to screen readers), and an expandable list of warnings.
  The dashboard stays usable during an ingest.
- **Import**: a link field with an example of the accepted form; "Dry run" only lists objects and
  shows a summary; "Import" asks for confirmation and then shows progress. Errors are written as cause
  and action ("This bucket is not allowed. Allowed: …").
- **Credentials**: status only (available / not, and the source). When not available, a form to paste
  temporary credentials appears (three password-type fields, without `autocomplete`) with the note "kept in
  server memory only, lost when the server restarts". Credential values are never shown again.
- When import is turned off in the configuration: the Import card is replaced by a note on how to enable it.
- **Audit log**: a filterable table, newest on top, first 50 rows + "show next".
- On phones the three cards stack; history and audit become row cards.

---

## 4. Reused components

Every component has four states: **filled**, **loading**, **empty**, **failed** (§6.5–6.7).

### 4.1 KPI card

```
┌──────────────────────┐
│ Label (13.5px, 500)  │   ← max. 2 lines
│ 124,822   (34px,600) │   ← tabular figures; colour = meaning (§5.3)
│ ▼ 36% vs 5 Oct 2026  │   ← optional, 11.5px
└──────────────────────┘
```

- Value colours: accent gradient (neutral), `err`, `warn`, `ok`, `muted`. Same as the old one.
- Comparison line: the four forms from inv. §2.0 (▲/▼ %, ≈ same, new, incomplete). Arrows are **always
  accompanied by a word** ("up"/"down" for screen readers) and colour is not the only indicator.
- Change U7: KPIs whose value now differs from the old system because of B03 get no mark at all in the
  view; the difference lives in the parity report, not in the interface.
- Change U8: a KPI may have an **`(i)` explanation** (tooltip + keyboard focus) containing a one-sentence
  definition. Required for those whose definition is not clear from the label: Error (nginx and frontend = 5xx responses +
  error log lines, **with the breakdown**: "51 5xx responses + 74 error log lines"), Warning / app 4xx,
  Availability (non-5xx), Unique destination IPs, Match rate. Outside KPIs, the same explanation is required on:
  the simpel-loop level donut title ("failed 4xx requests count as WARN, 5xx as ERROR") and the `EXC` level in the messages
  table ("exception detail; not added to the Error count") (TRD §4.4).

### 4.2 Chart card

- Frame: title on the left, actions on the right (if any), canvas height 280 px. Same as the old one.
- Types and styles are kept (inv. §2.0): gradient area lines, round-cornered bars (max. 34 px),
  74 % donut with the percentage in the centre, horizontal top-N bars with labels truncated at 48 characters.
- Colours come from tokens (§5.4), not hard-coded values; switching theme without reloading data.
- Legend only when there is > 1 series or a donut. Index-mode tooltip.
- Change U9: every chart has a **text alternative**: an `aria-label` with the title + a one-sentence summary
  (largest value and total), and a "View as table" button that opens the chart data in a table. Canvas
  charts cannot be read by screen readers and cannot be copied.
- Change U10: the time axis shows hours only (`13:00`) when all points are on one date; the date is written
  once below the axis. Currently every label repeats `5 Oct` and is slanted.
- Horizontal bars for IPs: clicking a bar scrolls to that IP's row in the related table on the same
  page (if any). It does not change page.

### 4.3 Table with filter

```
┌ Table title                              [🔍 filter…        ] ┐
│ COLUMN A ▾       COLUMN B       COUNT                         │  ← sticky header
│ row …                                                1,234    │
│ …                                                             │  ← max. 440–600px, scrolls inside the card
│ Showing 30 of 653   [Show next 100]                           │  ← new (B04)
└───────────────────────────────────────────────────────────────┘
```

- Kept: sticky header, right-aligned tabular numbers, row highlight on hover, first column
  `word-break`, proportion bar under the first cell for "Count" tables, status code colouring.
- **Initial count = the old limit** (inv. §5.2), so the first view is identical. One exception: the IP
  flow table shows the first **100** rows, not 3,000 (U30). Below it, a status line
  "Showing N of M" and a button to load the next ones (B04). When M ≤ N the status line is not shown.
- The **filter** searches **all the data** of that table, not just the visible rows (B04). Substring,
  case-insensitive, on all text columns; 250 ms typing debounce; × button to clear; result
  "N matching rows". No results: "No rows match '…'".
- Change U11: **sort per column** by clicking the header (numbers and times). Default order = old order.
- Wide tables (≥ 6 columns) scroll horizontally inside the card with the first column locked; see §8.
- Truncated cells (URL, UA, message) show the full text on click/focus, not only via `title`.

The grouped messages table (F19) uses this component with expandable rows: clicking a message → a sample of the original log
line in a monospace block labelled "Original log line (UTC time)", with a copy button.

### 4.4 IP cell with network owner

```
103.160.147.100                      ← bold, monospace-tabular
AS141576 · ID · IDNIC-OMBUDSMAN-AS-ID Ombudsman Republik Indonesia   ← 11px, muted
● Ombudsman network                  ← green tag, only when the owner is Ombudsman
```

- Variants: without owner (IP only); private IP → "Internal network (private IP)"; `+N` other IPs in the
  attacks table. Same as the old one.
- Owner text is truncated to 2 lines; full text on click/focus.
- Change U12: a small copy button appears on hover/focus. No outbound link to an IP lookup service
  (that would break the privacy rule).
- In charts, the IP tooltip shows the owner on the second line (old).

### 4.5 Severity tags

| Level | Categories | Dark (text / background) | Light (text / background) |
|---|---|---|---|
| 3 critical | Log4Shell / RCE, SQL Injection, Path Traversal / LFI, XSS | `#fda4af` / err 14 % | `#be123c` / err 14 % |
| 2 medium | Sensitive file probe, CMS / WordPress scan, PHP / CGI probe | `#fcd34d` / warn 14 % | `#b45309` / warn 14 % |
| 1 low | Automated tool/scanner UA; neutral tags ("Multi-account", account flags) | `#cbd5e1` / grey 14 % | `#44546a` / grey 14 % |
| ok | "Ombudsman network", "Has log" | `#6ee7b7` / ok 14 % | `#047857` / ok 14 % |

Pill shape, 11 px bold, small dot on the left. Same as the old one. Addition: the level is also distinguished by
**text** (the category name is always shown), so it does not depend on colour. The new "Corrupt" tag (B05) uses level 2.

### 4.6 Warnings and notes

- **Warning** ("Key findings", "Root cause summary"): a card with a 3 px red left border, bold
  title, bullet list. Same. IPs and accounts inside sentences use the data style (not capitalized).
- **Note**: a dashed-border card, `muted` 13 px text. Used for method explanations and
  empty states.

### 4.7 Map

One component for the IP Map tab and the service page; specification in §7.

### 4.8 Controls

| Control | Form | Note |
|---|---|---|
| Folder picker | pill `select`, accent text | §6.1 |
| Module picker | pill `select` | §6.2 |
| Language, theme, map preset | pill button group (segmented) | `role="radiogroup"`, left/right arrows move |
| Filter | pill input with a magnifying-glass icon | §4.3 |
| Secondary button | outlined pill, `fg` text | "Show next", "Try again", "View as table" |

---

## 5. Design tokens

Taken from `:root` and `:root[data-theme="light"]` in `dashboard_template.html`. The names are kept.
The "Δ" column marks values that are **changed or new**, with the reason in §5.6.

### 5.1 Base colours

| Token | Dark | Light | Use | Δ |
|---|---|---|---|:-:|
| `--bg` | `#0a1120` | `#f3f6fb` | page background | |
| `--bg2` | `#0d1628` | `#ffffff` | input and button group background | |
| `--card` | `#101b2e` | `#ffffff` | card background | |
| `--card2` | `#0c1524` | `#eef3fa` | map and code block background | |
| `--fg` | `#e2ecf3` | `#0f1b2d` | main text | |
| `--muted` | `#7d8fa6` | `#5b6b80` | secondary text | |
| `--line` | `#1c2a40` | `#dbe3ee` | divider lines (decorative) | |
| `--line-strong` | `#5a7299` | `#8794a8` | input and button borders | new |
| `--accent` | `#2dd4bf` | `#0d9488` | accent, charts, focus | |
| `--accent2` | `#22d3ee` | `#0891b2` | gradient | |
| `--accent-text` | `#2dd4bf` | `#0f766e` | accent as **small text** | new |
| `--violet` | `#8b5cf6` | `#7c3aed` | second series | |
| `--err` | `#f43f5e` | `#e11d48` | error, 5xx | |
| `--warn` | `#f59e0b` | `#b45309` | warning, 4xx | |
| `--ok` | `#34d399` | `#059669` | success, 2xx (charts, large numbers) | |
| `--ok-text` | `#34d399` | `#047857` | success as small text | new |
| `--neutral` | `#7a8699` | `#7a8699` | 3xx, severity 1 in charts | named |
| `--land` | `#1b2d4a` | `#cfdff5` | map land | |
| `--coast` | `#5a7299` | `#6f86ab` | coastlines and region borders | new |
| `--glow` | `0 0 0 1px rgba(45,212,191,.06), 0 12px 32px rgba(0,0,0,.35)` | `0 1px 2px rgba(15,27,45,.05), 0 8px 24px rgba(15,27,45,.06)` | card shadow | |

The dark-theme page background keeps its two subtle radial gradients (cyan top-right, violet bottom-left).
Dark-theme cards keep the gradient `rgba(20,34,56,.92) → rgba(11,20,35,.92)`; the light theme is plain white.

### 5.2 Derived colours that are currently written inline

In the old CSS these values are scattered as hex codes; v2 names them.

| Token | Dark | Light |
|---|---|---|
| `--side-bg` | gradient `#0b1424 → #080e1a` | `#ffffff` |
| `--nav-fg` | `#b6c4d4` | `#44546a` |
| `--kpi-label` | `#c4d2e0` | `#44546a` |
| `--heading` | `#dbe7f0` | `--fg` |
| `--th-fg` / `--th-bg` | `#9fb1c4` / `#0f1a2c` | `--muted` / `#f6f8fc` |
| `--code-fg` | `#c7d7e4` | `#44546a` |
| `--pre-bg` | `#08101d` | `#f6f8fc` |
| `--row-hover` | `rgba(45,212,191,.03)` | same |
| `--badge-fg` / `--badge-bg` | `#fda4af` / `rgba(244,63,94,.12)` | `#be123c` / same |
| `--title-grad` | `#2dd4bf → #a5f3fc → #e2e8f0` | `#0d9488 → #0891b2 → #1e3a8a` |
| `--kpi-grad` | `#2dd4bf → #67e8f9` | `#0d9488 → #0891b2` |
| `--tooltip-bg` | `rgba(8,16,29,.95)`, border `rgba(45,212,191,.3)` | same (dark tooltip in both themes) |
| `--grid` | `rgba(148,163,184,.08)` | `rgba(15,27,45,.08)` |

### 5.3 Meaningful colours

| Meaning | Token |
|---|---|
| 2xx / success / has log | `--ok` |
| 3xx / neutral | `--neutral` |
| 4xx / WARN / severity 2 | `--warn` |
| 5xx / ERROR / EXC / severity 3 | `--err` |
| INFO level | `--accent`; PERFORMANCE `--ok`; DEBUG `--muted` |
| Server dot on the map | `--warn` |
| Location dots and arcs | `--accent` |

### 5.4 Chart series palette

| # | Dark (old) | Light | Δ |
|--:|---|---|:-:|
| 1 | `#2dd4bf` | `#0d9488` | new light |
| 2 | `#8b5cf6` | `#7c3aed` | |
| 3 | `#22d3ee` | `#0891b2` | |
| 4 | `#f472b6` | `#db2777` | |
| 5 | `#f59e0b` | `#b45309` | |
| 6 | `#34d399` | `#059669` | |
| 7 | `#60a5fa` | `#2563eb` | |
| 8 | `#f43f5e` | `#e11d48` | |
| 9 | `#a3e635` | `#65a30d` | |
| 10 | `#fb923c` | `#ea580c` | |

The hard-coded purple `#8a5cd6` of the "client IP" bars is replaced by `--violet`.

### 5.5 Typography, sizes, shapes

| Token | Value | Note |
|---|---|---|
| Interface font | Outfit 400/500/600/700, then `system-ui` | **bundled**, not from Google Fonts (B09) |
| Data font | JetBrains Mono, then `ui-monospace` | the old one names it but does not load it; v2 bundles one weight (400) |
| Base text | 14 px / 1.5 | |
| Page title | 38 px / 600 (28 px on narrow screens) | |
| KPI value | 34 px / 600, tabular figures | |
| Card title | 15.5 px / 500 | |
| KPI label, navigation | 13.5 px | |
| Table cell | 13 px; header 12 px / 600, letter spacing .06em | |
| Small text | 12 px (code, time), 11.5 px (delta), 11 px (tags, IP owner) | **minimum 11 px** |
| Radius | card 20 · map/block/scroll 12 · pill 999 · bar 6 | |
| Spacing | card grid 18 · KPI 14 · card padding 20/22 · KPI 18/20 · cell 10 | |
| Height | chart 280 · table max. 440 (560–600 for large tables) | |
| Width | sidebar 236 · content max. 1560 · card min. 520 · KPI min. 170 | |
| Breakpoints | 900 px (old) and 560 px (new) | §8 |
| Focus | 2 px `--accent` outline + 2 px offset | new, §9 |
| Motion | 150 ms transitions; turned off under `prefers-reduced-motion` | |

Capitalization: interface text is *Capitalize Each Word* via CSS, data is not (old). **Owner decision 2026-10-06**:
**system names** (backend/frontend services, pods, namespaces, hosts, upstreams, modules) are always **lowercase** as they are,
including in the sidebar, service page titles, chart labels, and finding sentences (old: `tc()` capitalized service names;
change U33). Code: `sysName()` in `format.js` and the `sys` class for elements capitalized by CSS. New exception: long
sentences (notes, finding bullets, empty-state captions) are **not** capitalized; currently they get capitalized too
and are hard to read ("Lokasi Adalah Perkiraan Tingkat Kota Dari Database…", i.e. "Locations Are City-Level Estimates From The
Database…") (U13).

### 5.6 Why there are new tokens

Contrast ratios computed from the old values (WCAG 2.1; small text needs ≥ 4.5, graphics and control borders ≥ 3):

| Old pair | Ratio | Problem | Fix |
|---|--:|---|---|
| Light: `--accent` `#0d9488` on white | 3.74 | used as 13.5 px text (active nav, folder picker) | `--accent-text` `#0f766e` = 5.47 |
| Light: `--ok` `#059669` on white | 3.77 | small green text | `--ok-text` `#047857` = 5.48 |
| Light: chart series 1 `#2dd4bf` on white | 1.86 | bars almost invisible | light palette §5.4 (all ≥ 3) |
| Light: series `#f59e0b` on white | 2.15 | same | `#b45309` = 5.02 |
| `--line` against the card | 1.2–1.3 | input borders invisible | `--line-strong` (dark 3.6; light 3.1) |
| `--land` against `--card2` | 1.2–1.3 | land nearly merges with the sea | coastline `--coast` (dark 3.7; light 3.3) |

Already compliant and unchanged: `--fg` (14.4 / 17.3), `--muted` (5.2 / 5.4), table header (7.9 / 5.1),
navigation (10.4 / 7.7), `--err` and `--warn` as text in both themes (≥ 4.7), the dark palette (≥ 4.1).

---

## 6. Behaviour

### 6.1 Folder picker

- Contents: all folders, newest on top. Label: `Log folder 6 Oct 2026`; in the open list a small
  `log 5 Oct` caption is added, and an `empty` / `corrupt` mark when that folder has practically no data (B05, B06).
- Default: the latest folder. **ASSUMPTION D1**: it stays the browser's native `select`, not a calendar; enough for dozens of
  folders and accessible for free. Once there are hundreds of folders, options are grouped by month (`optgroup`).
- Changing folder: the tab stays; the content changes; the scroll position goes back to the top; the "Services" list in the sidebar and
  the badges adjust; the address is updated. Table filters are cleared; the module choice is kept if that module
  exists in the new folder.
- ◀ ▶ arrows next to the picker for the previous/next folder (U14); useful when comparing consecutive
  days. Shortcuts `[` and `]`.
- On the Trends tab: disabled (§3.3).

### 6.2 Module picker (IP Map)

- Contents: "All modules" + the destination modules present in that folder, sorted alphabetically (old).
- Changing module: KPIs, map, legend, and flow table change together; **the map position and zoom are kept**
  (currently the map is re-rendered; the preset stays but manual zoom is lost).
- The choice is stored in the address. A module that does not exist in the new folder → back to "All modules" (old).

### 6.3 Switching language

- ID / EN button in the header; applies instantly without reloading data; remembered per browser; default ID.
- What is translated: all interface text, automatic finding sentences, chart labels and legends, number format
  (`1.234` / `1,234`), dates and times (`06.03` / `06:03`), duration units (`dtk` / `s`), country names, month
  names (`Okt` / `Oct`).
- What is **not** translated: log data (URLs, messages, UAs, template names), service names, city and
  province names from the location database, province/regency labels on the map.
- Attack categories, account flags, business metrics, and JWT age groups are **labels**, so they are translated
  (the old system did so too).
- Change U15: text comes from a keyed dictionary, not from replacing text in the DOM after rendering. Not
  visible to users, but it removes the flicker of Indonesian text before it switches and the risk of data that
  happens to equal a dictionary key being "translated" as well.
- The document `lang` attribute follows the choice.

### 6.4 Switching theme

- ☀ / ☾ button; instant; remembered per browser.
- Default on first open: **dark** (old). **ASSUMPTION D2**: it does not follow the system preference, so that
  the first view matches the familiar one.
- Charts and the map change colour without fetching data again and without losing the map position.
- The button uses `aria-pressed` and a text label ("Light theme", "Dark theme"), not just an icon.

### 6.5 Loading

The old system has no loading state (all data is already in the page). v2 fetches data per tab, so:

- **The frame appears immediately**: sidebar, header, tab title. Never a blank screen.
- **Grey skeletons** the size of the final content: KPI row, 280 px chart cards, 6-row tables. No
  spinner in the middle of the screen. Fixed sizes so the page does not jump when the data arrives.
- Skeletons only appear if the data has not arrived within **200 ms**, so fast switches do not flicker.
- **One request per page** (TRD §5.3): all cards of a page appear together when their data arrives
  (U31). The only things loaded separately are table continuations ("show next", filter, sort): then only
  the body of that table dims.
- Changing folder on the same tab: the old content stays visible but dimmed (60 %) until the new one arrives.
- Sidebar: while the service list of the new folder has not arrived, the old list stays visible.
- `aria-busy` on `<main>`; screen readers get "Loading …" then "Done" via a polite `aria-live` region.

### 6.6 Empty

Empty states always **explain the cause** and, if possible, what can be done. The old texts are kept.

| Page | Condition | Display |
|---|---|---|
| All | No folder ingested yet | One card in the centre: "No data yet." For admins: a button to the Ingest & import screen; for users: "Contact an admin." |
| Admin screen | **No access**: a regular user opens the address of an admin screen | In `<main>`: "No access. This page is for admins only." + a "Go to Overview" button. Sidebar and header stay |
| All | The selected folder is practically empty or corrupt | Yellow band above the content: "This folder contains only N lines; M corrupt files" + a link to the Pods tab |
| Overview | No ingress nginx | HTTP KPIs and the "HTTP traffic" section are not shown (old) |
| IP Map | No ingress nginx | Note: "The map needs ingress nginx logs; this folder has none." |
| IP Map | Base map data or location database not present | The map is replaced by a note; KPIs and the flow table are still shown, Location column "Unknown" |
| Trends | Only one folder | Charts are still shown; the change column is empty |
| Security | No nginx | Note "per-URL attack detection is unavailable"; the login part stays |
| Security | No findings | The "Key findings" box is not shown (old) |
| Root Causes | No patterns | Note "No root cause patterns detected for this folder." |
| Availability | No nginx | Note "Availability analysis uses the ingress nginx log…" |
| Pods | — | Always has content as long as there are files |
| Business | No simpel-loop | KPIs with value 0 (old) + a new note "No simpel-loop log in this folder" |
| Tracing | No correlation | Note "Tracing needs om-be-simpel-loop and ingress nginx logs…" |
| Service | 0 lines | "No logs for this service on this date (empty file)." |
| Service | Only corrupt lines | Same + a "Corrupt" tag and the number of corrupt files |
| Any table | 0 rows | One `muted` row "No data" (old) |
| Any chart | 0 points | The card is not rendered (old) |

Change U16: a 0 because **the log is missing** is distinguished from a 0 because **it really did not happen**. The
former is shown as "–" with an explanation; currently both are "0" (example: the Business tab on a folder without
simpel-loop). **ASSUMPTION D3**; this changes how some KPIs are displayed, not their numbers.

### 6.7 Failure

The old system cannot partially fail. v2 can:

| Failure | Display |
|---|---|
| The whole page fails to fetch data | In `<main>`: title, one-sentence explanation, **Try again**; sidebar and header keep working |
| A table continuation fails ("show next", filter, sort) | A message row below that table + **Try again**; rows already shown stay |
| **Session expired** (the server answers "not signed in" in the middle of use) | Go to the Sign in screen with the note "Your session has ended"; after signing in, back to the same address (tab, folder, module) |
| An admin action fails (save user, ingest, import) | A message inside that action's dialog/card, stating cause and action; the input is not lost |
| Dashboard server unreachable | Red band at the top: "Not connected to the dashboard server" + automatic retry every 5 seconds (max. 1 minute), then manual |
| Folder in the address does not exist | Go to the latest folder + a notice (§1.3) |
| The map fails to render (no WebGL) | The map is replaced by a note; the flow table stays as the substitute |

Failure messages are written for users, not developers: no raw error codes in the main text; technical details
under an expandable "Details". Failure messages use `role="alert"`.

### 6.8 Miscellaneous

- Switching tabs: scroll position to the top; focus moves to the page title.
- Changing numbers are not animated.
- Data refresh: there is no automatic refresh (A7). A small "Reload" button in the header re-fetches the
  active tab and the folder list; useful after ingesting a new folder.

### 6.9 Sign-in, sessions, and roles

- **Before signing in** no dashboard data is loaded; only the Sign in screen. Language and theme can be changed
  on that screen and carry over after signing in.
- **After signing in**: to the address that was requested, or the Overview of the latest folder. If the password must be changed,
  the Change password screen comes first.
- A **session** ends after 60 minutes without activity or after 12 hours (TRD §8.2). Five minutes before it ends
  due to inactivity, a small band at the top: "Your session ends in 5 minutes" + "Stay signed in". Session expired → §6.7.
- **Sign out**: immediate, without confirmation; back to the Sign in screen; the data on screen is cleared.
- **Roles**: users and admins see the same dashboard. The only differences are the user menu (two admin items) and the two
  admin screens. There are no elements "greyed out for lack of permission" on the data pages.
- A role change or deactivation by an admin applies on the next request: a deactivated user
  is treated like an expired session.
- Short notices ("User added", "Password changed") appear in a corner for 4 seconds, use
  `role="status"`, and do not cover buttons.

---

## 7. Source IP → destination IP map (MapLibre)

### 7.1 What is kept from the old map

Same theme (sea `--card2`, land `--land`), accent ringed dots per location, an orange server dot
labelled "Server SIMPEL4 + IP", curved arcs from location to server with a thickness of 1–4 px according to the number of
requests, the **Indonesia** and **World** presets, +/− buttons, country → province → regency/city labels that
appear progressively, the legend, and the sentence "N requests from outside Indonesia · M from internal / unlocated IPs".

### 7.2 Base map: without sending user data

Requirement (PRD §5.4 item 3): the browser must not request anything from external domains. Online tile maps (OSM,
MapTiler, Carto) send the IP address of whoever opens the dashboard and the coordinates being viewed to third parties, so they
are **not used**. There are two sources that meet the requirement:

| Option | Contents | Size | Licence | Assessment |
|---|---|--:|---|---|
| **A. Natural Earth GeoJSON, served by the dashboard itself** | land, country borders, province borders | ±2–4 MB | public domain | **Chosen.** Same as the old map's source; enough for a city-level dot map |
| B. Single-file vector tiles (Protomaps/OSM) served in-house | roads, cities, rivers, detailed borders | hundreds of MB for Indonesia | ODbL, OSM attribution required | More detailed than the data's accuracy (IP locations are city-level only); postponed |

**ASSUMPTION D4**: option A. The map style does not load `sprite` or `glyphs` from outside; label fonts are bundled
with the application.

### 7.3 Layers

| Order | Layer | Source | Shown at |
|--:|---|---|---|
| 1 | Sea (background) | — | always |
| 2 | Land | Natural Earth 50m land | always |
| 3 | Coastline | same | always, 0.5 px `--coast` |
| 4 | Country borders | Natural Earth 50m admin-0 boundary lines | always, 0.75 px `--coast` |
| 5 | Indonesian province borders | Natural Earth 10m admin-1, filtered to Indonesia | zoom ≥ 4, 0.5 px dashed line |
| 6 | Location → server arcs | flow data | always, accent 45 % |
| 7 | Dot clusters | flow data | §7.5 |
| 8 | Location dots | flow data | §7.5 |
| 9 | Server dot | configuration | always, above all dots |
| 10 | Country labels | Natural Earth | always; small countries from zoom ≥ 3 |
| 11 | Province labels | GeoNames | zoom ≥ 4 |
| 12 | Regency/city labels | GeoNames | zoom ≥ 7 |
| 13 | IP location labels | flow data | 6 largest always; others when they do not collide |

Notes:

- **New border lines**: the old map only had land without any borders. Country and province borders
  are added because they were requested and because they help to read "which province is this dot in".
- **Regency/city borders are not drawn**; only their labels (as now). Regency border data with a
  free licence that can be bundled has not been confirmed yet (question Q3).
- Natural Earth may not yet include the 2022 split of Papua province, while the GeoNames labels already have 38
  provinces. If so, the border lines and labels in Papua do not match (Q3).
- **Label collisions are handled by the map engine**: overlapping labels are hidden by priority (IP location >
  country > province > regency). On the old map all labels were drawn so they overlapped each other, clearly visible
  in the screenshot (Java and Sulawesi are unreadable).
- Country labels: Indonesian or English name according to the language; spaced capitals, as now.
- The label font inside the map is **Noto Sans**, not Outfit: the map engine needs font files in a
  special format that are bundled too (TRD §6.4, T4). Dot labels and tooltips above the map stay Outfit.

### 7.4 Projection and initial view

- **Web Mercator** projection (MapLibre default). The old map used plain degrees (equirectangular), so
  shapes at high latitudes differ; for Indonesia (near the equator) it is practically the same (U17).
- **Indonesia** preset: longitude 94–142, latitude −12–8 (same as the old box). **World** preset: longitude
  −168–168, latitude −60–80. Presets use *fit bounds* so they adapt to the container size.
- Zoom is limited: minimum = the whole world visible; maximum zoom 10 (± city level). Deeper has
  no content and suggests an accuracy the data does not have.
- The map cannot be tilted or rotated.
- Container ratio 2.4 : 1 on wide screens (old); for narrow screens see §8.

### 7.5 Dots and clustering

The old map merged IPs only when their coordinates were **exactly the same** (one city). Nearby cities still
overlapped; in the Indonesia view, Jabodetabek and Java became blobs.

- **Location dot** = one city (IPs with the same coordinates), as in the old map. Fixed size 14 px.
- **Cluster**: location dots less than 40 px apart on screen are merged into one circle showing the
  **number of requests** (abbreviated: `18.9k`). Diameter 24–44 px according to the number of requests (square-root scale).
  Solid accent colour, dark text. Clustering is recomputed at every zoom.
- Click/tap a cluster → the map zooms in until that cluster splits.
- Zoom ≥ 8: clustering off; all location dots are shown.
- **Arcs**: still one per location (not per cluster), so the picture of "where from" is not lost when
  dots are clustered. Thickness 1–4 px according to that location's requests; opacity 45 %; small locations (< 1 % of the
  largest) 25 %.
- The **server dot** is never clustered; its label is always shown, to the left of the dot.
- Drawing order: largest location on top (old).

**ASSUMPTION D5**: the number in a cluster = requests, not the number of IPs. Requests are the measure also used for arc thickness
and the table columns.

### 7.6 Zoom, pan, touch

| Input | Behaviour |
|---|---|
| Drag (mouse) | pans |
| Mouse wheel | **Ctrl/⌘ + wheel** zooms in towards the cursor. The wheel alone scrolls the page, with a short hint "Hold Ctrl to zoom the map" |
| Double click | zooms in one level |
| + / − buttons | zoom in / out one level |
| ⤢ button | back to the active preset |
| Two-finger pinch | zooms in / out |
| Two-finger drag | pans the map |
| One-finger drag | scrolls the **page**, with the hint "Use two fingers to move the map" |
| Keyboard (map focused) | arrows pan; `+` `−` zoom; `0` back to the preset; `Esc` closes the tooltip |

Change U18: on the old map the mouse wheel zoomed immediately and one finger panned immediately, so
users scrolling the page got **trapped** in the map; on phones the page could not be scrolled past the map
(`touch-action: none`). MapLibre provides a "cooperative gestures" mode for exactly this problem.

### 7.7 Tooltip

Appears when the cursor is over a dot (mouse), when a dot is tapped (touch), or when a dot is focused (keyboard).

```
┌───────────────────────────────────────┐
│ Pagatan, Kalimantan Selatan, Indonesia│
│ 1 source IP · 6,425 requests          │
│ → om-be-simpel-loop (5,277)           │
│   om-fe-inhouse (1,148)               │
│ [Show in table]                       │
└───────────────────────────────────────┘
```

- Same contents as the old tooltip (`title`), plus a **Show in table** button that fills the flow table filter
  with that city's name and scrolls to the table.
- Cluster: "N locations · N source IPs · N requests" + the three largest locations + "Click to zoom in".
- Server: "Destination server `<ip>` · Jakarta, ID".
- The old tooltip used the `title` attribute: it appears slowly, does not work on touch screens, and is unreadable in the system
  dark theme. Replaced by a box styled like the chart tooltip (U19).
- Only one tooltip open at a time; it closes when the map is panned, on `Esc`, or on a tap outside.

### 7.8 Attribution

An attribution control in the bottom-right corner of **every** map, always visible (not collapsed):
"GeoLite2 data by MaxMind · GeoNames · Natural Earth", the first two linking to their sites (B08, F22).
The IP location source was changed from DB-IP to MaxMind GeoLite2 by owner decision (TRD §3.6); the note
below the flow table mentions MaxMind, not DB-IP.
Links open in a new tab with `rel="noreferrer"`. The long note below the flow table is kept.

### 7.9 Map substitute

The map is not the only way to its information: the "Source IP → destination IP flows" table holds the same data and
is always below it. The map gets `role="application"` with the label "Map of request origins; the same data is in
the table below", and a "Skip the map" skip link.

---

## 8. Narrow screens

Breakpoints: **900 px** (old) and **560 px** (new, phones).

**Decided by the owner: the phone view is done seriously.** This whole section is mandatory, including wide tables
becoming row cards, and is checked on a real phone (not only emulation) at widths of 360–390 px.

### 8.1 Problems visible in the 390 px screenshot

1. The header toolbar overflows: the theme button is cut off at the right edge.
2. The map is about 130 px tall; labels overlap until they are unreadable.
3. The 5-column flow table is cut off; the 3rd column onwards is only visible when scrolled, with no hint.
4. The horizontal navigation shows 4 of 16 items with no sign that it can be scrolled; the service tabs are practically
   hidden.
5. The subtitle and the WIB text take three lines before the content.

### 8.2 Layout ≤ 900 px

```
┌──────────────────────────────────────┐
│ [☰] SIMPEL4 Log      [Folder ▾] [⋯] │  ← sticky top bar, 52px
├──────────────────────────────────────┤
│ IP Map                               │
│ Folder 6 Oct · log 5 Oct 09:00–00:59 │
│ [All modules ▾]                      │
│ [KPI] [KPI]                          │  ← 2 columns
│ [KPI] [KPI]                          │
│ ┌ map, ratio 4:3, min. 300px ──────┐ │
│ └──────────────────────────────────┘ │
│ ┌ table → row cards (≤560px) ──────┐ │
└──────────────────────────────────────┘
```

- **Navigation**: the ☰ button opens a drawer from the left containing the full sidebar (two groups, badges). It replaces
  the horizontally scrolling strip (U20). The drawer closes after a choice, with `Esc`, or a tap outside; focus is trapped
  inside while it is open.
- **Top bar**: the folder picker stays visible; language, theme, reload, and the user menu contents (name, change
  password, admin items, sign out) go into the `⋯` menu.
- **Sign in screen and dialogs** (add user, confirmation): full screen width; input fields ≥ 44 px tall and font
  ≥ 16 px so phones do not zoom the page when a field is touched; the keyboard does not cover the submit button.
- **KPIs**: 2 columns (≥ 360 px), 1 column below that. Value 28 px.
- **Card grid**: 1 column. Charts stay 280 px; time axis labels are reduced automatically.
- **Horizontal bar charts**: labels truncated at 28 characters (not 48).
- **Map**: ratio 4 : 3, minimum height 300 px; the ⤢ full-screen button opens the map at screen height. The
  +/− buttons are 44 px.
- **Tables with ≤ 4 columns**: stay tables; the first column wraps.
- **Tables with > 4 columns at ≤ 560 px**: each row becomes a stacked **card**: the first column as the title,
  the other columns as "label: value" pairs. Applies to: IP flows, attack endpoints, attack source IPs,
  account analysis, failed logins, request traces, incidents, connection errors, endpoint performance, pod health,
  pod traffic distribution, user list, import history, audit log.
- **Tables with > 4 columns at 561–900 px**: horizontal scroll inside the card, first column locked, a shadow on the
  right edge as a sign that there is more content.
- **Trends tables** (columns = folders): always scroll horizontally with the "Service" column locked.
- Minimum touch target **44 × 44 px** for buttons, navigation items, and map controls.
- No horizontal scrolling at page level at widths ≥ 320 px.

---

## 9. Accessibility basics

Target: WCAG 2.1 level AA for the items below. Not a full audit.

### 9.1 Contrast

- Text ≥ 4.5 : 1; large text (≥ 24 px, or ≥ 18.7 px bold) and graphical elements ≥ 3 : 1. The token values in §5
  have been calculated; the failing ones have been replaced (§5.6).
- `muted` text only on `--card`, `--bg`, `--bg2`; not on colours.
- Navigation groups ("ANALYSIS") are currently `muted` with 70 % opacity (≈ 3.0–3.4 : 1): the opacity is removed.
- Gradient KPI numbers: even the lightest end of the gradient is ≥ 3 : 1 against the card (large text).

### 9.2 Not dependent on colour

- HTTP statuses always show their code; severity tags always show the category name; ▲/▼ always come with
  a percentage and a word; "Corrupt"/"Empty" are text.
- Multi-series stacked charts: the legend can be clicked to hide a series; the tooltip names the series.
- Success/failure bars (PDF, Uptime-Kuma) are also distinguished by a fixed order (success first) and the tooltip label.

### 9.3 Keyboard

- Tab order: "Skip to content" link → navigation → header (folder, language, theme) → content.
- All controls can be reached and operated with the keyboard: navigation items, pickers, button groups, filters,
  sortable table headers, expandable message rows, the "Show next" button, chart legends,
  map controls.
- **Focus is always visible**: a 2 px `--accent` outline (light: `--accent-text`) with a 2 px offset. The old CSS
  removed the `outline` on inputs and replaced it with a faint shadow; navigation buttons had no focus style (U21).
- Shortcuts: `[` `]` previous/next folder; `/` focuses the first filter on the page; `g` followed by the first letter
  of a tab is not used (avoids clashing with screen readers). Shortcuts are inactive while typing in an input.
- No focus traps; the navigation drawer and map tooltips close with `Esc`.

### 9.4 Structure and screen readers

- Landmarks: `<nav>` (sidebar), `<header>`, `<main>`. One `<h1>` per page (tab title); card titles `<h2>`.
  Currently card titles are `<h3>` without an `<h2>`.
- Active tab: `aria-current="page"`. Badges have hidden text: "14 attack source IPs", "125 errors".
- Tables: `<th scope="col">`, a hidden `<caption>` = card title; sortable headers use
  `aria-sort`.
- Filter: a hidden `<label>` "Filter table <title>"; the number of results is announced via `aria-live`.
- Expandable message rows: `<details>/<summary>` (old, already correct).
- Charts: text alternative (§4.2). Map: §7.9.
- Icon-only controls (☀ ☾ + − ⤢ ☰ ⋯ ×) always have an accessible name.
- The document language follows the choice; data in other languages is not marked (too much, little benefit).

### 9.5 Miscellaneous

- Text can be enlarged up to 200 % without losing content; sizes use `rem`.
- `prefers-reduced-motion`: transitions, chart animations, and map fly movements are turned off.
- Tooltips that appear on hover also appear on focus, can be closed with `Esc`, and do not disappear when the cursor
  moves onto them.
- No content blinks or moves on its own.

---

## 10. Changes from the old look

Everything not mentioned here is **the same as the old look**.

| # | Change | Reason | Kind |
|--:|---|---|---|
| U1 | The address stores folder and module, not just the tab | Links can be shared; the back button works | addition |
| U2 | The subtitle shows the actual log time range | The folder name is not the date of its contents (B06) | addition |
| U3 | The folder picker bar sticks while scrolling | Long pages; the folder is changed often | layout |
| U4 | Trends: range picker; tables scroll horizontally; folder picker disabled | 365 folders do not fit; the folder picker has no effect here anyway | addition |
| U5 | Balanced KPI rows (e.g. 4 + 4), no orphan row | Readability | layout |
| U6 | The map on the service page is collapsed by default | Heaviest element; duplicates the IP Map tab; pushes the main charts down | behaviour |
| U7 | No "differs from the old system" mark in the interface | Differences are recorded in the parity report | decision |
| U8 | `(i)` explanation on KPIs whose definition is unclear | Some definitions are surprising (inv. §8 items 7, 9) | addition |
| U9 | Charts have a text alternative and "View as table" | Accessibility; chart data can be copied | addition |
| U10 | Time axis without repeated dates | Slanted, repeated labels are hard to read | display |
| U11 | Tables can be sorted; "Showing N of M" + load next; the filter searches all data | B04 | addition |
| U12 | Copy button on IPs and log lines | The most frequent task after finding an IP | addition |
| U13 | Long sentences no longer *Capitalize Each Word* | Hard to read | display |
| U14 | ◀ ▶ arrows and shortcuts for the previous/next folder | Comparing consecutive days | addition |
| U15 | Translation from a keyed dictionary, not text replacement in the DOM | No flicker; data is not translated by accident | internal |
| U16 | "–" for numbers that are missing because the log is missing | A misleading 0 (ASSUMPTION D3) | display |
| U17 | Web Mercator map projection | MapLibre default | unavoidable |
| U18 | Map zoom with Ctrl + wheel; pan with two fingers | The old map trapped page scrolling, especially on phones | behaviour |
| U19 | Map tooltip as a box, not a `title` attribute | Does not work on touch screens | fix |
| U20 | Narrow screens: drawer navigation; wide tables become row cards; map 4 : 3 | §8.1 | layout |
| U21 | Visible focus style; heading and landmark structure | Accessibility | fix |
| U22 | Map: coastlines, country and province borders; label collisions handled; nearby dots clustered | Requested; labels and dots overlapped on the old map | fix |
| U23 | Attribution on every map | B08 | compliance |
| U24 | Loading and failure states per page (and per table continuation) | Data is now fetched per page | unavoidable |
| U25 | New colour tokens for accent text, control borders, coastlines, light chart palette | Contrast (§5.6) | fix |
| U26 | Fonts and libraries bundled; JetBrains Mono actually loaded | B09 | internal |
| U27 | New labels and marks: "Corrupt files", "Pods with retries", "Expired refresh tokens" | B05, B10, B07 | addition |
| U28 | Sign in and Change password screens; user menu in the header; session warning | The dashboard is opened from many computers (owner decision) | new |
| U29 | Admin screens: Manage users, Ingest & import (including S3 import and the audit log) | Owner decision | new |
| U30 | The IP flow table shows the first 100 rows, not 3,000 | It can now be continued and filtered across all data; 3,000 rows were the largest rendering load | behaviour |
| U31 | The cards of a page appear together, not one by one | One request per page (TRD) | behaviour |
| U33 | System names (services, pods, namespaces, hosts, upstreams, modules) lowercase as they are | Owner decision 2026-10-06: system names read as technical identifiers | display |
| U32 | Numbers and charts that change due to definition fixes: the nginx/frontend errors-per-hour chart includes error log lines; the simpel-loop level donut uses the effective level; "slow ≥ 5 s" includes 3xx | Owner decision (TRD §4.4); given an `(i)` explanation | fix |

Unchanged although considered: tab order and names; card colours and style; chart type of each
card; table column contents; initial top-N display limits; automatic finding texts; dark default theme; default language ID.

---

## 11. Assumptions and open questions

### 11.1 Design ASSUMPTIONS

| # | ASSUMPTION | If wrong |
|--:|---|---|
| D1 | The folder picker stays a `select` (grouped by month when there are many), not a calendar | Replace the component; other pages are unaffected |
| D2 | Dark default theme, not following the system preference | One line of logic |
| D3 | "–" replaces 0 when the log is missing | Revert to 0 |
| D4 | Base map = self-served Natural Earth GeoJSON (no tiles) | Option B in §7.2; the map component stays the same |
| D5 | Dot cluster number = number of requests | Switch to number of IPs |
| D6 | All changes U1–U27 may go in before the parity test because they do not change **numbers** | Postpone the "addition" ones until after handover (PRD R9) |
| D7 | **[Partly dropped]** Per folder is now a decision. "Local only without login" is dropped: there is a two-role login (§3.11, §6.9). No internet / no external domains (A4) remains an assumption | — |

### 11.2 Questions for the product owner

| # | Question | Interim assumption |
|--:|---|---|
| Q1 | ~~How serious is the phone view?~~ **Answered: serious.** §8 is mandatory in full | — |
| Q2 | ~~Is a login needed?~~ **Answered: yes**, two roles, local accounts. The screens are in §3.11 | — |
| Q3 | Region borders: are country + province from Natural Earth enough? Is it acceptable that the Papua province lines do not yet include the 2022 split? Are regency/city borders needed (requires a data source with a clear licence)? | Country + province; regencies as labels only |
| Q4 | Trends: is the default range of the last 30 folders right? | 30 |
| Q5 | Map on the service page: agree that it is collapsed by default (U6), or should it rather be removed from there? | Collapsed |
| Q6 | "–" vs 0 (U16): agreed? This is the only change that alters what is written in a KPI. | Yes |
| Q7 | The "addition" changes in §10 (table sorting, copy, shortcuts, `(i)`): done during the migration, or after parity is proven? | During the migration, after P0 |
| Q8 | Is there an Ombudsman RI visual identity (logo, official colours) that must be used? Currently the logo is an "S4" square. **App name decided 2026-10-06: "SIMPeL4 Dashboard"; changed by the owner on 2026-10-07 to "MoniShield"** (`web/src/brand.js`) | "MS" logo mark, shield tab icon |

---

## 12. Request 2026-10-06: reference style and Command Center (style applied in Stage 12a)

The owner sent a reference image (a dark dashboard in a "Fleet Overview" style) and asked for a realtime **Command Center**
module. What can be seen in the reference and its impact on this document:

| Reference element | Compared with the current v2 | Proposal |
|---|---|---|
| Dark navy background, teal accent, cards with large corners, thin lines | Already in the same direction (tokens §5) | Keep the tokens; the §5.6 contrast still applies |
| Grouped sidebar with an **icon** per item, logo top-left, action card in the footer | Sidebar without icons, marker dots | Add line icons (bundled SVG, no CDN) |
| Title bar with a **compact status line** (`37/40 healthy · 2 failing …`) | Folder subtitle + time range | Compact status line below the page title |
| Compact KPIs with icons, large number + change badge, `⋯` menu | KPIs without icons | Icon + coloured change badge (still accompanied by text, §9.2) |
| Numbered **"What needs your attention"** card with action links | "Key findings" as a list | Numbered attention card; each item links to the related page/table |
| Compact status table + status pills (Healthy / Stuck / Cost spike) | Severity tags §4.5 | Status pills use the §4.5 tags |
| A **"streaming · last event 2s ago"** indicator and a **Live** button | No automatic refresh (A7, §6.8) | **Postponed**: log folders remain the primary source (decision 2026-10-06); meanwhile replaced by "data of folder 6 Oct · ingested 17:51 WIB" |

This departs from the "old look is kept" principle at the start of the document, so it needs the owner's approval (TRD R6).
**Decided by the owner 2026-10-06**: the new style for **the whole dashboard** (tokens and shared components; the layout and contents
of each page remain as in §3). **Overview stays**; Command Center is a **world map screen**. **ASSUMPTION**: the "IP Map" tab
is merged into Command Center at the same position in the sidebar.

