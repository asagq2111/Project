from flask import Flask, request, jsonify
from datetime import datetime
from predictor import get_diagnosis_text, teach_model
import sqlite3
import os

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
# ============================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
# ============================================

def get_db():
    """Подключение к базе данных"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # чтобы можно было обращаться к полям по имени
    conn.execute("PRAGMA encoding = 'UTF-8'")
    return conn

def init_db():
    """Создание таблиц, если их нет (на всякий случай)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA encoding = 'UTF-8'")
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_id INTEGER UNIQUE,
        name TEXT,
        role TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        status TEXT DEFAULT 'waiting_data',
        raw_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ai_conclusion TEXT,
        doctor_conclusion TEXT,
        doctor_id INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions (id),
        FOREIGN KEY (doctor_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Вызываем при старте сервера
init_db()

# ============================================
# ЭНДПОИНТЫ (API)
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка, что сервер жив"""
    return jsonify({"status": "alive", "message": "Server is running"}), 200

@app.route('/teach', methods=['POST'])
def teach_ai():
    """
    Врач исправляет диагноз ИИ.
    Ожидает JSON:
    {
        "session_id": 1,
        "correct_state": "Стресс"
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        correct_state = data.get('correct_state')
        
        if not session_id or not correct_state:
            return jsonify({"error": "session_id and correct_state required"}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Получаем параметры сессии
        cursor.execute("""
            SELECT raw_data FROM sessions WHERE id = ?
        """, (session_id,))
        
        session = cursor.fetchone()
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        # Парсим raw_data (она хранится как строка)
        import json
        raw_data = json.loads(session['raw_data'])
        
        # Дообучаем модель
        from predictor import teach_model
        success = teach_model(
            pulse=raw_data.get('pulse', 0),
            rhythm=raw_data.get('rhythm', 'синусовый'),
            emg=raw_data.get('emg', 0),
            alpha=raw_data.get('alpha', 0),
            beta=raw_data.get('beta', 0),
            correct_state=correct_state
        )
        
        if success:
            # Обновляем отчёт с исправленным диагнозом
            cursor.execute("""
                UPDATE reports 
                SET doctor_conclusion = ?, status = 'approved'
                WHERE session_id = ?
            """, (f"Исправлено врачом: {correct_state}", session_id))
            conn.commit()
            
            return jsonify({
                "status": "ok",
                "message": f"Модель дообучена. Новый диагноз: {correct_state}"
            }), 200
        else:
            return jsonify({"error": "Неизвестное состояние"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/report/<int:session_id>', methods=['GET'])
def get_report(session_id):
    """
    Возвращает полный отчёт по сессии.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.raw_data, s.status, s.created_at,
                   r.ai_conclusion, r.doctor_conclusion, r.status as report_status
            FROM sessions s
            LEFT JOIN reports r ON s.id = r.session_id
            WHERE s.id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"error": "Report not found"}), 404
        
        import json
        raw_data = json.loads(row['raw_data']) if row['raw_data'] else {}
        
        return jsonify({
            "session_id": row['id'],
            "parameters": raw_data,
            "ai_conclusion": row['ai_conclusion'],
            "doctor_conclusion": row['doctor_conclusion'],
            "status": row['report_status'] or row['status'],
            "created_at": row['created_at']
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/pending_reports', methods=['GET'])
def get_pending_reports():
    """
    Возвращает список отчётов, ожидающих проверки врачом.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.user_id, s.created_at, r.ai_conclusion
            FROM sessions s
            JOIN reports r ON s.id = r.session_id
            WHERE r.status = 'pending'
            ORDER BY s.created_at DESC
        """)
        
        reports = []
        for row in cursor.fetchall():
            reports.append({
                "session_id": row['id'],
                "user_id": row['user_id'],
                "created_at": row['created_at'],
                "ai_conclusion": row['ai_conclusion'][:100] + "..."  # кратко
            })
        
        conn.close()
        
        return jsonify({"reports": reports, "count": len(reports)}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


from flask import Flask, request, jsonify
from datetime import datetime
from predictor import get_diagnosis_text, teach_model
import sqlite3
import os

app = Flask(__name__)

# ============================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
# ============================================

def get_db():
    """Подключение к базе данных"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # чтобы можно было обращаться к полям по имени
    return conn

def init_db():
    """Создание таблиц, если их нет (на всякий случай)"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_id INTEGER UNIQUE,
        name TEXT,
        role TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        status TEXT DEFAULT 'waiting_data',
        raw_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ai_conclusion TEXT,
        doctor_conclusion TEXT,
        doctor_id INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions (id),
        FOREIGN KEY (doctor_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Вызываем при старте сервера
init_db()

# ============================================
# ЭНДПОИНТЫ (API)
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка, что сервер жив"""
    return jsonify({"status": "alive", "message": "Server is running"}), 200

@app.route('/teach', methods=['POST'])
def teach_ai():
    """
    Врач исправляет диагноз ИИ.
    Ожидает JSON:
    {
        "session_id": 1,
        "correct_state": "Стресс"
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        correct_state = data.get('correct_state')
        
        if not session_id or not correct_state:
            return jsonify({"error": "session_id and correct_state required"}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Получаем параметры сессии
        cursor.execute("""
            SELECT raw_data FROM sessions WHERE id = ?
        """, (session_id,))
        
        session = cursor.fetchone()
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        # Парсим raw_data (она хранится как строка)
        import json
        raw_data = json.loads(session['raw_data'])
        
        # Дообучаем модель
        from predictor import teach_model
        success = teach_model(
            pulse=raw_data.get('pulse', 0),
            rhythm=raw_data.get('rhythm', 'синусовый'),
            emg=raw_data.get('emg', 0),
            alpha=raw_data.get('alpha', 0),
            beta=raw_data.get('beta', 0),
            correct_state=correct_state
        )
        
        if success:
            # Обновляем отчёт с исправленным диагнозом
            cursor.execute("""
                UPDATE reports 
                SET doctor_conclusion = ?, status = 'approved'
                WHERE session_id = ?
            """, (f"Исправлено врачом: {correct_state}", session_id))
            conn.commit()
            
            return jsonify({
                "status": "ok",
                "message": f"Модель дообучена. Новый диагноз: {correct_state}"
            }), 200
        else:
            return jsonify({"error": "Неизвестное состояние"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/report/<int:session_id>', methods=['GET'])
def get_report(session_id):
    """
    Возвращает полный отчёт по сессии.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.raw_data, s.status, s.created_at,
                   r.ai_conclusion, r.doctor_conclusion, r.status as report_status
            FROM sessions s
            LEFT JOIN reports r ON s.id = r.session_id
            WHERE s.id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"error": "Report not found"}), 404
        
        import json
        raw_data = json.loads(row['raw_data']) if row['raw_data'] else {}
        
        return jsonify({
            "session_id": row['id'],
            "parameters": raw_data,
            "ai_conclusion": row['ai_conclusion'],
            "doctor_conclusion": row['doctor_conclusion'],
            "status": row['report_status'] or row['status'],
            "created_at": row['created_at']
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/pending_reports', methods=['GET'])
def get_pending_reports():
    """
    Возвращает список отчётов, ожидающих проверки врачом.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.user_id, s.created_at, r.ai_conclusion
            FROM sessions s
            JOIN reports r ON s.id = r.session_id
            WHERE r.status = 'pending'
            ORDER BY s.created_at DESC
        """)
        
        reports = []
        for row in cursor.fetchall():
            reports.append({
                "session_id": row['id'],
                "user_id": row['user_id'],
                "created_at": row['created_at'],
                "ai_conclusion": row['ai_conclusion'][:100] + "..."  # кратко
            })
        
        conn.close()
        
        return jsonify({"reports": reports, "count": len(reports)}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/upload', methods=['POST'])
def upload_data():
    """
    Приём данных от Arduino.
    Ожидает JSON: {"user_id": 123, "pulse": 96, "rhythm": "синусовый", "emg": 100, "alpha": 46, "beta": 54}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
        
        user_id = data.get('user_id')
        pulse = data.get('pulse')
        emg = data.get('emg')
        alpha = data.get('alpha')
        beta = data.get('beta')
        rhythm = data.get('rhythm', 'синусовый')
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        if pulse is None or emg is None or alpha is None or beta is None:
            return jsonify({"error": "Missing required fields: pulse, emg, alpha, beta"}), 400
        
        print(f"[{datetime.now().isoformat()}] Получены данные от user_{user_id}")
        print(f"  → Пульс: {pulse}, Ритм: {rhythm}, ЭМГ: {emg}, Альфа: {alpha}, Бета: {beta}")
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Проверяем, есть ли пользователь
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (id, vk_id, name, role) VALUES (?, ?, ?, ?)",
                (user_id, user_id, f"Пациент #{user_id}", "patient")
            )
            print(f"  → Создан новый пользователь: user_{user_id}")
        
        # Ищем активную сессию со статусом 'waiting_data'
        cursor.execute("""
            SELECT id FROM sessions 
            WHERE user_id = ? AND status = 'waiting_data'
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        
        session = cursor.fetchone()
        
        # Сохраняем сырые данные как JSON-строку
        import json
        raw_data = {
            "pulse": pulse,
            "rhythm": rhythm,
            "emg": emg,
            "alpha": alpha,
            "beta": beta
        }
        
        if session:
            session_id = session['id']
            cursor.execute(
                "UPDATE sessions SET raw_data = ?, status = ? WHERE id = ?",
                (json.dumps(raw_data), "data_received", session_id)
            )
            print(f"  → Обновлена сессия #{session_id}")
        else:
            cursor.execute(
                "INSERT INTO sessions (user_id, status, raw_data) VALUES (?, ?, ?)",
                (user_id, "data_received", json.dumps(raw_data))
            )
            session_id = cursor.lastrowid
            print(f"  → Создана новая сессия #{session_id}")
        
        conn.commit()
        
        # ===== ВЫЗОВ ИИ =====
        try:
            ai_conclusion = get_diagnosis_text(pulse, rhythm, emg, alpha, beta)
            
            cursor.execute("""
                INSERT INTO reports (session_id, ai_conclusion, status)
                VALUES (?, ?, ?)
            """, (session_id, ai_conclusion, "pending"))
            
            conn.commit()
            print(f"  → ИИ поставил диагноз: {ai_conclusion[:50]}...")
            
        except Exception as e:
            print(f"  ⚠️ Ошибка при вызове ИИ: {e}")
            ai_conclusion = "Ошибка анализа. Требуется проверка врачом."
            cursor.execute("""
                INSERT INTO reports (session_id, ai_conclusion, status)
                VALUES (?, ?, ?)
            """, (session_id, ai_conclusion, "pending"))
            conn.commit()
        
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": f"Data received. Pulse: {pulse} BPM",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/start_session', methods=['POST'])
def start_session():
    """
    Создание новой сессии измерения.
    Вызывается ботом, когда пациент нажимает /start_check
    Ожидает JSON: {"user_id": 123}
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Проверяем/создаём пользователя
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (id, vk_id, name, role) VALUES (?, ?, ?, ?)",
                (user_id, user_id, f"Пациент #{user_id}", "patient")
            )
        
        # Создаём сессию со статусом waiting_data
        cursor.execute(
            "INSERT INTO sessions (user_id, status) VALUES (?, ?)",
            (user_id, "waiting_data")
        )
        session_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        print(f"[{datetime.now().isoformat()}] Новая сессия #{session_id} для user_{user_id}")
        
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "message": "Session created. Waiting for data from Arduino."
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/session/<int:session_id>', methods=['GET'])
def get_session_status(session_id):
    """
    Проверка статуса сессии.
    Вызывается ботом, чтобы узнать, пришли ли данные и готов ли отчёт.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.status, s.created_at, u.name 
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
        """, (session_id,))
        
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        return jsonify({
            "session_id": session['id'],
            "status": session['status'],
            "patient_name": session['name'],
            "created_at": session['created_at']
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# ЗАПУСК СЕРВЕРА
# ============================================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 СЕРВЕР ЗАПУЩЕН (с БД SQLite)")
    print("=" * 50)
    print("📡 Эндпоинты:")
    print("   - POST /upload         → приём данных от Arduino")
    print("   - POST /start_session  → создание сессии (бот)")
    print("   - GET  /session/<id>   → проверка статуса сессии")
    print("   - GET  /health         → проверка жизни сервера")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True)

@app.route('/start_session', methods=['POST'])
def start_session():
    """
    Создание новой сессии измерения.
    Вызывается ботом, когда пациент нажимает /start_check
    Ожидает JSON: {"user_id": 123}
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Проверяем/создаём пользователя
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (id, vk_id, name, role) VALUES (?, ?, ?, ?)",
                (user_id, user_id, f"Пациент #{user_id}", "patient")
            )
        
        # Создаём сессию со статусом waiting_data
        cursor.execute(
            "INSERT INTO sessions (user_id, status) VALUES (?, ?)",
            (user_id, "waiting_data")
        )
        session_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        print(f"[{datetime.now().isoformat()}] Новая сессия #{session_id} для user_{user_id}")
        
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "message": "Session created. Waiting for data from Arduino."
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/session/<int:session_id>', methods=['GET'])
def get_session_status(session_id):
    """
    Проверка статуса сессии.
    Вызывается ботом, чтобы узнать, пришли ли данные и готов ли отчёт.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.status, s.created_at, u.name 
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
        """, (session_id,))
        
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        return jsonify({
            "session_id": session['id'],
            "status": session['status'],
            "patient_name": session['name'],
            "created_at": session['created_at']
        }), 200
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================
# ЗАПУСК СЕРВЕРА
# ============================================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 СЕРВЕР ЗАПУЩЕН (с БД SQLite)")
    print("=" * 50)
    print("📡 Эндпоинты:")
    print("   - POST /upload         → приём данных от Arduino")
    print("   - POST /start_session  → создание сессии (бот)")
    print("   - GET  /session/<id>   → проверка статуса сессии")
    print("   - GET  /health         → проверка жизни сервера")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True)