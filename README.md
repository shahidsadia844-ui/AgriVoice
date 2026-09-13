# AgriPak / AgriVoice Backend

FastAPI backend designed to match the **AgriPak Frontend** (HTML pages).

## Features mapped from Frontend

| Frontend page              | Backend endpoint                          |
|---------------------------|-------------------------------------------|
| 02_signin / 03_signup     | `POST /api/auth/signin`, `/api/auth/signup` |
| 03.1_forgot_password      | `POST /api/auth/forgot-password`          |
| 04_select_crop            | `POST /api/crop/select`, `GET /api/crops` |
| 05_dashboard              | profile + crop info + fields              |
| 06_agrivoice              | `POST /api/chat`                          |
| 07_leaf_scan              | `POST /api/leaf-scan` (multipart image)   |
| 08_mandi_rates            | `GET /api/mandi-rates?crop=Wheat`         |
| 09_field_details          | `GET/POST /api/fields`                    |
| 10_profile                | `GET /api/profile`                        |
| 11_crop_info              | `GET /api/crop/{name}`                    |
| 12_weather_details        | `GET /api/weather?latitude=&longitude=`   |

## Quick start

```bash
cd AgriPak_Backend
pip install -r requirements.txt

# Optional: real AI answers
export GEMINI_API_KEY=your_key_here

uvicorn agrivoice_api:app --host 0.0.0.0 --port 8000 --reload
```

Open interactive docs: http://localhost:8000/docs

## Auth flow (for frontend JS)

1. Signup or Signin → response includes `token`
2. Store token (e.g. `localStorage.setItem('agri_token', token)`)
3. Send on protected routes:
   ```
   Authorization: Bearer <token>
   ```

## Example calls

```bash
# Signup
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"name":"Ali","contact":"03001234567","password":"secret1"}'

# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"گندم کا ریٹ کیا ہے؟"}'

# Leaf scan
curl -X POST http://localhost:8000/api/leaf-scan \
  -F "file=@leaf.jpg"

# Weather (Lahore default)
curl "http://localhost:8000/api/weather"

# Mandi rates
curl "http://localhost:8000/api/mandi-rates?crop=Wheat"
```

## Demo mode

If `GEMINI_API_KEY` is not set, the API still works with realistic mock diagnosis and chat replies (including Urdu responses that match the frontend prototype).

## Files

- `agrivoice_api.py` — main FastAPI app
- `requirements.txt` — dependencies
- `agrivoice.db` — created automatically on first run
- `uploads/` — saved leaf images
