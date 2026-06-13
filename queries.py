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
