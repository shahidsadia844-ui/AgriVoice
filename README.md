# AgriVoice
# 🌾 AgriPak (AgriVoice)

AgriPak is an accessible, multimodal agricultural decision-support web platform engineered for Pakistani smallholder farmers. By combining conversational voice advisory, computer vision leaf pathology diagnostics, and real-time field telemetry, AgriPak eliminates literacy and technological barriers to empower farmers with actionable agronomic insights.

---

## 🚀 Key Features

* **🌾 Crop Selection & Dynamic Dashboard:** Auto-populates telemetry metrics, mandi prices, and sensor data tailored for primary seasonal crops (Wheat, Cotton, Sugarcane, Maize).
* **📸 AI Leaf Scan & Pathology Diagnostics:** Native camera capture or gallery upload for real-time visual disease matching (e.g., Wheat Rust detection) with instant chemical and organic remediation advisories.
* **🎙️ AgriVoice Multilingual Assistant:** Urdu-localized conversational agent with single-tap voice input for hands-free weather, irrigation, and market price inquiries.
* **📊 Live Mandi Commodity Tracker:** Real-time rate cards and price delta indicators across major trading hubs including Multan, Lahore, Faisalabad, and Sahiwal.

---

## 🛠️ Technical Stack & Architecture

| Layer | Selection | Rationale |
| :--- | :--- | :--- |
| **Frontend** | HTML5, Vanilla JavaScript, CSS3 | Zero-dependency, ultra-fast initial load times on budget mobile browsers |
| **Backend Engine** | Python 3.14+ (FastAPI) | High-throughput asynchronous routing and ML pipeline integration |
| **Persistence** | SQLite | Zero-configuration, lightweight edge deployment |
| **AI Inference** | Google Gemini API (Vision & Voice) | Single-call joint vision and contextual reasoning |
| **Future Client** | Flutter (Dart) | Cross-platform native deployment for offline caching |

### 🎨 Design System
* **Theme:** Glassmorphic Dark Green (`#0B1912`, `#2D6A4F`, `#52B788`) designed for high-contrast visibility under direct sunlight.

---

## 🔧 Installation & Setup

1. **Clone the Repository**
   ```bash
   git clone [https://github.com/your-username/agripak.git](https://github.com/your-username/agripak.git)
   cd agripak
   2.Set Up Virtual Environment & Dependencies
   python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
3.Configure Environment Variables
Create a .env file in the root directory:
GEMINI_API_KEY=your_google_gemini_api_key
4.Run the Application
uvicorn main:app --reload
   
