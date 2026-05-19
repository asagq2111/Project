import os
import json
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from predictor import get_diagnosis_text, teach_model, get_statistics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECEIVED_DIR = os.path.join(BASE_DIR, "received_data")


def get_db():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'database.db'))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, vk_id INTEGER UNIQUE, name TEXT,
        role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        status TEXT DEFAULT "waiting_data", raw_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
        ai_conclusion TEXT, doctor_conclusion TEXT, doctor_id INTEGER,
        status TEXT DEFAULT "pending", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")


init_db()


@app.route('/upload', methods=['POST'])
def upload_data():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400

        os.makedirs(RECEIVED_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S.%f")
        filename = f"user_{user_id}_{timestamp}.json"
        filepath = os.path.join(RECEIVED_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Data saved from user %s: %s", user_id, filename)
        return jsonify({"status": "success", "file": filename})
    except Exception as e:
        logger.error("Upload error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route('/session_status/<int:session_id>', methods=['GET'])
def session_status(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"status": row["status"]})
    return jsonify({"status": "not_found"}), 404


@app.route('/start_session', methods=['POST'])
def start_session():
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"error": "Missing user_id"}), 400

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "user_id must be an integer"}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (user_id, status) VALUES (?, 'waiting_data')",
            (user_id,)
        )
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info("Session %d started for user %d", session_id, user_id)
        return jsonify({"status": "success", "session_id": session_id})

    except Exception as e:
        logger.error("start_session error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route('/get_report/<int:session_id>', methods=['GET'])
def get_report(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ai_conclusion, status FROM reports WHERE session_id = ?",
        (session_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({
            "status": row["status"],
            "ai_conclusion": row["ai_conclusion"],
        })
    return jsonify({"status": "error", "message": "Report not found"}), 404


@app.route('/stats', methods=['GET'])
def stats():
    return jsonify(get_statistics())


@app.route('/upload_batch', methods=['POST'])
def upload_batch():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        session_id = data.get("session_id")
        frames = data.get("frames", [])

        if not frames:
            return jsonify({"error": "No frames provided"}), 400

        last = frames[-1]
        required_fields = ["pulse", "rhythm", "emg", "alpha", "beta"]
        missing = [f for f in required_fields if f not in last]
        if missing:
            return jsonify({"error": f"Missing fields in frame: {missing}"}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE sessions SET raw_data = ?, status = 'data_received' WHERE id = ?",
            (json.dumps(frames, ensure_ascii=False), session_id)
        )

        ai_conclusion = get_diagnosis_text(
            last["pulse"], last["rhythm"], last["emg"],
            last["alpha"], last["beta"]
        )

        cursor.execute(
            "INSERT INTO reports (session_id, ai_conclusion, status) VALUES (?, ?, 'pending')",
            (session_id, ai_conclusion)
        )

        conn.commit()
        conn.close()

        logger.info("Batch processed for session %d: %s", session_id, ai_conclusion[:50])
        return jsonify({"status": "success", "ai_conclusion": ai_conclusion})

    except Exception as e:
        logger.error("upload_batch error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route('/approve', methods=['POST'])
def approve_report():
    try:
        data = request.get_json() or request.form
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"error": "Missing session_id"}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        patient_id = session_row["user_id"] if session_row else None

        cursor.execute("SELECT raw_data FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()

        trained = False
        final_diagnosis = None
        if session_row and session_row["raw_data"]:
            frames = json.loads(session_row["raw_data"])
            if frames:
                last_frame = frames[-1]

                cursor.execute(
                    "SELECT ai_conclusion FROM reports WHERE session_id = ?",
                    (session_id,)
                )
                report_row = cursor.fetchone()

                if report_row and report_row["ai_conclusion"]:
                    ai_text = report_row["ai_conclusion"]
                    detected_state = "Норма"
                    for s in ["Норма", "Напряжение", "Усталость", "Восстановление", "Стресс", "Перегрузка", "Аритмия"]:
                        if s in ai_text:
                            detected_state = s
                            break

                    final_diagnosis = detected_state
                    teach_model(
                        pulse=last_frame["pulse"],
                        rhythm=last_frame["rhythm"],
                        emg=last_frame["emg"],
                        alpha=last_frame["alpha"],
                        beta=last_frame["beta"],
                        correct_state=detected_state,
                    )
                    trained = True
                    logger.info("Model retrained: session %d -> %s", session_id, detected_state)

        cursor.execute(
            "UPDATE reports SET doctor_conclusion = ?, status = 'approved' WHERE session_id = ?",
            (f"Подтверждено врачом: {final_diagnosis}", session_id)
        )

        conn.commit()
        conn.close()
        return jsonify({
            "status": "success",
            "message": "Diagnosis confirmed, AI trained",
            "trained": trained,
            "patient_id": patient_id,
            "final_diagnosis": final_diagnosis,
        })

    except Exception as e:
        logger.error("approve error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route('/teach', methods=['POST'])
def teach_model_endpoint():
    try:
        data = request.get_json() or request.form
        session_id = data.get("session_id")
        correct_state = data.get("correct_state")

        if not session_id or not correct_state:
            return jsonify({"error": "Missing session_id or correct_state"}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        patient_id = session_row["user_id"] if session_row else None

        cursor.execute(
            "UPDATE reports SET doctor_conclusion = ?, status = 'approved' WHERE session_id = ?",
            (f"Исправлено врачом: {correct_state}", session_id)
        )

        cursor.execute("SELECT raw_data FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()

        trained = False
        if session_row and session_row["raw_data"]:
            frames = json.loads(session_row["raw_data"])
            if frames:
                last_frame = frames[-1]

                teach_model(
                    pulse=last_frame["pulse"],
                    rhythm=last_frame["rhythm"],
                    emg=last_frame["emg"],
                    alpha=last_frame["alpha"],
                    beta=last_frame["beta"],
                    correct_state=correct_state,
                )
                trained = True
                logger.info("Model corrected: session %d -> %s", session_id, correct_state)

        conn.commit()
        conn.close()
        return jsonify({
            "status": "success",
            "trained": trained,
            "patient_id": patient_id,
            "final_diagnosis": correct_state,
        })

    except Exception as e:
        logger.error("teach error: %s", e)
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5000, debug=debug)
