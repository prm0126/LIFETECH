"""
Production server entry point (PATH-independent).

Runs the dashboard under the waitress WSGI server without needing the
`waitress-serve` console script on PATH -- handy on Windows. Just run:

    python serve.py
"""
from waitress import serve

from app import app
from config import Config

if __name__ == "__main__":
    print(f"LIFETECH dashboard serving on http://{Config.HOST}:{Config.PORT}/")
    print("Press Ctrl+C to stop.")
    serve(app, host=Config.HOST, port=Config.PORT)
