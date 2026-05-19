# Digital Doctor - Project Overview

## Architecture
- **server.py** — Flask REST API (session management, AI diagnosis, doctor feedback)
- **bot.py** — VK bot (patient/doctor interaction, inline keyboards)
- **udp_server.py** — UDP receiver for ESP32 sensor data
- **doctor_ai.py** — Core AI model (RandomForestClassifier, 7 states)
- **predictor.py** — Singleton wrapper around the AI
- **train_model.py** — Script to train initial model

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in VK_TOKEN, GROUP_ID, SERVER_URL
python db_setup.py      # Create database tables
python train_model.py   # Train initial AI model
```

## Run
```bash
python server.py        # Flask API (port 5000)
python bot.py           # VK bot (longpoll)
python udp_server.py    # UDP receiver for ESP32
```

## Testing
```bash
python -c "
import requests
r = requests.post('http://localhost:5000/start_session', json={'user_id': 1})
print(r.json())
"
```

## Conventions
- All new code should use `logging` instead of `print`
- Environment variables in `.env` for secrets
- Database: SQLite (`database.db`)
- AI model serialized as `ai_model.pkl`
