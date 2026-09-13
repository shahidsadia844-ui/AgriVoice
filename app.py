#!/usr/bin/env python3
"""
AgriVoice / AgriPak - Combined Flask server
=============================================
This single file:
  1. Serves the AgriPak frontend (the HTML pages you designed).
  2. Exposes the AgriVoice AI features (originally a CLI script) as a
     small JSON API that the frontend calls with fetch().

Run mode:
  - If GEMINI_API_KEY is not set, everything runs in DEMO MODE with
    mock responses (exactly like the original agrivoice.py CLI did).
  - Set GEMINI_API_KEY as an environment variable to get real answers.

Start it with:
    python app.py
Then open:
    http://127.0.0.1:5000/01_splash.html
"""

import os
import io
import json
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------
# Paths / app setup
# ---------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DB_PATH = os.path.join(BASE_DIR, "agrivoice.db")

app = Flask(__name__)
CORS(app)  # allow the frontend pages to call the API freely

# ---------------------------------------------------------------------
# Database setup (unchanged from the original agrivoice.py)
# ---------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            crop TEXT,
            disease TEXT,
            confidence TEXT,
            treatment TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            question TEXT,
            answer TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            temperature_C REAL,
            humidity_percent REAL
        )
    """)
    conn.commit()
    conn.close()


def save_diagnosis(result: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO diagnoses (timestamp, crop, disease, confidence, treatment) VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now().isoformat(timespec="seconds"),
            result.get("crop", ""),
            result.get("disease", ""),
            result.get("confidence", ""),
            result.get("treatment", ""),
        ),
    )
    conn.commit()
    conn.close()


def save_question(question: str, answer: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO questions (timestamp, question, answer) VALUES (?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), question, answer),
    )
    conn.commit()
    conn.close()


def save_weather(latitude, longitude, weather: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO weather_checks (timestamp, latitude, longitude, temperature_C, humidity_percent) VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now().isoformat(timespec="seconds"),
            latitude,
            longitude,
            weather.get("temperature_C"),
            weather.get("humidity_percent"),
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# Gemini / demo-mode setup (unchanged logic from agrivoice.py)
# ---------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEMO_MODE = not bool(GEMINI_API_KEY)

try:
    import google.generativeai as genai
    if not DEMO_MODE:
        genai.configure(api_key=GEMINI_API_KEY)
except ImportError:
    genai = None
    DEMO_MODE = True

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import requests


def _banner():
    mode = "DEMO MODE (no GEMINI_API_KEY found)" if DEMO_MODE else "LIVE MODE (Gemini connected)"
    print("=" * 55)
    print(f"  AgriVoice Flask API  --  {mode}")
    print("=" * 55)


# ---------------------------------------------------------------------
# Feature 1: Crop disease diagnosis from an image
# ---------------------------------------------------------------------

def diagnose_crop_image_bytes(image_bytes: bytes) -> dict:
    if DEMO_MODE:
        return {
            "crop": "Wheat (demo guess)",
            "disease": "Leaf Rust (mock diagnosis)",
            "confidence": "N/A - demo mode",
            "treatment": (
                "This is a MOCK response since no GEMINI_API_KEY is set. "
                "Remove affected leaves, apply a fungicide spray such as "
                "Propiconazole 25% EC (200ml/acre), and ensure good field "
                "drainage to slow fungal spread."
            ),
        }

    try:
        if not PIL_AVAILABLE:
            return {"error": "Pillow (PIL) not installed. Run: pip install pillow"}

        img = Image.open(io.BytesIO(image_bytes))

        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "You are an agricultural expert. Look at this leaf image and "
            "identify: 1) the crop/plant type, 2) any visible disease or "
            "pest damage, 3) your confidence level, 4) a practical treatment "
            "recommendation for a smallholder farmer. "
            "Respond ONLY with valid JSON in this exact shape: "
            '{"crop": "...", "disease": "...", "confidence": "...", "treatment": "..."}'
        )

        response = model.generate_content([prompt, img])
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    except json.JSONDecodeError:
        return {"error": "Could not parse model response as JSON."}
    except Exception as e:
        return {"error": f"Diagnosis failed: {e}"}


# ---------------------------------------------------------------------
# Feature 2: Text/voice farming assistant
# ---------------------------------------------------------------------

def ask_assistant(question: str) -> str:
    if DEMO_MODE:
        return (
            f"[DEMO MODE] You asked: '{question}'. "
            "In live mode, Gemini would give a detailed, practical farming answer here. "
            "Set your GEMINI_API_KEY environment variable to get real responses."
        )
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "You are AgriVoice, a friendly farming assistant for smallholder "
            "farmers. Answer this question simply, practically, and briefly:\n\n"
            f"{question}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error getting response from Gemini: {e}"


# ---------------------------------------------------------------------
# Feature 3: Local weather + mock market price snapshot
# ---------------------------------------------------------------------

def get_local_snapshot(latitude: float, longitude: float) -> dict:
    snapshot = {"location": {"latitude": latitude, "longitude": longitude}}
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        snapshot["weather"] = {
            "temperature_C": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        }
    except Exception as e:
        snapshot["weather"] = {"error": f"Could not fetch weather: {e}"}

    snapshot["market_prices_mock"] = {
        "wheat_per_40kg": "PKR 3,200 (mock)",
        "tomato_per_kg": "PKR 90 (mock)",
        "potato_per_kg": "PKR 65 (mock)",
    }
    return snapshot


# ---------------------------------------------------------------------
# API ROUTES  (these are what the frontend JS calls with fetch())
# ---------------------------------------------------------------------

@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please send a 'question' field."}), 400

    answer = ask_assistant(question)
    save_question(question, answer)
    return jsonify({"answer": answer, "demo_mode": DEMO_MODE})


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    if "image" not in request.files:
        return jsonify({"error": "No 'image' file in the request."}), 400

    image_file = request.files["image"]
    image_bytes = image_file.read()

    result = diagnose_crop_image_bytes(image_bytes)
    if "error" not in result:
        save_diagnosis(result)
    return jsonify({**result, "demo_mode": DEMO_MODE})


@app.route("/api/weather", methods=["GET"])
def api_weather():
    lat = request.args.get("lat", default=31.5204, type=float)  # default: Lahore
    lon = request.args.get("lon", default=74.3587, type=float)
    snapshot = get_local_snapshot(lat, lon)
    save_weather(lat, lon, snapshot.get("weather", {}))
    return jsonify(snapshot)


@app.route("/api/history", methods=["GET"])
def api_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM diagnoses ORDER BY id DESC LIMIT 20")
    diagnoses = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM questions ORDER BY id DESC LIMIT 20")
    questions = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM weather_checks ORDER BY id DESC LIMIT 20")
    weather_checks = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({
        "diagnoses": diagnoses,
        "questions": questions,
        "weather_checks": weather_checks,
    })


# ---------------------------------------------------------------------
# STATIC FRONTEND (serves the HTML/CSS/JS pages you designed)
# ---------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "01_splash.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    init_db()
    _banner()
    app.run(host="0.0.0.0", port=5000, debug=True)
