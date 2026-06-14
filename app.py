"""
LIFETECH management dashboard.

Serves a single-page dashboard plus a small JSON API:

    GET /                       -> dashboard page
    GET /api/health            -> DB connectivity check
    GET /api/summary           -> KPI cards (registrations + today's encounters)
    GET /api/registrations     -> ?period=day|week|month  time series for chart
    GET /api/encounters/today  -> today's encounter breakdown
    GET /api/doctors/today     -> top providers today

Run on the internal network so management can browse to it:
    python app.py            (dev)
    waitress-serve ...       (production, see README)
"""
import logging

from flask import Flask, jsonify, render_template, request

from config import Config
import custom
import custom_store
import db
import queries
import samples

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
app.config.from_object(Config)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/health")
def health():
    ok = db.ping()
    return jsonify({"ok": ok}), (200 if ok else 503)


@app.route("/api/summary")
def summary():
    reg = queries.registration_summary()
    enc = queries.encounters_today()
    return jsonify({"registrations": reg, "encounters_today": enc})


@app.route("/api/registrations")
def registrations():
    period = request.args.get("period", "day").lower()
    if period not in ("day", "week", "month"):
        period = "day"
    rows = queries.registrations_series(period)
    return jsonify({
        "period": period,
        "labels": [r["period"] for r in rows],
        "values": [r["cnt"] for r in rows],
    })


@app.route("/api/encounters/today")
def encounters_today():
    return jsonify(queries.encounters_today())


@app.route("/api/doctors/today")
def doctors_today():
    return jsonify(queries.encounters_by_doctor_today())


def _period_arg():
    period = request.args.get("period", "day").lower()
    return period if period in ("day", "week", "month", "year") else "day"


@app.route("/api/encounters/doctor-trend")
def doctor_trend():
    period = _period_arg()
    data = queries.encounters_doctor_trend(period)
    data["period"] = period
    return jsonify(data)


@app.route("/api/nurse/summary")
def nurse_summary():
    return jsonify(queries.nurse_summary())


@app.route("/api/nurse/trend")
def nurse_trend():
    period = _period_arg()
    data = queries.nurse_trend(period)
    data["period"] = period
    return jsonify(data)


@app.route("/api/nurse/vitals")
def nurse_vitals():
    return jsonify(queries.nurse_vitals_details())


@app.route("/api/billing/summary")
def billing_summary():
    return jsonify(queries.billing_summary())


@app.route("/api/billing/trend")
def billing_trend():
    period = _period_arg()
    rows = queries.billing_trend(period)
    return jsonify({"period": period,
                    "labels": [r["period"] for r in rows],
                    "values": [r["cnt"] for r in rows]})


@app.route("/api/billing/by-source")
def billing_by_source():
    period = _period_arg()
    rows = queries.billing_by_source(period)
    return jsonify({"period": period,
                    "labels": [r["source"] for r in rows],
                    "values": [r["amount"] for r in rows]})


@app.route("/api/billing/top-services")
def billing_top_services():
    return jsonify(queries.billing_top_services())


def _public(item):
    d = {k: item[k] for k in ("id", "title", "type", "sql", "created")}
    d["params"] = custom.required_params(item["sql"])
    return d


@app.route("/api/custom", methods=["GET"])
def custom_list():
    return jsonify([_public(it) for it in custom_store.list_all()])


@app.route("/api/custom", methods=["POST"])
def custom_create():
    body = request.get_json(force=True, silent=True) or {}
    title = (body.get("title") or "").strip()
    qtype = (body.get("type") or "").strip().lower()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if qtype not in custom.VALID_TYPES:
        return jsonify({"error": "Invalid report type."}), 400
    try:
        sql = custom.clean_sql(body.get("sql") or "")
        custom.validate_params(sql)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_public(custom_store.add(title, qtype, sql))), 201


@app.route("/api/custom/<qid>", methods=["PUT"])
def custom_update(qid):
    body = request.get_json(force=True, silent=True) or {}
    title = (body.get("title") or "").strip()
    qtype = (body.get("type") or "").strip().lower()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if qtype not in custom.VALID_TYPES:
        return jsonify({"error": "Invalid report type."}), 400
    try:
        sql = custom.clean_sql(body.get("sql") or "")
        custom.validate_params(sql)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    updated = custom_store.update(qid, title, qtype, sql)
    if not updated:
        return jsonify({"error": "Report not found."}), 404
    return jsonify(_public(updated))


@app.route("/api/custom/<qid>", methods=["DELETE"])
def custom_delete(qid):
    ok = custom_store.delete(qid)
    return jsonify({"deleted": ok}), (200 if ok else 404)


@app.route("/api/custom/<qid>/run")
def custom_run(qid):
    item = custom_store.get(qid)
    if not item:
        return jsonify({"error": "Report not found."}), 404
    return jsonify(custom.run_saved(item, request.args))


@app.route("/api/custom/seed", methods=["POST"])
def custom_seed():
    """Load the bundled sample billing reports (skips ones already present by title)."""
    existing = {it["title"].strip().lower() for it in custom_store.list_all()}
    added = 0
    for r in samples.BILLING_REPORTS:
        if r["title"].strip().lower() in existing:
            continue
        try:
            sql = custom.clean_sql(r["sql"])
            custom.validate_params(sql)
        except ValueError:
            continue
        custom_store.add(r["title"], r["type"], sql)
        added += 1
    return jsonify({"added": added})


@app.route("/api/custom/preview", methods=["POST"])
def custom_preview():
    body = request.get_json(force=True, silent=True) or {}
    qtype = (body.get("type") or "table").strip().lower()
    if qtype not in custom.VALID_TYPES:
        qtype = "table"
    sql = body.get("sql") or ""
    try:
        custom.validate_params(sql)
        binds = custom.build_binds(sql, body.get("params") or {})
        cols, rows = custom.run_select(sql, binds=binds)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = custom.shape(qtype, cols, rows)
    data["params"] = custom.required_params(sql)
    return jsonify(data)


@app.errorhandler(Exception)
def handle_error(exc):
    app.logger.exception("Unhandled error")
    return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
