from flask import Flask, request, jsonify
from datetime import datetime
from predictor import get_diagnosis_text, teach_model, get_statistics
import sqlite3
import json
import os

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, vk_id INTEGER UNIQUE, name TEXT, role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT DEFAULT "waiting_data", raw_data TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, ai_conclusion TEXT, doctor_conclusion TEXT, doctor_id INTEGER, status TEXT DEFAULT "pending", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

init_db()

@app.route('/upload', methods=['POST'])
def upload_data():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "No data"}), 400
        
        user_id = data.get('user_id')
        # (Остальной код эндпоинта /upload остается без изменений)
        return jsonify({"status": "success"})
    except Exception as e:
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

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO sessions (user_id, status)
            VALUES (?, 'waiting_data')
            """,
            (user_id,)
        )

        session_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "session_id": session_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_report/<int:session_id>', methods=['GET'])
def get_report(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT ai_conclusion, status FROM reports WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"status": row["status"], "ai_conclusion": row["ai_conclusion"]})
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
            return jsonify({"error": "No frames"}), 400

        conn = get_db()
        cursor = conn.cursor()

        # сохраняем телеметрию сессии
        cursor.execute(
            """
            UPDATE sessions
            SET raw_data = ?, status = 'data_received'
            WHERE id = ?
            """,
            (
                json.dumps(frames, ensure_ascii=False),
                session_id
            )
        )

        # берём последний кадр для классификации ИИ
        last = frames[-1]

        ai_conclusion = get_diagnosis_text(
            last["pulse"],
            last["rhythm"],
            last["emg"],
            last["alpha"],
            last["beta"]
        )

        cursor.execute(
            "INSERT INTO reports (session_id, ai_conclusion, status) VALUES (?, ?, 'pending')",
            (session_id, ai_conclusion)
        )

        conn.commit()
        conn.close()

        return jsonify({"status": "success", "ai_conclusion": ai_conclusion})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== НОВЫЕ И ИЗМЕНЕННЫЕ ЭНДПОИНТЫ ДЛЯ КНОПОК ВРАЧА ====================

@app.route('/approve', methods=['POST'])
def approve_report():
    """
    Врач нажал кнопку 'Подтвердить'. 
    ИИ берет показатели сессии и обучается на них, подтверждая правильность своего выбора.
    """
    try:
        data = request.get_json() or request.form
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"error": "Missing session_id"}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 1. Обновляем статус отчета в базе данных на 'approved'
        cursor.execute(
            "UPDATE reports SET status = 'approved' WHERE session_id = ?",
            (session_id,)
        )

        # 2. Вытаскиваем сырые данные сессии для дообучения ИИ
        cursor.execute("SELECT raw_data FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        
        trained = False
        if session_row and session_row["raw_data"]:
            frames = json.loads(session_row["raw_data"])
            if frames:
                last_frame = frames[-1]
                
                # Достаем текст вывода ИИ, чтобы понять, какое состояние подтвердил врач
                cursor.execute("SELECT ai_conclusion FROM reports WHERE session_id = ?", (session_id,))
                report_row = cursor.fetchone()
                
                if report_row and report_row["ai_conclusion"]:
                    ai_text = report_row["ai_conclusion"]
                    
                    # Ищем кодовое слово состояния внутри строки диагноза (например, "Диагноз: Normal (уверенность: 85%)")
                    detected_state = "Normal"
                    states_list = ["Normal", "Tension", "Fatigue", "Recovery", "Stress", "Overload", "Arrhythmia"]
                    for s in states_list:
                        if s in ai_text:
                            detected_state = s
                            break
                    
                    # Отправляем в предиктор на дообучение и автосохранение .pkl
                    teach_model(
                        pulse=last_frame["pulse"],
                        rhythm=last_frame["rhythm"],
                        emg=last_frame["emg"],
                        alpha=last_frame["alpha"],
                        beta=last_frame["beta"],
                        correct_state=detected_state
                    )
                    trained = True

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Диагноз подтвержден, ИИ обучен", "trained": trained})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/teach', methods=['POST'])
def teach_model_endpoint():
    """
    Врач исправил диагноз на другой вариант.
    ИИ принудительно переобучается на этой метрике с новой верной меткой класса.
    """
    try:
        data = request.get_json() or request.form
        session_id = data.get("session_id")
        correct_state = data.get("correct_state")  # Вариант диагноза, выбранный врачом в ВК

        if not session_id or not correct_state:
            return jsonify({"error": "Missing session_id or correct_state"}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 1. Записываем вердикт врача в отчет и закрываем его статус как 'approved'
        cursor.execute(
            "UPDATE reports SET doctor_conclusion = ?, status = 'approved' WHERE session_id = ?",
            (f"Исправлено врачом: {correct_state}", session_id)
        )

        # 2. Извлекаем телеметрию датчиков для исправления ошибки ИИ
        cursor.execute("SELECT raw_data FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()

        trained = False
        if session_row and session_row["raw_data"]:
            frames = json.loads(session_row["raw_data"])
            if frames:
                last_frame = frames[-1]
                
                # Дообучаем модель правильному ответу врача
                teach_model(
                    pulse=last_frame["pulse"],
                    rhythm=last_frame["rhythm"],
                    emg=last_frame["emg"],
                    alpha=last_frame["alpha"],
                    beta=last_frame["beta"],
                    correct_state=correct_state
                )
                trained = True

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "trained": trained})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Очищаем или подготавливаем базу данных при локальном тестировании, если требуется
    app.run(host='0.0.0.0', port=5000, debug=True)