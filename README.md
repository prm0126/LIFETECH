# LIFETECH Management Dashboard

A lightweight web dashboard for hospital management to view:

- **Total registrations** &mdash; day-wise, week-wise and month-wise (with a trend chart)
- **Encounters created today** &mdash; total, **urgent care**, **consult**, **non-consult** and **consulted**, plus a per-provider breakdown

It reads directly from the Oracle database and is meant to be hosted on an
internal server so management can open it in any browser on the same network.
The UI has **no external/CDN dependencies**, so it works on an air-gapped LAN.

## Business rules

| Metric        | Source                                         |
|---------------|------------------------------------------------|
| Registrations | `PAT_PATIENT_DEMOGRAPHICS.VISIT_DATE`          |
| Encounters    | `PAT_FIN_ENCOUNTER_DETAILS.START_DATE`         |
| Urgent care   | `ISEMERGENCY = 1`                              |
| Consult       | `NVL(ISNONCONSULTENCOUNTER, 0) = 0`            |
| Non-consult   | `ISNONCONSULTENCOUNTER = 1`                    |
| Consulted     | `IS_CONSULTED = 1`                             |
| Provider name | `GET_EMPLOYEE_NAME(PROVIDER_ID)` Oracle fn.    |

By default only valid encounters (`NVL(ISVALID,1)=1`) are counted. Table names,
column names and the employee-name function are all configurable via `.env` so
the app can point at views or renamed objects without code changes.

## Windows quick start (one click)

On the Windows server, get the code and use the bundled launcher:

```bat
git clone https://github.com/prm0126/LIFETECH.git
cd /d D:\path\to\LIFETECH
run.bat
```

`run.bat` creates a virtual environment, installs dependencies, and creates a
`.env` from the template on first run (it opens Notepad so you can fill in
`ORACLE_USER` / `ORACLE_PASSWORD` / `ORACLE_DSN`). Run it again and the
dashboard starts on `http://0.0.0.0:8080/`.

> Requires Python 3 with **"Add python.exe to PATH"** ticked during install
> (download: https://www.python.org/downloads/windows/). If `git` isn't
> available, download the repo ZIP from GitHub and extract it instead.
>
> Note: on Windows, `cd` to another drive needs the `/d` switch
> (`cd /d D:\...`), and use `copy` rather than the Linux `cp`.

## Setup (manual)

```bash
cd LIFETECH
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # Windows: python -m pip install -r requirements.txt

cp .env.example .env               # Windows: copy .env.example .env
```

Edit `.env` and set at least `ORACLE_USER`, `ORACLE_PASSWORD` and `ORACLE_DSN`
(e.g. `192.168.1.50:1521/ORCLPDB1`).

## Run

**Quick / development**

```bash
python app.py
```

**Production (recommended for hosting)** &mdash; use a WSGI server bound to all
interfaces so other machines on the network can reach it:

```bash
# Cross-platform, no PATH issues (uses waitress under the hood)
python serve.py

# Or the waitress console script (Linux/Windows)
waitress-serve --host=0.0.0.0 --port=8080 app:app

# Linux only (gunicorn)
gunicorn -w 2 -b 0.0.0.0:8080 app:app
```

Then management opens **`http://<server-ip>:8080/`** from their browser
(e.g. `http://192.168.1.50:8080/`).

> If a firewall is enabled on the host, allow inbound TCP on the chosen port.

## API endpoints

| Endpoint                       | Description                              |
|--------------------------------|------------------------------------------|
| `GET /`                        | Dashboard page                           |
| `GET /api/health`              | Database connectivity check              |
| `GET /api/summary`             | KPI cards (registrations + encounters)   |
| `GET /api/registrations?period=day\|week\|month` | Trend time series      |
| `GET /api/encounters/today`    | Today's encounter breakdown              |
| `GET /api/doctors/today`       | Today's encounters grouped by provider   |

The page auto-refreshes every 60 seconds.

## Project layout

```
app.py            Flask app + JSON API
config.py         Configuration (env-driven)
db.py             Oracle connection pool (python-oracledb)
queries.py        Dashboard SQL
templates/        dashboard.html
static/css        styling
static/js         chart.js (custom mini chart), dashboard.js
```
