import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import json
import os
import requests
import threading
import time

# ==================== НАСТРОЙКИ ====================
TOKEN = "vk1.a.VRFQnTXRDgsI7k54SIaqdfQLNRv8Mka59_eRkrrp1Ijt2Icewi_NrOtQdSIU83yHx0CCALaaegHR6oo1V-_kWbOo1pJ5GtswMNHPRfD9ZZiIURHBNngJwIiC6sf6xsyfB3ddSZvlPolX0FMnVwchytykm1oP3_7KWZ4Vf1Ywxc3TnMcZtkvJPfSk5zZVUu4zLTGB-q1wJladwS8TGRhy1Q"
GROUP_ID = 237626944
USERS_FILE = "users.json"
SERVER_URL = "https://digital-doctor-zwr7.onrender.com"
# ===================================================

vk_session = vk_api.VkApi(token=TOKEN, api_version='5.131')
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)


# ==================== ЗАПРОСЫ К СЕРВЕРУ ====================
def call_server(endpoint, method="GET", data=None):
    url = f"{SERVER_URL}/{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        return response.json() if response.status_code == 200 else {"error": response.status_code}
    except Exception as e:
        return {"error": str(e)}


# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


# ==================== КЛАВИАТУРЫ ====================
def get_role_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button("🫀 Я Пациент", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("🩺 Я Врач", color=VkKeyboardColor.PRIMARY)
    return kb.get_keyboard()


def get_patient_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("/start_check", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("/reset", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()


def get_doctor_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("📋 Список отчетов", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("/reset", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()


def get_approve_keyboard(session_id):
    kb = VkKeyboard(one_time=True)
    kb.add_button(f"✅ Подтвердить #{session_id}", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button(f"❌ Исправить #{session_id}", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


def get_states_keyboard(session_id):
    states = ["Normal", "Stress", "Arrhythmia", "Fatigue"]
    kb = VkKeyboard(one_time=True)
    for i, state in enumerate(states):
        kb.add_button(f"{state}#{session_id}", color=VkKeyboardColor.PRIMARY)
        if i % 2 == 1: kb.add_line()
    return kb.get_keyboard()


# ==================== УВЕДОМЛЕНИЕ ВРАЧЕЙ ====================
def notify_all_doctors(session_id):
    users = load_users()
    for uid, role in users.items():
        if role == "doctor":
            try:
                vk.messages.send(
                    user_id=int(uid),
                    message=f"🔔 Новый отчет #{session_id} готов к проверке!\nНажмите кнопку 'Список отчетов' или введите /report {session_id}",
                    random_id=get_random_id()
                )
            except:
                pass


# ==================== ФОНОВАЯ ПРОВЕРКА ====================
def check_session_status(user_id, session_id):
    for _ in range(30):
        time.sleep(10)
        report = call_server(f"report/{session_id}")
        conclusion = report.get("ai_conclusion")

        if conclusion and conclusion != "None":
            vk.messages.send(
                user_id=user_id,
                message=f"📊 Отчет #{session_id} готов!\n\nИИ говорит: {conclusion}\n\nВаши данные переданы врачу на проверку.",
                random_id=get_random_id()
            )
            notify_all_doctors(session_id)
            return
    vk.messages.send(user_id=user_id, message="⚠️ Данные не получены. Тайм-аут.", random_id=get_random_id())


# ==================== ОСНОВНОЙ ЦИКЛ ====================
print("🚀 Бот House MD Project запущен...")

while True:
    try:
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.obj.message:
                user_id = event.obj.message['from_id']
                text = event.obj.message.get('text', '').strip()
                users_db = load_users()

                if text.lower() == "/reset":
                    if str(user_id) in users_db: del users_db[str(user_id)]
                    save_users(users_db)
                    vk.messages.send(user_id=user_id, message="🔄 Роль сброшена.", keyboard=get_role_keyboard(),
                                     random_id=get_random_id())
                    continue

                role = users_db.get(str(user_id))

                # Регистрация
                if text == "🫀 Я Пациент":
                    users_db[str(user_id)] = "patient"
                    save_users(users_db)
                    vk.messages.send(user_id=user_id, message="✅ Вы вошли как Пациент", keyboard=get_patient_keyboard(),
                                     random_id=get_random_id())
                elif text == "🩺 Я Врач":
                    users_db[str(user_id)] = "doctor"
                    save_users(users_db)
                    vk.messages.send(user_id=user_id, message="✅ Вы вошли как Врач", keyboard=get_doctor_keyboard(),
                                     random_id=get_random_id())
                elif not role:
                    vk.messages.send(user_id=user_id, message="👋 Выберите вашу роль:", keyboard=get_role_keyboard(),
                                     random_id=get_random_id())

                # Логика Пациента
                elif role == "patient" and text.lower() == "/start_check":
                    res = call_server("start_session", method="POST", data={"user_id": user_id})
                    if "session_id" in res:
                        sid = res["session_id"]
                        vk.messages.send(user_id=user_id, message=f"🔍 Сессия #{sid} начата. Жду данные...",
                                         random_id=get_random_id())
                        threading.Thread(target=check_session_status, args=(user_id, sid)).start()

                # Логика Врача
                elif role == "doctor":
                    if text == "/reports" or text == "📋 Список отчетов":
                        res = call_server("pending_reports")
                        if "error" in res:
                            vk.messages.send(user_id=user_id, message=f"❌ Ошибка сервера: {res['error']}",
                                             random_id=get_random_id())
                        else:
                            reports = res.get('reports', [])
                            if reports:
                                items = [f"🆔 Сессия #{r['session_id']} (User: {r.get('user_id', '???')})" for r in
                                         reports]
                                msg = "📋 Ожидают проверки:\n\n" + "\n".join(items) + "\n\nВведите: /report [номер]"
                                vk.messages.send(user_id=user_id, message=msg, random_id=get_random_id())
                            else:
                                vk.messages.send(user_id=user_id, message="✅ Новых отчетов нет.",
                                                 random_id=get_random_id())

                    elif text.startswith("/report "):
                        parts = text.split()
                        if len(parts) >= 2:
                            sid = parts[1]
                            res = call_server(f"report/{sid}")
                            if "ai_conclusion" in res and res["ai_conclusion"] != "None":
                                vk.messages.send(user_id=user_id, message=f"📝 Отчет #{sid}: {res['ai_conclusion']}",
                                                 keyboard=get_approve_keyboard(sid), random_id=get_random_id())
                            else:
                                vk.messages.send(user_id=user_id, message=f"❓ Отчет #{sid} не готов.",
                                                 random_id=get_random_id())

                    elif "✅ Подтвердить #" in text:
                        sid = text.split("#")[-1]
                        vk.messages.send(user_id=user_id, message=f"✅ Отчет #{sid} подтвержден.",
                                         keyboard=get_doctor_keyboard(), random_id=get_random_id())

                    elif "❌ Исправить #" in text:
                        sid = text.split("#")[-1]
                        vk.messages.send(user_id=user_id, message=f"Выберите верный диагноз для #{sid}:",
                                         keyboard=get_states_keyboard(sid), random_id=get_random_id())

                    elif "#" in text and any(s in text for s in ["Normal", "Stress", "Arrhythmia", "Fatigue"]):
                        clean_text = text.replace(" ", "")
                        state, sid = clean_text.split("#")
                        teach_res = call_server("teach", method="POST",
                                                data={"session_id": sid, "correct_state": state})
                        vk.messages.send(user_id=user_id, message=f"🎯 Обучено: #{sid} -> {state}",
                                         keyboard=get_doctor_keyboard(), random_id=get_random_id())

    except Exception as e:
        print(f"🆘 Ошибка: {e}")
        time.sleep(5)

