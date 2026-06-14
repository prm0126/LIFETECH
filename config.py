"""
Central configuration for the LIFETECH dashboard.

All values can be overridden with environment variables (loaded from a `.env`
file if present). Table / column names are configurable so the app can be
pointed at a view or a renamed table without touching the SQL.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


class Config:
    # ---- Oracle connection -------------------------------------------------
    # Either supply ORACLE_DSN (e.g. "host:1521/service") OR the individual
    # ORACLE_HOST / ORACLE_PORT / ORACLE_SERVICE values below.
    ORACLE_USER = os.getenv("ORACLE_USER", "")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
    ORACLE_DSN = os.getenv("ORACLE_DSN", "")
    ORACLE_HOST = os.getenv("ORACLE_HOST", "")
    ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
    ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "")

    # Use thick mode (needs the Oracle client). Since the client is already
    # installed on this server, thick mode is enabled by default. Set
    # ORACLE_THICK_MODE=0 to use the pure-python thin driver instead.
    ORACLE_THICK_MODE = _as_bool(os.getenv("ORACLE_THICK_MODE"), default=True)
    # Optional explicit path to the Oracle client libraries (instant client).
    ORACLE_CLIENT_LIB_DIR = os.getenv("ORACLE_CLIENT_LIB_DIR", "") or None

    # Connection pool sizing
    POOL_MIN = int(os.getenv("ORACLE_POOL_MIN", "1"))
    POOL_MAX = int(os.getenv("ORACLE_POOL_MAX", "4"))
    POOL_INCREMENT = int(os.getenv("ORACLE_POOL_INCREMENT", "1"))

    # ---- Schema / object names --------------------------------------------
    # Registration source (patient demographics). Used for day/week/month
    # registration counts via its date column.
    REG_TABLE = os.getenv("REG_TABLE", "PAT_PATIENT_DEMOGRAPHICS")
    REG_DATE_COLUMN = os.getenv("REG_DATE_COLUMN", "REGISTERED_SINCE")

    # Encounter source.
    ENC_TABLE = os.getenv("ENC_TABLE", "PAT_FIN_ENCOUNTER")
    ENC_DATE_COLUMN = os.getenv("ENC_DATE_COLUMN", "START_DATE")

    # Only count valid (not-cancelled) encounters when True.
    ENC_VALID_ONLY = _as_bool(os.getenv("ENC_VALID_ONLY"), default=True)

    # Employee-name lookup function (schema-qualify if needed).
    EMPLOYEE_NAME_FN = os.getenv("EMPLOYEE_NAME_FN", "GET_EMPLOYEE_NAME")

    # ---- Billing objects ---------------------------------------------------
    BILL_GEN_TABLE = os.getenv("BILL_GEN_TABLE", "GEN_PAT_BILLING")
    BILL_INV_TABLE = os.getenv("BILL_INV_TABLE", "INV_PAT_BILLING")
    BILL_CON_TABLE = os.getenv("BILL_CON_TABLE", "CON_PAT_BILLING")
    BILL_PH_TABLE = os.getenv("BILL_PH_TABLE", "PH_PAT_BILLING")
    SERVICE_TABLE = os.getenv("SERVICE_TABLE", "INV_MAST_SERVICE")
    BILL_DATE_COLUMN = os.getenv("BILL_DATE_COLUMN", "BILL_DATE")
    BILL_AMOUNT_COLUMN = os.getenv("BILL_AMOUNT_COLUMN", "NET_AMOUNT")

    # ---- Nurse analysis / EMR objects -------------------------------------
    # A nurse note is considered present when a row exists in the provider
    # visit table (template_type = EMR_VISIT_TEMPLATE_TYPE, isvalid = 1).
    EMR_VISIT_TABLE = os.getenv("EMR_VISIT_TABLE", "emr_provider_visit")
    EMR_VISIT_DATE_COL = os.getenv("EMR_VISIT_DATE_COL", "EMR_DATE")
    EMR_VISIT_PATIENT_COL = os.getenv("EMR_VISIT_PATIENT_COL", "MRNO")
    EMR_VISIT_TEMPLATE_TYPE = int(os.getenv("EMR_VISIT_TEMPLATE_TYPE", "1"))
    EMR_VITALS_TABLE = os.getenv("EMR_VITALS_TABLE", "EMR_PAT_VITAL_SIGN_PHYS")
    EMR_LOOKUP_TABLE = os.getenv("EMR_LOOKUP_TABLE", "emr_lookup")

    # ---- Chart history windows --------------------------------------------
    DAYS_HISTORY = int(os.getenv("DAYS_HISTORY", "30"))
    WEEKS_HISTORY = int(os.getenv("WEEKS_HISTORY", "12"))
    MONTHS_HISTORY = int(os.getenv("MONTHS_HISTORY", "12"))
    YEARS_HISTORY = int(os.getenv("YEARS_HISTORY", "5"))
    # Max distinct doctors plotted on the trend (rest grouped as "Others").
    TOP_DOCTORS = int(os.getenv("TOP_DOCTORS", "8"))

    # ---- App ---------------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "lifetech-dashboard")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8080"))

    # ---- Custom reports (web query builder) -------------------------------
    # File where user-defined reports are saved (created automatically).
    CUSTOM_STORE_FILE = os.getenv("CUSTOM_STORE_FILE", "custom_queries.json")
    # Max rows fetched per custom query (safety cap).
    CUSTOM_MAX_ROWS = int(os.getenv("CUSTOM_MAX_ROWS", "500"))

    @classmethod
    def dsn(cls):
        if cls.ORACLE_DSN:
            return cls.ORACLE_DSN
        if cls.ORACLE_HOST and cls.ORACLE_SERVICE:
            return f"{cls.ORACLE_HOST}:{cls.ORACLE_PORT}/{cls.ORACLE_SERVICE}"
        raise RuntimeError(
            "Oracle DSN not configured. Set ORACLE_DSN or "
            "ORACLE_HOST/ORACLE_PORT/ORACLE_SERVICE in your environment/.env."
        )
