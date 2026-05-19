# Digital Doctor

Система диагностики на базе ИИ с интеграцией биосенсоров ESP32, Flask-бэкендом и VK-ботом для взаимодействия пациентов и врачей.

## Архитектура

```
ESP32 (сенсоры) ──UDP──> udp_server.py ──HTTP──> server.py (Flask) ──> SQLite DB
                                │                                  │
                                │                              predictor.py
                                │                                  │
                                v                              doctor_ai.py
                          bot.py (VK)                   (RandomForest AI)
```

## Компоненты

| Компонент | Описание |
|-----------|----------|
| `doctor_ai.py` | Ядро ИИ — `RandomForestClassifier` с 7 состояниями: Normal, Tension, Fatigue, Recovery, Stress, Overload, Arrhythmia |
| `predictor.py` | Обёртка-синглтон вокруг модели ИИ: `analyze()`, `get_diagnosis_text()`, `teach_model()` |
| `server.py` | REST API на Flask — управление сессиями, пакетная загрузка данных, диагностика ИИ, подтверждение/обучение врачами |
| `bot.py` | VK-бот — запуск обследования пациентом, инлайн-клавиатуры для проверки врачами |
| `udp_server.py` | UDP-приёмник данных с ESP32 — декодирует бинарные пакеты, вычисляет метрики, отправляет батчи на Flask |
| `train_model.py` | Скрипт первичного обучения модели на синтетических данных |

## Установка

```bash
pip install -r requirements.txt

cp .env.example .env
# Отредактируйте .env: укажите VK_TOKEN, GROUP_ID, SERVER_URL

python db_setup.py
python train_model.py
```

## Запуск

Каждый компонент запускается в отдельном терминале:

```bash
python server.py        # Flask API на порту 5000
python bot.py           # VK-бот (LongPoll)
python udp_server.py    # UDP-приёмник для ESP32
```

## API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/start_session` | Создать новую сессию обследования |
| POST | `/upload` | Загрузить одиночную точку данных (сохраняется в `received_data/`) |
| POST | `/upload_batch` | Загрузить батч кадров с сенсоров, запускает диагностику ИИ |
| GET | `/session_status/<id>` | Проверить статус сессии |
| GET | `/get_report/<id>` | Получить заключение ИИ |
| POST | `/approve` | Врач подтверждает диагноз ИИ (модель дообучается) |
| POST | `/teach` | Врач исправляет диагноз ИИ (модель дообучается) |
| GET | `/stats` | Статистика модели ИИ |

## Тестирование

```bash
python -c "
import requests
# Создать сессию
r = requests.post('http://localhost:5000/start_session', json={'user_id': 1})
print(r.json())
# Загрузить батч данных с сенсоров
session_id = r.json()['session_id']
r = requests.post('http://localhost:5000/upload_batch', json={
    'user_id': 1,
    'session_id': session_id,
    'frames': [{'pulse': 96, 'rhythm': 'sinus', 'emg': 55, 'alpha': 30, 'beta': 70}]
})
print(r.json())
"
```

## Соглашения

- Весь код использует `logging` вместо `print`
- Секреты хранятся в `.env` (не коммитятся)
- База данных — SQLite (`database.db`)
- Модель ИИ сериализуется в `ai_model.pkl`
- Данные с сенсоров принимаются по UDP на порту 5005, обрабатываются батчами по 100 кадров
