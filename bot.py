import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import json
import os
import requests
import threading
import time
import traceback

# ==================== НАСТРОЙКИ ====================
TOKEN = "vk1.a.VRFQnTXRDgsI7k54SIaqdfQLNRv8Mka59_eRkrrp1Ijt2Icewi_NrOtQdSIU83yHx0CCALaaegHR6oo1V-_kWbOo1pJ5GtswMNHPRfD9ZZiIURHBNngJwIiC6sf6xsyfB3ddSZvlPolX0FMnVwchytykm1oP3_7KWZ4Vf1Ywxc3TnMcZtkvJPfSk5zZVUu4zLTGB-q1wJladwS8TGRhy1Q"
GROUP_ID = 237626944

USERS_FILE = "users.json"
SERVER_URL = "https://digital-doctor-zwr7.onrender.com"

# ===================================================

vk_session = vk_api.VkApi(
    token=TOKEN,
    api_version='5.131'
)

vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)
notified_sessions = set()

# ==================== ЗАПРОСЫ К СЕРВЕРУ ====================

def call_server(endpoint, method="GET", data=None):
    url = f"{SERVER_URL}/{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, timeout=15)

        elif method == "POST":
            response = requests.post(
                url,
                json=data,
                timeout=15
            )

        response.encoding = "utf-8"

        if response.status_code == 200:
            return response.json()

        return {
            "error": f"HTTP {response.status_code}"
        }

    except Exception as e:
        return {
            "error": str(e)
        }

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
        json.dump(
            users,
            f,
            ensure_ascii=False,
            indent=4
        )

# ==================== КЛАВИАТУРЫ ====================

def get_role_keyboard():
    kb = VkKeyboard(one_time=True)

    kb.add_button(
        "🫀 Я Пациент",
        color=VkKeyboardColor.POSITIVE
    )

    kb.add_line()

    kb.add_button(
        "🩺 Я Врач",
        color=VkKeyboardColor.PRIMARY
    )

    return kb.get_keyboard()

def get_patient_keyboard():
    kb = VkKeyboard(one_time=False)

    kb.add_button(
        "/start_check",
        color=VkKeyboardColor.PRIMARY
    )

    kb.add_line()

    kb.add_button(
        "/reset",
        color=VkKeyboardColor.SECONDARY
    )

    return kb.get_keyboard()

def get_doctor_keyboard():
    kb = VkKeyboard(one_time=False)

    kb.add_button(
        "📋 Список отчетов",
        color=VkKeyboardColor.PRIMARY
    )

    kb.add_line()

    kb.add_button(
        "/reset",
        color=VkKeyboardColor.SECONDARY
    )

    return kb.get_keyboard()

def get_approve_keyboard(session_id):
    kb = VkKeyboard(one_time=True)

    kb.add_button(
        f"✅ Подтвердить #{session_id}",
        color=VkKeyboardColor.POSITIVE
    )

    kb.add_line()

    kb.add_button(
        f"❌ Исправить #{session_id}",
        color=VkKeyboardColor.NEGATIVE
    )

    return kb.get_keyboard()

def get_states_keyboard(session_id):
    states = [
        "Normal",
        "Stress",
        "Arrhythmia",
        "Fatigue"
    ]

    kb = VkKeyboard(one_time=True)

    for i, state in enumerate(states):

        kb.add_button(
            f"{state}#{session_id}",
            color=VkKeyboardColor.PRIMARY
        )

        if i % 2 == 1:
            kb.add_line()

    return kb.get_keyboard()

# ==================== УВЕДОМЛЕНИЕ ВРАЧЕЙ ====================

def notify_all_doctors(session_id):

    global notified_sessions

    if session_id in notified_sessions:
        return

    notified_sessions.add(session_id)

    users = load_users()

    for uid, role in users.items():

        if role == "doctor":

            try:

                vk.messages.send(
                    user_id=int(uid),
                    message=(
                        f"🔔 Новый отчет #{session_id} готов к проверке!\n\n"
                        f"Введите:\n"
                        f"/report {session_id}"
                    ),
                    random_id=get_random_id()
                )

            except Exception as e:
                print("Ошибка уведомления врача:", e)


# ==================== ПРОВЕРКА СТАТУСА ====================

def check_session_status(user_id, session_id):

    for _ in range(30):

        time.sleep(10)

        report = call_server(f"report/{session_id}")

        if "error" in report:
            continue

        conclusion = report.get("ai_conclusion")

        if conclusion and conclusion != "None":

            vk.messages.send(
                user_id=user_id,
                message=(
                    f"📊 Отчет #{session_id} готов!\n\n"
                    f"ИИ говорит:\n"
                    f"{conclusion}\n\n"
                    f"Ваши данные переданы врачу."
                ),
                random_id=get_random_id()
            )

            notify_all_doctors(session_id)

            return

    vk.messages.send(
        user_id=user_id,
        message="⚠️ Данные не получены. Тайм-аут.",
        random_id=get_random_id()
    )

# ==================== ЗАПУСК ====================

print("🚀 Бот House MD Project запущен...")

while True:

    try:

        for event in longpoll.listen():

            if (
                event.type == VkBotEventType.MESSAGE_NEW
                and event.obj.message
            ):

                user_id = event.obj.message["from_id"]

                text = (
                    event.obj.message
                    .get("text", "")
                    .strip()
                )

                users_db = load_users()

                role = users_db.get(str(user_id))

                # ==================== RESET ====================

                if text.lower() == "/reset":

                    if str(user_id) in users_db:
                        del users_db[str(user_id)]

                    save_users(users_db)

                    vk.messages.send(
                        user_id=user_id,
                        message="🔄 Роль сброшена.",
                        keyboard=get_role_keyboard(),
                        random_id=get_random_id()
                    )

                    continue

                # ==================== РЕГИСТРАЦИЯ ====================

                if text == "🫀 Я Пациент":

                    users_db[str(user_id)] = "patient"

                    save_users(users_db)

                    vk.messages.send(
                        user_id=user_id,
                        message="✅ Вы вошли как Пациент",
                        keyboard=get_patient_keyboard(),
                        random_id=get_random_id()
                    )

                    continue

                elif text == "🩺 Я Врач":

                    users_db[str(user_id)] = "doctor"

                    save_users(users_db)

                    vk.messages.send(
                        user_id=user_id,
                        message="✅ Вы вошли как Врач",
                        keyboard=get_doctor_keyboard(),
                        random_id=get_random_id()
                    )

                    continue

                elif not role:

                    vk.messages.send(
                        user_id=user_id,
                        message="👋 Выберите вашу роль:",
                        keyboard=get_role_keyboard(),
                        random_id=get_random_id()
                    )

                    continue

                elif text.lower() == "/myid":

                    vk.messages.send(
                        user_id=user_id,
                        message=f"🆔 Ваш VK ID:\n{user_id}",
                        random_id=get_random_id()
                    )

                    continue

                elif text.lower() == "/health":

                    health = call_server("health")

                    vk.messages.send(
                        user_id=user_id,
                        message=f"🟢 Сервер:\n{health}",
                        random_id=get_random_id()
                    )

                    continue

                elif text.lower() == "/stats":

                    stats = call_server("statistics")

                    msg = (
                        f"📊 Статистика ИИ\n\n"
                        f"Примеров: {stats.get('total_examples')}\n"
                        f"Обучена: {stats.get('is_fitted')}\n\n"
                        f"Состояния:\n"
                        + "\n".join(stats.get("states", []))
                    )

                    vk.messages.send(
                        user_id=user_id,
                        message=msg,
                        random_id=get_random_id()
                    )

                    continue
                # ==================== ПАЦИЕНТ ====================

                if role == "patient":

                    if text.lower() == "/start_check":

                        res = call_server(
                            "start_session",
                            method="POST",
                            data={
                                "user_id": user_id
                            }
                        )

                        if "session_id" in res:

                            sid = res["session_id"]

                            vk.messages.send(
                                user_id=user_id,
                                message=(
                                    f"🔍 Сессия #{sid} начата.\n\n"
                                    f"⏳ Ожидаю данные с датчиков...\n"
                                    f"📡 ESP32 должен отправить 500 кадров."
                                ),
                                random_id=get_random_id()
                            )

                            threading.Thread(
                                target=check_session_status,
                                args=(user_id, sid),
                                daemon=True
                            ).start()

                # ==================== ВРАЧ ====================

                elif role == "doctor":

                    if text == "📋 Список отчетов":

                        res = call_server("pending_reports")

                        reports = res.get("reports", [])

                        if reports:

                            items = []

                            for r in reports:
                                items.append(
                                    f"🆔 Сессия #{r['session_id']} | 👤 User ID: {r.get('user_id', 'Unknown')}"
                                )

                            msg = (
                                "📋 Ожидают проверки:\n\n"
                                + "\n".join(items)
                                + "\n\nВведите:\n/report [номер]"
                            )

                        else:
                            msg = "✅ Новых отчетов нет."

                        vk.messages.send(
                            user_id=user_id,
                            message=msg,
                            random_id=get_random_id()
                        )

                    elif text.startswith("/report"):

                        parts = text.split()

                        if len(parts) >= 2:

                            sid = parts[1]

                            res = call_server(f"report/{sid}")

                            if (
                                "ai_conclusion" in res
                                and res["ai_conclusion"] != "None"
                            ):

                                raw = res.get("raw_data", {})

                                # ===== BATCH =====
                                if isinstance(raw, list):

                                    last = raw[-1]

                                    pulse = last.get("pulse", "???")
                                    rhythm = last.get("rhythm", "???")
                                    emg = last.get("emg", "???")
                                    alpha = last.get("alpha", "???")
                                    beta = last.get("beta", "???")

                                    msg = (
                                        f"📝 Batch Report #{sid}\n\n"
                                        f"📦 Frames received: {len(raw)}\n\n"

                                        f"📊 Last frame:\n"
                                        f"❤️ Pulse: {pulse}\n"
                                        f"🫀 Rhythm: {rhythm}\n"
                                        f"💪 EMG: {emg}\n"
                                        f"🧠 Alpha: {alpha}\n"
                                        f"🧠 Beta: {beta}\n\n"

                                        f"🤖 AI conclusion:\n"
                                        f"{res['ai_conclusion']}"
                                    )

                                # ===== SINGLE =====
                                else:

                                    pulse = raw.get("pulse", "???")
                                    rhythm = raw.get("rhythm", "???")
                                    emg = raw.get("emg", "???")
                                    alpha = raw.get("alpha", "???")
                                    beta = raw.get("beta", "???")

                                    msg = (
                                        f"📝 Report #{sid}\n\n"
                                        f"📊 Patient data:\n"
                                        f"❤️ Pulse: {pulse}\n"
                                        f"🫀 Rhythm: {rhythm}\n"
                                        f"💪 EMG: {emg}\n"
                                        f"🧠 Alpha: {alpha}\n"
                                        f"🧠 Beta: {beta}\n\n"

                                        f"🤖 AI conclusion:\n"
                                        f"{res['ai_conclusion']}"
                                    )

                                vk.messages.send(
                                    user_id=user_id,
                                    message=msg,
                                    keyboard=get_approve_keyboard(sid),
                                    random_id=get_random_id()
                                )

                            else:

                                vk.messages.send(
                                    user_id=user_id,
                                    message=f"❓ Отчет #{sid} не готов.",
                                    random_id=get_random_id()
                                )

                        elif "❌ Исправить #" in text:

                            sid = text.split("#")[-1]

                            vk.messages.send(
                                user_id=user_id,
                                message=f"Выберите правильный диагноз для #{sid}:",
                                keyboard=get_states_keyboard(sid),
                                random_id=get_random_id()
                            )

                        elif (
                            "#" in text
                            and any(
                                s in text for s in
                                [
                                    "Normal",
                                    "Stress",
                                    "Arrhythmia",
                                    "Fatigue"
                                ]
                            )
                        ):

                            clean_text = text.replace(" ", "")

                            parts = clean_text.split("#")

                            if len(parts) == 2:

                                state = parts[0]
                                sid = parts[1]

                                teach_res = call_server(
                                    "teach",
                                    method="POST",
                                    data={
                                        "session_id": sid,
                                        "correct_state": state
                                    }
                                )

                                if teach_res.get("trained"):

                                    msg = (
                                        f"🎯 ИИ обучен!\n\n"
                                        f"Сессия #{sid}\n"
                                        f"Правильный диагноз: {state}"
                                    )

                                else:

                                    msg = (
                                        f"❌ Ошибка обучения:\n"
                                        f"{teach_res}"
                                    )

                                vk.messages.send(
                                    user_id=user_id,
                                    message=msg,
                                    keyboard=get_doctor_keyboard(),
                                    random_id=get_random_id()
                                )

    except Exception as e:

        print(traceback.format_exc())

        time.sleep(5)