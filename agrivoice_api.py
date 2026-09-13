#!/usr/bin/env python3
"""
AgriPak / AgriVoice Backend API
--------------------------------
FastAPI server that powers the AgriPak Frontend.

Matches frontend features:
  - Auth: signup / signin / forgot-password (name, contact/email, password)
  - AgriVoice chat (text + optional image)
  - Leaf disease scan (image upload → diagnosis)
  - Weather (Open-Meteo, default Lahore)
  - Mandi rates (crop + city based, matches frontend mock data)
  - Crop info & selected crop
  - Profile & history
  - Field details

Keeps original Gemini Vision + text assistant logic.
Falls back to DEMO MODE when GEMINI_API_KEY is not set.

Run:
  pip install -r requirements.txt
  uvicorn agrivoice_api:app --host 0.0.0.0 --port 8000 --reload

Frontend should call: http://localhost:8000/api/...
"""

from __future__ import annotations

import os
import sys
import json
import sqlite3
import hashlib
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, EmailStr

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "agrivoice.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Gemini / demo setup (same spirit as original CLI)
# ---------------------------------------------------------------------------

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
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            selected_crop TEXT DEFAULT 'Wheat',
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            image_path TEXT,
            crop TEXT,
            disease TEXT,
            treatment TEXT,
            confidence TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            question TEXT,
            answer TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weather_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            temperature_C REAL,
            humidity_percent REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            crop TEXT,
            area TEXT,
            location TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires),
    )
    conn.commit()
    conn.close()
    return token


def get_user_from_token(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT u.* FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.token = ?",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def require_user(user: Optional[dict] = Depends(get_user_from_token)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Login required. Send Authorization: Bearer <token>")
    return user


# ---------------------------------------------------------------------------
# Original core logic (adapted)
# ---------------------------------------------------------------------------

def diagnose_crop_image(image_path: str) -> dict:
    if not os.path.exists(image_path):
        return {"error": f"Image not found at path: {image_path}"}

    if DEMO_MODE:
        return {
            "crop": "Wheat",
            "disease": "Wheat Leaf Rust (پتے کا زنگ)",
            "confidence": "94% (demo)",
            "treatment": (
                "متاثرہ پتوں کو فوری طور پر ہٹا دیں، متاثرہ حصے کو تلف کریں، "
                "اور تجویز کردہ فنجی سائیڈ کا اسپرے 3 دن کے اندر کریں۔"
            ),
        }

    try:
        if not PIL_AVAILABLE:
            return {"error": "Pillow (PIL) not installed. Run: pip install pillow"}

        img = Image.open(image_path)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "You are an agricultural expert for Pakistani farmers. Look at this leaf image and "
            "identify: 1) the crop/plant type, 2) any visible disease or pest damage, "
            "3) your confidence level, 4) a practical treatment recommendation. "
            "Respond ONLY with valid JSON: "
            '{"crop": "...", "disease": "...", "confidence": "...", "treatment": "..."}'
        )
        response = model.generate_content([prompt, img])
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "Could not parse model response as JSON.", "raw_response": text}
    except Exception as e:
        return {"error": f"Diagnosis failed: {e}"}


def ask_assistant(question: str, speak: bool = False) -> str:
    # Frontend-style smart replies for common Urdu/English keywords (works even in demo)
    q = question.lower()
    if "leaf-scan-result:" in q or "زنگ" in question or "rust" in q:
        disease = question.replace("leaf-scan-result:", "").strip()
        return (
            f"اسکین مکمل ہوگئی۔ تشخیص: {disease}۔ "
            "متاثرہ پتوں کو فوری طور پر ہٹا دیں، متاثرہ حصے کو تلف کریں، "
            "اور تجویز کردہ فنجی سائیڈ کا اسپرے 3 دن کے اندر کریں۔ مزید سوال پوچھیں۔"
        )
    if "گندم" in question or "wheat" in q:
        return "آج لاہور منڈی میں گندم کا ریٹ 3,900 روپے فی من ہے۔"
    if "پانی" in question or "water" in q or "irrigat" in q:
        return "مٹی میں نمی 68% ہے، آج فصل کو مزید پانی دینے کی ضرورت نہیں ہے۔"
    if "موسم" in question or "weather" in q:
        return "آج کا درجہ حرارت 31 ڈگری سینٹی گریڈ ہے اور موسم بالکل صاف ہے۔"

    if DEMO_MODE:
        return (
            f"[DEMO] آپ نے پوچھا: '{question}'۔ "
            "لائیو موڈ میں Gemini تفصیلی مشورہ دے گا۔ GEMINI_API_KEY سیٹ کریں۔"
        )

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "You are AgriVoice, a friendly farming assistant for smallholder farmers in Pakistan. "
            "Answer simply, practically, and briefly. Prefer Urdu mixed with simple English when helpful.\n\n"
            f"Question: {question}"
        )
        response = model.generate_content(prompt)
        answer = response.text.strip()
    except Exception as e:
        answer = f"Sorry, assistant error: {e}"

    if speak and GTTS_AVAILABLE:
        try:
            tts = gTTS(text=answer, lang="ur")
            tts.save(str(BASE_DIR / "agrivoice_response.mp3"))
        except Exception:
            pass

    return answer


def get_local_snapshot(lat: float = 31.5204, lon: float = 74.3587) -> dict:
    snapshot: Dict[str, Any] = {
        "location": {"latitude": lat, "longitude": lon},
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&timezone=Asia%2FKarachi"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})
        daily = data.get("daily", {})
        snapshot["weather"] = {
            "temperature_C": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
        }
        # Build a simple 7-day style forecast for frontend
        days = []
        times = daily.get("time", [])[:7]
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        rain = daily.get("precipitation_probability_max", [])
        for i, t in enumerate(times):
            days.append({
                "date": t,
                "temp_max": tmax[i] if i < len(tmax) else None,
                "temp_min": tmin[i] if i < len(tmin) else None,
                "rain_chance": rain[i] if i < len(rain) else None,
            })
        snapshot["forecast"] = days
    except Exception as e:
        snapshot["weather"] = {"error": f"Could not fetch weather: {e}"}
        snapshot["forecast"] = []

    return snapshot


# Mandi rates matching frontend 08_mandi_rates.html data
MANDI_RATES = {
    "Wheat": [
        {"city": "Lahore", "price": 3950, "change": 50, "distance": 5, "unit": "Rs / 40kg"},
        {"city": "Sahiwal", "price": 3920, "change": 20, "distance": 180, "unit": "Rs / 40kg"},
        {"city": "Faisalabad", "price": 3900, "change": -10, "distance": 130, "unit": "Rs / 40kg"},
        {"city": "Multan", "price": 3820, "change": 30, "distance": 340, "unit": "Rs / 40kg"},
    ],
    "Cotton": [
        {"city": "Multan", "price": 8500, "change": 120, "distance": 340, "unit": "Rs / 40kg"},
        {"city": "Bahawalpur", "price": 8380, "change": 90, "distance": 420, "unit": "Rs / 40kg"},
        {"city": "Sahiwal", "price": 8300, "change": -40, "distance": 180, "unit": "Rs / 40kg"},
        {"city": "Rahim Yar Khan", "price": 8150, "change": 60, "distance": 480, "unit": "Rs / 40kg"},
    ],
    "Maize": [
        {"city": "Sahiwal", "price": 2400, "change": 0, "distance": 180, "unit": "Rs / 40kg"},
        {"city": "Okara", "price": 2380, "change": 10, "distance": 150, "unit": "Rs / 40kg"},
        {"city": "Faisalabad", "price": 2350, "change": -15, "distance": 130, "unit": "Rs / 40kg"},
        {"city": "Lahore", "price": 2320, "change": 5, "distance": 5, "unit": "Rs / 40kg"},
    ],
    "Sugarcane": [
        {"city": "Faisalabad", "price": 425, "change": 5, "distance": 130, "unit": "Rs / 40kg"},
        {"city": "Sahiwal", "price": 420, "change": 0, "distance": 180, "unit": "Rs / 40kg"},
        {"city": "Lahore", "price": 415, "change": -5, "distance": 5, "unit": "Rs / 40kg"},
        {"city": "Multan", "price": 410, "change": 10, "distance": 340, "unit": "Rs / 40kg"},
    ],
}

CROP_INFO = {
    "Wheat": {
        "uName": "Wheat / گندم",
        "moisture": "68%",
        "ph": "6.5",
        "rate": "Rs. 3,900",
        "trend": "+2.4%",
        "season": "Rabi (Nov–Apr)",
        "tips": "گندم کو بروقت آبپاشی اور نائٹروجن کھاد دیں۔ زنگ کی نگرانی کریں۔",
    },
    "Cotton": {
        "uName": "Cotton / کپاس",
        "moisture": "45%",
        "ph": "7.2",
        "rate": "Rs. 8,500",
        "trend": "+1.8%",
        "season": "Kharif (May–Oct)",
        "tips": "سفید مکھی اور بال ورم سے بچاؤ کے لیے باقاعدہ سپرے کریں۔",
    },
    "Maize": {
        "uName": "Maize / مکئی",
        "moisture": "55%",
        "ph": "6.0",
        "rate": "Rs. 2,400",
        "trend": "-0.5%",
        "season": "Kharif / Spring",
        "tips": "مکئی کو اچھی نکاسی والی مٹی اور متوازن کھاد درکار ہے۔",
    },
    "Sugarcane": {
        "uName": "Sugarcane / گنا",
        "moisture": "75%",
        "ph": "6.8",
        "rate": "Rs. 425",
        "trend": "Stable",
        "season": "Year-round (planted Feb–Mar)",
        "tips": "گنے کو زیادہ پانی اور پوٹاش کھاد پسند ہے۔",
    },
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=3)
    contact: str = Field(..., min_length=5)  # phone or email
    password: str = Field(..., min_length=6)


class SigninRequest(BaseModel):
    contact: str  # frontend uses "email" field but can be phone too
    password: str


class ChatRequest(BaseModel):
    message: str
    speak: bool = False


class CropSelectRequest(BaseModel):
    crop: str


class WeatherRequest(BaseModel):
    latitude: float = 31.5204
    longitude: float = 74.3587


class FieldCreate(BaseModel):
    name: str
    crop: str
    area: str = ""
    location: str = ""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgriPak / AgriVoice API",
    description="Backend for AgriPak Frontend (auth, AgriVoice chat, leaf scan, weather, mandi rates)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    mode = "DEMO MODE (no GEMINI_API_KEY)" if DEMO_MODE else "LIVE MODE (Gemini)"
    print(f"AgriVoice API starting — {mode}")


@app.get("/")
def root():
    return {
        "service": "AgriPak / AgriVoice API",
        "mode": "demo" if DEMO_MODE else "live",
        "docs": "/docs",
        "endpoints": [
            "POST /api/auth/signup",
            "POST /api/auth/signin",
            "GET  /api/profile",
            "POST /api/chat",
            "POST /api/leaf-scan",
            "GET  /api/weather",
            "GET  /api/mandi-rates",
            "GET  /api/crops",
            "POST /api/crop/select",
            "GET  /api/history",
            "GET  /api/fields",
            "POST /api/fields",
        ],
    }


# ---- Auth -----------------------------------------------------------------

@app.post("/api/auth/signup")
def signup(body: SignupRequest):
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM users WHERE contact = ?", (body.contact.strip(),)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Account already exists with this contact/email")

    cur = conn.execute(
        "INSERT INTO users (name, contact, password_hash, selected_crop, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            body.name.strip(),
            body.contact.strip(),
            hash_password(body.password),
            "Wheat",
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    token = create_token(user_id)
    return {
        "ok": True,
        "message": "Account created",
        "token": token,
        "user": {
            "id": user_id,
            "name": body.name.strip(),
            "contact": body.contact.strip(),
            "selected_crop": "Wheat",
        },
    }


@app.post("/api/auth/signin")
def signin(body: SigninRequest):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE contact = ?", (body.contact.strip(),)
    ).fetchone()
    conn.close()
    if not row or row["password_hash"] != hash_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid contact or password")

    token = create_token(row["id"])
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": row["id"],
            "name": row["name"],
            "contact": row["contact"],
            "selected_crop": row["selected_crop"] or "Wheat",
        },
    }


@app.post("/api/auth/forgot-password")
def forgot_password(contact: str = Form(...)):
    """Demo: just confirms contact exists. Real SMS/email reset can be added later."""
    conn = get_conn()
    row = conn.execute("SELECT id, name FROM users WHERE contact = ?", (contact.strip(),)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No account found with this contact")
    return {
        "ok": True,
        "message": f"Password reset link would be sent to {contact} (demo — not sent).",
        "user_name": row["name"],
    }


# ---- Profile & crop selection ---------------------------------------------

@app.get("/api/profile")
def profile(user: dict = Depends(require_user)):
    return {
        "id": user["id"],
        "name": user["name"],
        "contact": user["contact"],
        "selected_crop": user.get("selected_crop") or "Wheat",
        "created_at": user.get("created_at"),
    }


@app.post("/api/crop/select")
def select_crop(body: CropSelectRequest, user: dict = Depends(require_user)):
    crop = body.crop.strip()
    if crop not in CROP_INFO:
        raise HTTPException(status_code=400, detail=f"Unknown crop. Choose from: {list(CROP_INFO.keys())}")
    conn = get_conn()
    conn.execute("UPDATE users SET selected_crop = ? WHERE id = ?", (crop, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True, "selected_crop": crop, "info": CROP_INFO[crop]}


@app.get("/api/crops")
def list_crops():
    return {"crops": CROP_INFO}


@app.get("/api/crop/{name}")
def crop_detail(name: str):
    info = CROP_INFO.get(name) or CROP_INFO.get(name.title())
    if not info:
        raise HTTPException(status_code=404, detail="Crop not found")
    return {"crop": name, **info}


# ---- AgriVoice Chat -------------------------------------------------------

@app.post("/api/chat")
def chat(body: ChatRequest, user: Optional[dict] = Depends(get_user_from_token)):
    answer = ask_assistant(body.message, speak=body.speak)
    user_id = user["id"] if user else None
    conn = get_conn()
    conn.execute(
        "INSERT INTO questions (user_id, timestamp, question, answer) VALUES (?, ?, ?, ?)",
        (user_id, datetime.now().isoformat(timespec="seconds"), body.message, answer),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "question": body.message, "answer": answer, "mode": "demo" if DEMO_MODE else "live"}


# ---- Leaf Scan ------------------------------------------------------------

@app.post("/api/leaf-scan")
async def leaf_scan(
    file: UploadFile = File(...),
    user: Optional[dict] = Depends(get_user_from_token),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file")

    suffix = Path(file.filename or "leaf.jpg").suffix or ".jpg"
    save_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{suffix}"
    save_path = UPLOAD_DIR / save_name

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    result = diagnose_crop_image(str(save_path))

    if "error" not in result:
        user_id = user["id"] if user else None
        conn = get_conn()
        conn.execute(
            """INSERT INTO diagnoses
               (user_id, timestamp, image_path, crop, disease, treatment, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                datetime.now().isoformat(timespec="seconds"),
                str(save_path),
                result.get("crop", ""),
                result.get("disease", ""),
                result.get("treatment", ""),
                result.get("confidence", ""),
            ),
        )
        conn.commit()
        conn.close()

    return {
        "ok": "error" not in result,
        "result": result,
        "image_saved": save_name,
        "mode": "demo" if DEMO_MODE else "live",
    }


# ---- Weather --------------------------------------------------------------

@app.get("/api/weather")
def weather(
    latitude: float = 31.5204,
    longitude: float = 74.3587,
    user: Optional[dict] = Depends(get_user_from_token),
):
    snapshot = get_local_snapshot(latitude, longitude)
    w = snapshot.get("weather", {})
    if "error" not in w and user:
        conn = get_conn()
        conn.execute(
            """INSERT INTO weather_checks
               (user_id, timestamp, latitude, longitude, temperature_C, humidity_percent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user["id"],
                datetime.now().isoformat(timespec="seconds"),
                latitude,
                longitude,
                w.get("temperature_C"),
                w.get("humidity_percent"),
            ),
        )
        conn.commit()
        conn.close()
    return snapshot


# ---- Mandi Rates ----------------------------------------------------------

@app.get("/api/mandi-rates")
def mandi_rates(crop: Optional[str] = None):
    if crop:
        key = crop if crop in MANDI_RATES else crop.title()
        rates = MANDI_RATES.get(key)
        if not rates:
            raise HTTPException(status_code=404, detail=f"No rates for crop: {crop}")
        return {"crop": key, "rates": rates}
    return {"crops": MANDI_RATES}


# ---- History --------------------------------------------------------------

@app.get("/api/history")
def history(user: dict = Depends(require_user)):
    conn = get_conn()
    diagnoses = [
        dict(r)
        for r in conn.execute(
            "SELECT id, timestamp, crop, disease, treatment, confidence FROM diagnoses WHERE user_id = ? ORDER BY id DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    ]
    questions = [
        dict(r)
        for r in conn.execute(
            "SELECT id, timestamp, question, answer FROM questions WHERE user_id = ? ORDER BY id DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    ]
    weather_rows = [
        dict(r)
        for r in conn.execute(
            "SELECT id, timestamp, temperature_C, humidity_percent, latitude, longitude FROM weather_checks WHERE user_id = ? ORDER BY id DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
    ]
    conn.close()
    return {"diagnoses": diagnoses, "questions": questions, "weather": weather_rows}


# ---- Fields ---------------------------------------------------------------

@app.get("/api/fields")
def list_fields(user: dict = Depends(require_user)):
    conn = get_conn()
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, crop, area, location, created_at FROM fields WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    ]
    conn.close()
    return {"fields": rows}


@app.post("/api/fields")
def add_field(body: FieldCreate, user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO fields (user_id, name, crop, area, location, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            user["id"],
            body.name,
            body.crop,
            body.area,
            body.location,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    field_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": field_id, "name": body.name, "crop": body.crop}


# ---- Health ---------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "demo_mode": DEMO_MODE,
        "gemini": not DEMO_MODE,
        "pillow": PIL_AVAILABLE,
        "gtts": GTTS_AVAILABLE,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agrivoice_api:app", host="0.0.0.0", port=8000, reload=True)
