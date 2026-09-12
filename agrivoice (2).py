
        import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Ye frontend aur backend ka connection allow karega

# Gemini API setup
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

@app.route('/')
def home():
    return "AgriVoice Backend is Running Successfully!"

# 1. Ask Assistant Endpoint
@app.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.json
    question = data.get("question", "")
    
    if not question:
        return jsonify({"error": "Sawal likhna lazmi hai!"}), 400

    if DEMO_MODE:
        answer = f"[DEMO MODE] Aap ne poocha: '{question}'. GEMINI_API_KEY set nahi hai."
    else:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"Aap AgriVoice hain, farmers ke liye assistant. Is sawal ka chota aur behtareen jawab dein:\n\n{question}"
            response = model.generate_content(prompt)
            answer = response.text.strip()
        except Exception as e:
            answer = f"Error: {e}"

    return jsonify({"answer": answer})

# 2. Weather & Market Snapshot Endpoint
@app.route('/api/weather', methods=['GET'])
def api_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=31.5204&longitude=74.3587&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
        resp = requests.get(url, timeout=10)
        data = resp.json().get("current", {})
        
        weather_data = {
            "temperature": data.get("temperature_2m"),
            "humidity": data.get("relative_humidity_2m"),
            "wind_speed": data.get("wind_speed_10m"),
            "market_prices": {
                "wheat_per_40kg": "PKR 3,200",
                "tomato_per_kg": "PKR 90"
            }
        }
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
