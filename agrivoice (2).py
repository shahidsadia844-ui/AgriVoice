#!/usr/bin/env python3
"""
AgriVoice - AI-powered farming assistant
Features:
1. Crop disease diagnosis from leaf images (Gemini Vision)
2. Voice/Text assistant for farming questions (Gemini + gTTS)
3. Local weather & mock market price snapshot (Open-Meteo API)
Works in "demo mode" (mock responses) if GEMINI_API_KEY is not set,
so the whole flow can be tested without an API key.
"""

import os
import sys
import json
import requests
# ---------------------------------------------------------------------
# Setup: check for API key and required libraries
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
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def _banner():
    mode = "DEMO MODE (no API key found)" if DEMO_MODE else "LIVE MODE (Gemini connected)"
    print("=" * 55)
    print(f"  AgriVoice  —  {mode}")
    print("=" * 55)


# ---------------------------------------------------------------------
# Feature 1: Crop disease diagnosis from an image
# ---------------------------------------------------------------------

def diagnose_crop_image(image_path: str) -> dict:
    """
    Sends a leaf image to Gemini Vision and asks it to identify the crop,
    detect disease, and suggest treatment. Returns a dict (parsed JSON).
    Falls back to a mock response in demo mode or on error.
    """
    if not os.path.exists(image_path):
        return {"error": f"Image not found at path: {image_path}"}

    if DEMO_MODE:
        return {
            "crop": "Tomato (demo guess)",
            "disease": "Early Blight (mock diagnosis)",
            "confidence": "N/A - demo mode",
            "treatment": (
                "This is a MOCK response since no GEMINI_API_KEY is set. "
                "Remove affected leaves, apply a copper-based fungicide, "
                "and avoid overhead watering to reduce leaf wetness."
            ),
        }

    try:
        if not PIL_AVAILABLE:
            return {"error": "Pillow (PIL) not installed. Run: pip install pillow"}

        img = Image.open(image_path)

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
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()

        return json.loads(text)

    except json.JSONDecodeError:
        return {"error": "Could not parse model response as JSON.", "raw_response": text}
    except Exception as e:
        return {"error": f"Diagnosis failed: {e}"}


# ---------------------------------------------------------------------
# Feature 2: Voice/Text farming assistant
# ---------------------------------------------------------------------

def ask_assistant(question: str, speak: bool = True) -> str:
    """
    Sends a farming-related question to Gemini and returns the text answer.
    Optionally converts the answer to speech (agrivoice_response.mp3) using gTTS.
    Falls back to a mock answer in demo mode.
    """
    if DEMO_MODE:
        answer = (
            f"[DEMO MODE] You asked: '{question}'. "
            "In live mode, Gemini would give a detailed, practical farming answer here. "
            "Set your GEMINI_API_KEY to get real responses."
        )
    else:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                "You are AgriVoice, a friendly farming assistant for smallholder "
                "farmers. Answer this question simply, practically, and briefly:\n\n"
                f"{question}"
            )
            response = model.generate_content(prompt)
            answer = response.text.strip()
        except Exception as e:
            answer = f"Error getting response from Gemini: {e}"

    print("\n--- AgriVoice says ---")
    print(answer)
    print("----------------------\n")

    if speak and GTTS_AVAILABLE:
        try:
            tts = gTTS(text=answer, lang="en")
            out_path = "agrivoice_response.mp3"
            tts.save(out_path)
            print(f"🔊 Audio saved to: {out_path}")
        except Exception as e:
            print(f"(Could not generate audio: {e})")
    elif speak and not GTTS_AVAILABLE:
        print("(gTTS not installed — skipping audio. Run: pip install gTTS)")

    return answer


# ---------------------------------------------------------------------
# Feature 3: Local weather + mock market price snapshot
# ---------------------------------------------------------------------

def get_local_snapshot(latitude: float = 31.5204, longitude: float = 74.3587) -> dict:
    """
    Fetches live weather from Open-Meteo (free, no API key needed) and
    combines it with mock market prices for a quick farmer-facing snapshot.
    Default coordinates are Lahore, Pakistan.
    """
    snapshot = {"location": {"latitude": latitude, "longitude": longitude}}

    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        snapshot["weather"] = {
            "temperature_C": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        }
    except Exception as e:
        snapshot["weather"] = {"error": f"Could not fetch weather: {e}"}

    # Mock market prices (demo only — replace with a real market data API later)
    snapshot["market_prices_mock"] = {
        "wheat_per_40kg": "PKR 3,200 (mock)",
        "tomato_per_kg": "PKR 90 (mock)",
        "potato_per_kg": "PKR 65 (mock)",
    }

    print("\n--- Local Snapshot ---")
    print(json.dumps(snapshot, indent=2))
    print("----------------------\n")

    return snapshot


# ---------------------------------------------------------------------
# CLI Menu
# ---------------------------------------------------------------------

def main():
    _banner()

    while True:
        print("\nAgriVoice Menu:")
        print("1) Leaf diagnose (crop disease detection)")
        print("2) Sawal poochna (ask the assistant)")
        print("3) Weather dekhna (weather + prices)")
        print("4) Exit")

        choice = input("\nChoose an option (1-4): ").strip()

        if choice == "1":
            path = input("Leaf image ka path dein (e.g. leaf.jpg): ").strip()
            result = diagnose_crop_image(path)
            print("\n--- Diagnosis Result ---")
            print(json.dumps(result, indent=2))
            print("------------------------\n")

        elif choice == "2":
            q = input("Apna sawal likhein: ").strip()
            if q:
                ask_assistant(q)

        elif choice == "3":
            lat_in = input("Latitude (Enter = default Lahore 31.5204): ").strip()
            lon_in = input("Longitude (Enter = default Lahore 74.3587): ").strip()
            lat = float(lat_in) if lat_in else 31.5204
            lon = float(lon_in) if lon_in else 74.3587
            get_local_snapshot(lat, lon)

        elif choice == "4":
            print("AgriVoice band ho raha hai. Allah Hafiz!")
            sys.exit(0)

        else:
            print("Ghalat option — 1, 2, 3 ya 4 mein se chunein.")


if __name__ == "__main__":
    main()