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
        session_id = data.get('session_id') # Читаем ID сессии из запроса
        
        # Параметры для ИИ
        pulse, rhythm = data.get('pulse'), data.get('rhythm', 'синусовый')
        emg, alpha, beta = data.get('emg'), data.get('alpha'), data.get('beta')

        conn = get_db()
        cursor = conn.cursor()

        # 1. Если нам явно прислали session_id, используем его
        if session_id:
            cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            session = cursor.fetchone()
        else:
            # 2. Иначе ищем последнюю открытую сессию пользователя
            cursor.execute("SELECT id FROM sessions WHERE user_id = ? AND status = 'waiting_data' ORDER BY created_at DESC LIMIT 1", (user_id,))
            session = cursor.fetchone()

        print("RHYTHM:", rhythm)
        print("RAW JSON:", json.dumps({
            "pulse": pulse,
            "rhythm": rhythm,
            "emg": emg,
            "alpha": alpha,
            "beta": beta
        }, ensure_ascii=False))

        raw_json = json.dumps({
            "pulse": pulse,
            "rhythm": rhythm,
            "emg": emg,
            "alpha": alpha,
            "beta": beta
        }, ensure_ascii=False)

        if session:
            target_id = session['id']
            cursor.execute("UPDATE sessions SET raw_data = ?, status = 'data_received' WHERE id = ?", (raw_json, target_id))
        else:
            # 3. Если вообще ничего не нашли, создаем новую
            cursor.execute("INSERT INTO sessions (user_id, status, raw_data) VALUES (?, 'data_received', ?)", (user_id, raw_json))
            target_id = cursor.lastrowid

        # Вызов ИИ
        ai_conclusion = get_diagnosis_text(pulse, rhythm, emg, alpha, beta)
        cursor.execute("INSERT INTO reports (session_id, ai_conclusion, status) VALUES (?, ?, 'pending')", (target_id, ai_conclusion))
        
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "session_id": target_id, "ai": ai_conclusion}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/start_session', methods=['POST'])
def start_session():
    data = request.get_json()
    user_id = data.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (user_id, status) VALUES (?, 'waiting_data')", (user_id,))
    sid = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "session_id": sid})

@app.route('/report/<int:session_id>', methods=['GET'])
def get_report(session_id):

    conn = get_db()

    row = conn.execute("""
        SELECT r.*, s.raw_data
        FROM reports r
        JOIN sessions s ON r.session_id = s.id
        WHERE r.session_id = ?
        ORDER BY r.created_at DESC
        LIMIT 1
    """, (session_id,)).fetchone()

    conn.close()

    if not row:
        return jsonify({
            "ai_conclusion": "None"
        }), 200

    return jsonify({
        "session_id": session_id,
        "ai_conclusion": row['ai_conclusion'],
        "doctor_conclusion": row['doctor_conclusion'],
        "status": row['status'],
        "raw_data": json.loads(row['raw_data']) if row['raw_data'] else {}
    })

@app.route('/pending_reports', methods=['GET'])
def pending():
    conn = get_db()
    rows = conn.execute("SELECT r.*, s.user_id FROM reports r JOIN sessions s ON r.session_id = s.id WHERE r.status = 'pending'").fetchall()
    conn.close()
    return jsonify({"reports": [dict(r) for r in rows]})

@app.route('/teach', methods=['POST'])
def teach_endpoint():
    try:
        data = request.get_json()

        session_id = data.get('session_id')
        correct_state = data.get('correct_state')

        conn = get_db()

        row = conn.execute(
            "SELECT raw_data FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Session not found"}), 404

        raw_data = json.loads(row['raw_data'])

        pulse = raw_data.get('pulse')
        rhythm = raw_data.get('rhythm')
        emg = raw_data.get('emg')
        alpha = raw_data.get('alpha')
        beta = raw_data.get('beta')

        success = teach_model(
            pulse,
            rhythm,
            emg,
            alpha,
            beta,
            correct_state
        )

        if success:
            conn.execute(
                """
                UPDATE reports
                SET status='reviewed',
                    doctor_conclusion=?
                WHERE session_id=?
                """,
                (correct_state, session_id)
            )

            conn.commit()

        conn.close()

        return jsonify({
            "status": "ok",
            "trained": success
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive"}), 200

@app.route('/statistics', methods=['GET'])
def statistics():
    return jsonify(get_statistics())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
