"""
Data-access layer: builds and runs the dashboard queries against Oracle.

Registration counts come from the patient-demographics source (REG_TABLE)
keyed on REG_DATE_COLUMN. Encounter metrics come from ENC_TABLE keyed on
ENC_DATE_COLUMN with the following business rules:

    urgent care   -> ISEMERGENCY = 1
    consult       -> NVL(ISNONCONSULTENCOUNTER, 0) = 0
    non-consult   -> ISNONCONSULTENCOUNTER = 1
    consulted     -> IS_CONSULTED = 1
"""
import logging

from config import Config
import db

log = logging.getLogger(__name__)


def _enc_valid_clause():
    """Optional filter to exclude cancelled / invalid encounters."""
    return " AND NVL(ISVALID, 1) = 1" if Config.ENC_VALID_ONLY else ""


# --------------------------------------------------------------------------- #
# Registrations
# --------------------------------------------------------------------------- #
def registration_summary():
    """Today / this-week / this-month / total registration counts."""
    sql = f"""
        SELECT
            COUNT(CASE WHEN TRUNC({Config.REG_DATE_COLUMN}) = TRUNC(SYSDATE)
                       THEN 1 END)                                AS today,
            COUNT(CASE WHEN {Config.REG_DATE_COLUMN} >= TRUNC(SYSDATE, 'IW')
                       THEN 1 END)                                AS this_week,
            COUNT(CASE WHEN {Config.REG_DATE_COLUMN} >= TRUNC(SYSDATE, 'MM')
                       THEN 1 END)                                AS this_month,
            COUNT(*)                                              AS total
        FROM {Config.REG_TABLE}
    """
    return db.query_one(sql) or {"today": 0, "this_week": 0, "this_month": 0, "total": 0}


def registrations_day_wise(days=None):
    days = days or Config.DAYS_HISTORY
    sql = f"""
        SELECT TO_CHAR(TRUNC({Config.REG_DATE_COLUMN}), 'YYYY-MM-DD') AS period,
               COUNT(*)                                              AS cnt
        FROM {Config.REG_TABLE}
        WHERE {Config.REG_DATE_COLUMN} >= TRUNC(SYSDATE) - :days
        GROUP BY TRUNC({Config.REG_DATE_COLUMN})
        ORDER BY TRUNC({Config.REG_DATE_COLUMN})
    """
    return db.query_all(sql, {"days": days})


def registrations_week_wise(weeks=None):
    weeks = weeks or Config.WEEKS_HISTORY
    sql = f"""
        SELECT TO_CHAR(TRUNC({Config.REG_DATE_COLUMN}, 'IW'), 'YYYY-MM-DD') AS period,
               COUNT(*)                                                    AS cnt
        FROM {Config.REG_TABLE}
        WHERE {Config.REG_DATE_COLUMN} >= TRUNC(SYSDATE, 'IW') - (:weeks * 7)
        GROUP BY TRUNC({Config.REG_DATE_COLUMN}, 'IW')
        ORDER BY TRUNC({Config.REG_DATE_COLUMN}, 'IW')
    """
    return db.query_all(sql, {"weeks": weeks})


def registrations_month_wise(months=None):
    months = months or Config.MONTHS_HISTORY
    sql = f"""
        SELECT TO_CHAR(TRUNC({Config.REG_DATE_COLUMN}, 'MM'), 'YYYY-MM') AS period,
               COUNT(*)                                                  AS cnt
        FROM {Config.REG_TABLE}
        WHERE {Config.REG_DATE_COLUMN} >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -:months)
        GROUP BY TRUNC({Config.REG_DATE_COLUMN}, 'MM')
        ORDER BY TRUNC({Config.REG_DATE_COLUMN}, 'MM')
    """
    return db.query_all(sql, {"months": months})


def registrations_series(period):
    if period == "week":
        return registrations_week_wise()
    if period == "month":
        return registrations_month_wise()
    return registrations_day_wise()


# --------------------------------------------------------------------------- #
# Encounters
# --------------------------------------------------------------------------- #
def encounters_today():
    """Breakdown of encounters created today."""
    sql = f"""
        SELECT
            COUNT(*)                                                       AS total,
            COUNT(CASE WHEN ISEMERGENCY = 1 THEN 1 END)                    AS urgent_care,
            COUNT(CASE WHEN NVL(ISNONCONSULTENCOUNTER, 0) = 0 THEN 1 END)  AS consult,
            COUNT(CASE WHEN ISNONCONSULTENCOUNTER = 1 THEN 1 END)          AS non_consult,
            COUNT(CASE WHEN IS_CONSULTED = 1 THEN 1 END)                   AS consulted
        FROM {Config.ENC_TABLE}
        WHERE TRUNC({Config.ENC_DATE_COLUMN}) = TRUNC(SYSDATE){_enc_valid_clause()}
    """
    return db.query_one(sql) or {
        "total": 0, "urgent_care": 0, "consult": 0,
        "non_consult": 0, "consulted": 0,
    }


def _bucket(period, col):
    """Return (trunc_expression, to_char_format, where_window_expression)."""
    if period == "week":
        return (f"TRUNC({col}, 'IW')", "YYYY-MM-DD",
                f"{col} >= TRUNC(SYSDATE, 'IW') - ({Config.WEEKS_HISTORY} * 7)")
    if period == "month":
        return (f"TRUNC({col}, 'MM')", "YYYY-MM",
                f"{col} >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -{Config.MONTHS_HISTORY})")
    if period == "year":
        return (f"TRUNC({col}, 'YYYY')", "YYYY",
                f"{col} >= ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), -{Config.YEARS_HISTORY * 12})")
    # default: day
    return (f"TRUNC({col})", "YYYY-MM-DD",
            f"{col} >= TRUNC(SYSDATE) - {Config.DAYS_HISTORY}")


def _pivot(rows, key, label, value, top_n):
    """Pivot flat rows -> {labels, series}. Keeps top_n keys, groups rest as Others."""
    labels = sorted({r[label] for r in rows})
    idx = {lab: i for i, lab in enumerate(labels)}
    totals, grids = {}, {}
    for r in rows:
        k = r[key] if r[key] is not None else "Unknown"
        totals[k] = totals.get(k, 0) + (r[value] or 0)
        grids.setdefault(k, [0] * len(labels))[idx[r[label]]] += (r[value] or 0)
    top = sorted(totals, key=totals.get, reverse=True)[:top_n]
    series = [{"name": str(k), "values": grids[k]} for k in top]
    others = [k for k in totals if k not in top]
    if others:
        merged = [0] * len(labels)
        for k in others:
            for i, v in enumerate(grids[k]):
                merged[i] += v
        series.append({"name": "Others", "values": merged})
    return {"labels": labels, "series": series}


def encounters_doctor_trend(period):
    """Encounters over time split by doctor (multi-series). period: day/week/month/year."""
    trunc, fmt, window = _bucket(period, Config.ENC_DATE_COLUMN)
    sql = f"""
        SELECT TO_CHAR({trunc}, '{fmt}')                              AS period,
               NVL({Config.EMPLOYEE_NAME_FN}(PROVIDER_ID), PROVIDER_ID) AS doctor,
               COUNT(*)                                               AS cnt
        FROM {Config.ENC_TABLE}
        WHERE {window}{_enc_valid_clause()}
          AND PROVIDER_ID IS NOT NULL
        GROUP BY TO_CHAR({trunc}, '{fmt}'),
                 NVL({Config.EMPLOYEE_NAME_FN}(PROVIDER_ID), PROVIDER_ID)
        ORDER BY period
    """
    try:
        rows = db.query_all(sql)
    except Exception as exc:  # noqa: BLE001
        log.warning("doctor trend unavailable: %s", exc)
        return {"labels": [], "series": []}
    return _pivot(rows, "doctor", "period", "cnt", Config.TOP_DOCTORS)


# --------------------------------------------------------------------------- #
# Nurse analysis (EMR)
# --------------------------------------------------------------------------- #
def _visit_filter(alias="c"):
    return (f"{alias}.isvalid = 1 "
            f"AND {alias}.template_type = {Config.EMR_VISIT_TEMPLATE_TYPE}")


def nurse_summary():
    """Today's nurse KPIs: patients with notes / vitals, vitals records, active nurses."""
    v = Config.EMR_VISIT_TABLE
    vit = Config.EMR_VITALS_TABLE
    dcol = Config.EMR_VISIT_DATE_COL
    pcol = Config.EMR_VISIT_PATIENT_COL
    vf = _visit_filter("c")
    sql = f"""
        SELECT
          (SELECT COUNT(DISTINCT c.{pcol}) FROM {v} c
             WHERE TRUNC(c.{dcol}) = TRUNC(SYSDATE) AND {vf})              AS notes_patients,
          (SELECT COUNT(DISTINCT a.mrno) FROM {vit} a
             JOIN {v} c ON c.emr_provider_visit_id = a.emr_provider_visit_id
             WHERE TRUNC(c.{dcol}) = TRUNC(SYSDATE) AND {vf})             AS vitals_patients,
          (SELECT COUNT(*) FROM {vit} a
             JOIN {v} c ON c.emr_provider_visit_id = a.emr_provider_visit_id
             WHERE TRUNC(c.{dcol}) = TRUNC(SYSDATE) AND {vf})             AS vitals_records,
          (SELECT COUNT(DISTINCT a.entered_by) FROM {vit} a
             JOIN {v} c ON c.emr_provider_visit_id = a.emr_provider_visit_id
             WHERE TRUNC(c.{dcol}) = TRUNC(SYSDATE) AND {vf})             AS nurses_active
        FROM DUAL
    """
    return db.query_one(sql) or {
        "notes_patients": 0, "vitals_patients": 0,
        "vitals_records": 0, "nurses_active": 0,
    }


def nurse_trend(period):
    """Patients-with-notes vs patients-with-vitals over time (two series)."""
    v = Config.EMR_VISIT_TABLE
    vit = Config.EMR_VITALS_TABLE
    dcol = Config.EMR_VISIT_DATE_COL
    pcol = Config.EMR_VISIT_PATIENT_COL
    trunc, fmt, window = _bucket(period, f"c.{dcol}")
    notes_sql = f"""
        SELECT TO_CHAR({trunc}, '{fmt}') AS period, COUNT(DISTINCT c.{pcol}) AS cnt
        FROM {v} c
        WHERE {window} AND {_visit_filter('c')}
        GROUP BY TO_CHAR({trunc}, '{fmt}') ORDER BY period
    """
    vitals_sql = f"""
        SELECT TO_CHAR({trunc}, '{fmt}') AS period, COUNT(DISTINCT a.mrno) AS cnt
        FROM {vit} a
        JOIN {v} c ON c.emr_provider_visit_id = a.emr_provider_visit_id
        WHERE {window} AND {_visit_filter('c')}
        GROUP BY TO_CHAR({trunc}, '{fmt}') ORDER BY period
    """
    try:
        notes = {r["period"]: r["cnt"] for r in db.query_all(notes_sql)}
        vitals = {r["period"]: r["cnt"] for r in db.query_all(vitals_sql)}
    except Exception as exc:  # noqa: BLE001
        log.warning("nurse trend unavailable: %s", exc)
        return {"labels": [], "series": []}
    labels = sorted(set(notes) | set(vitals))
    return {
        "labels": labels,
        "series": [
            {"name": "Patients w/ Notes", "values": [notes.get(l, 0) for l in labels]},
            {"name": "Patients w/ Vitals", "values": [vitals.get(l, 0) for l in labels]},
        ],
    }


def nurse_vitals_details(limit=50):
    """Recent vitals entered today, with nurse name resolved when possible."""
    v = Config.EMR_VISIT_TABLE
    vit = Config.EMR_VITALS_TABLE
    look = Config.EMR_LOOKUP_TABLE
    dcol = Config.EMR_VISIT_DATE_COL
    base = f"""
            SELECT TO_CHAR(c.{dcol}, 'YYYY-MM-DD') AS emr_date,
                   a.mrno                          AS mrno,
                   b.lookup_value                  AS vital,
                   TO_CHAR(a.vs_phys_date, 'YYYY-MM-DD HH24:MI') AS vs_phys_date,
                   {{entered}}                     AS entered_by
            FROM {vit} a
            JOIN {look} b ON b.emr_lookup_id = a.VS_PHYS_ID
            JOIN {v} c ON c.emr_provider_visit_id = a.emr_provider_visit_id
            WHERE c.template_type = {Config.EMR_VISIT_TEMPLATE_TYPE}
              AND c.isvalid = 1
              AND TRUNC(c.{dcol}) = TRUNC(SYSDATE)
            ORDER BY a.vs_phys_date DESC
    """
    named = f"NVL({Config.EMPLOYEE_NAME_FN}(a.entered_by), a.entered_by)"
    for entered in (named, "a.entered_by"):
        sql = f"SELECT * FROM (\n{base.format(entered=entered)}\n) WHERE ROWNUM <= :limit"
        try:
            return db.query_all(sql, {"limit": limit})
        except Exception as exc:  # noqa: BLE001
            log.warning("vitals details (entered=%s) failed: %s", entered, exc)
    return []


def encounters_by_doctor_today(limit=10):
    """Top providers by encounter count today (uses the employee-name function).

    Degrades gracefully if the function or PROVIDER_ID is unavailable.
    """
    sql = f"""
        SELECT doctor, cnt FROM (
            SELECT NVL({Config.EMPLOYEE_NAME_FN}(PROVIDER_ID), PROVIDER_ID) AS doctor,
                   COUNT(*)                                                 AS cnt
            FROM {Config.ENC_TABLE}
            WHERE TRUNC({Config.ENC_DATE_COLUMN}) = TRUNC(SYSDATE){_enc_valid_clause()}
              AND PROVIDER_ID IS NOT NULL
            GROUP BY PROVIDER_ID
            ORDER BY COUNT(*) DESC
        ) WHERE ROWNUM <= :limit
    """
    try:
        return db.query_all(sql, {"limit": limit})
    except Exception as exc:  # noqa: BLE001
        log.warning("doctor breakdown unavailable: %s", exc)
        return []
