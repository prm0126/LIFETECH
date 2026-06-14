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
import db
import queries

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


@app.errorhandler(Exception)
def handle_error(exc):
    app.logger.exception("Unhandled error")
    return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
