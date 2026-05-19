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

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

def call_server(endpoint, method="GET", data=None):
    """Универсальная функция запросов к Flask-серверу"""
    try:
        url = f"{SERVER_URL}/{endpoint}"
        if method == "GET":
            r = requests.get(url, timeout=10)
        else:
            r = requests.post(url, json=data, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Ошибка запроса к серверу {endpoint}: {e}")
        return {"status": "error", "error": str(e)}

# ==================== КЛАВИАТУРЫ ====================

def get_role_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button("Я Пациент", color=VkKeyboardColor.PRIMARY)
    kb.add_button("Я Врач", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

def get_patient_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("🤖 Начать обследование", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("📊 Моя статистика", color=VkKeyboardColor.SECONDARY)
    kb.add_button("🔄 Сменить роль", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_doctor_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("🔎 Посмотреть статистику ИИ", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🔄 Сменить роль", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_decision_keyboard(session_id):
    """Клавиатура действий для врача при получении отчёта"""
    kb = VkKeyboard(inline=True)
    # Кнопка подтверждения диагноза
    kb.add_button(
        "✅ Подтвердить", 
        color=VkKeyboardColor.POSITIVE, 
        payload={"command": "approve_conclusion", "session_id": session_id}
    )
    # Кнопка вызова меню исправления диагноза
    kb.add_button(
        "❌ Исправить", 
        color=VkKeyboardColor.NEGATIVE, 
        payload={"command": "show_fix_menu", "session_id": session_id}
    )
    return kb.get_keyboard()

def get_fix_keyboard(session_id):
    """Клавиатура со списком всех возможных диагнозов для дообучения ИИ"""
    kb = VkKeyboard(inline=True)
    states = ["Normal", "Tension", "Fatigue", "Recovery", "Stress", "Overload", "Arrhythmia"]
    
    for i, state in enumerate(states):
        kb.add_button(
            state, 
            color=VkKeyboardColor.SECONDARY, 
            payload={"command": "fix_conclusion", "state": state, "session_id": session_id}
        )
        # Делаем перенос строки каждые 2 кнопки, чтобы клавиатура выглядела аккуратно
        if (i + 1) % 2 == 0 and i < len(states) - 1:
            kb.add_line()
            
    return kb.get_keyboard()

# ==================== МОНИТОРИНГ СЕССИИ ====================

def check_session_status(vk, user_id, session_id):
    """Фоновый поток: ждет, пока эмулятор пришлет пакет данных на Flask"""
    start_time = time.time()
    timeout = 300  # 5 минут ожидания
    
    print(f"[THREAD] Начат мониторинг статуса для сессии #{session_id}")
    
    while time.time() - start_time < timeout:
        try:
            res = call_server(f"session_status/{session_id}")
            
            # Как только UDP-сервер загрузил пакет кадров на Flask:
            if res.get("status") == "data_received":
                # Шаг 1. Забираем готовое заключение ИИ
                report_res = call_server(f"get_report/{session_id}")
                ai_text = report_res.get("ai_conclusion", "Анализ успешно завершен.")
                
                # Шаг 2. Отправляем пользователю (пациенту) предварительный результат
                msg_patient = (
                    f"✅ Данные с эмулятора ESP успешно получены!\n\n"
                    f"🤖 Предварительное заключение ИИ:\n{ai_text}\n\n"
                    f"⏳ Статус: Отчет отправлен на модерацию дежурному врачу."
                )
                vk.messages.send(
                    user_id=user_id,
                    message=msg_patient,
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id()
                )
                
                # Шаг 3. Рассылаем дежурным врачам карточку для валидации и обучения ИИ
                users = load_users()
                msg_doctor = (
                    f"🚨 Поступили новые данные обследования!\n"
                    f"Пациент ID: {user_id}\n"
                    f"Сессия: #{session_id}\n\n"
                    f"🤖 Вердикт ИИ:\n{ai_text}\n\n"
                    f"Пожалуйста, проверьте показатели и подтвердите/исправьте результат для обучения модели."
                )
                
                for uid, info in users.items():
                    if info.get("role") == "doctor":
                        vk.messages.send(
                            user_id=int(uid),
                            message=msg_doctor,
                            keyboard=get_decision_keyboard(session_id),
                            random_id=get_random_id()
                        )
                return  # Успешно завершаем фоновый поток!
                
        except Exception as e:
            print(f"[THREAD ERROR] Ошибка при проверке статуса: {e}")
            
        time.sleep(10)  # Опрос раз в 10 секунд
        
    # Если данные так и не пришли за 5 минут:
    vk.messages.send(
        user_id=user_id,
        message="⚠️ Данные от эмулятора ESP не были получены в течение 5 минут. Время сессии истекло.",
        keyboard=get_patient_keyboard(),
        random_id=get_random_id()
    )

# ==================== СТАРТ ЛОНГПОЛЛА ====================

print("Бот запущен и слушает LongPoll...")
users_db = load_users()

try:
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_id = event.obj.message['from_id']
            text = event.obj.message['text'].strip()
            payload = event.obj.message.get('payload')

            str_uid = str(user_id)

            # ==================== РЕГИСТРАЦИЯ / ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ ====================

            if str_uid not in users_db:
                users_db[str_uid] = {"role": None}
                save_users(users_db)

                vk.messages.send(
                    user_id=user_id,
                    message="👋 Приветствую в системе Digital Doctor! Кто вы?",
                    keyboard=get_role_keyboard(),
                    random_id=get_random_id()
                )
                continue

            # Безопасная обработка структуры users.json
            user_data = users_db.get(str_uid)

            # Если данных нет
            if user_data is None:
                users_db[str_uid] = {"role": None}
                save_users(users_db)
                user_data = users_db[str_uid]

            # Если старый формат: "patient" / "doctor"
            elif isinstance(user_data, str):
                users_db[str_uid] = {"role": user_data}
                save_users(users_db)
                user_data = users_db[str_uid]

            # Если файл повреждён
            elif not isinstance(user_data, dict):
                users_db[str_uid] = {"role": None}
                save_users(users_db)
                user_data = users_db[str_uid]

            user_role = user_data.get("role")

            # --- ОБРАБОТКА ИНЛАЙН/PAYLOAD КНОПОК ДЛЯ ВРАЧА (ОБУЧЕНИЕ ИИ) ---
            if payload:
                try:
                    payload_data = json.loads(payload)
                    command = payload_data.get("command")
                    sid = payload_data.get("session_id")

                    # 1. Врач подтвердил выбор ИИ
                    if command == "approve_conclusion":
                        res = call_server(
                            "approve",
                            method="POST",
                            data={"session_id": sid}
                        )

                        if res.get("status") == "success":
                            msg = (
                                f"✅ Спасибо! Диагноз для сессии #{sid} "
                                f"подтвержден. ИИ зафиксировал этот случай как эталонный."
                            )
                        else:
                            msg = (
                                f"❌ Не удалось отправить подтверждение "
                                f"на сервер: {res.get('error', 'ошибка сервера')}"
                            )

                        vk.messages.send(
                            user_id=user_id,
                            message=msg,
                            keyboard=get_doctor_keyboard(),
                            random_id=get_random_id()
                        )
                        continue

                    # 2. Врач нажал "Исправить"
                    elif command == "show_fix_menu":
                        vk.messages.send(
                            user_id=user_id,
                            message=(
                                f"🛠 Выберите правильный диагноз "
                                f"для сессии #{sid}:"
                            ),
                            keyboard=get_fix_keyboard(sid),
                            random_id=get_random_id()
                        )
                        continue

                    # 3. Дообучение модели
                    elif command == "fix_conclusion":
                        correct_state = payload_data.get("state")

                        teach_res = call_server(
                            "teach",
                            method="POST",
                            data={
                                "session_id": sid,
                                "correct_state": correct_state
                            }
                        )

                        if teach_res.get("trained"):
                            msg = (
                                f"🎯 Модель успешно дообучена!\n\n"
                                f"Сессия: #{sid}\n"
                                f"Правильный диагноз: {correct_state}"
                            )
                        else:
                            msg = (
                                f"❌ Ошибка дообучения: "
                                f"{teach_res.get('error', 'неизвестная ошибка')}"
                            )

                        vk.messages.send(
                            user_id=user_id,
                            message=msg,
                            keyboard=get_doctor_keyboard(),
                            random_id=get_random_id()
                        )
                        continue

                except Exception as ex:
                    print(f"Ошибка payload: {ex}")

            # ==================== НАВИГАЦИЯ ====================

            if text == "Я Пациент":
                users_db[str_uid]["role"] = "patient"
                save_users(users_db)

                vk.messages.send(
                    user_id=user_id,
                    message="Вы зашли как Пациент.",
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id()
                )

            elif text == "Я Врач":
                users_db[str_uid]["role"] = "doctor"
                save_users(users_db)

                vk.messages.send(
                    user_id=user_id,
                    message="Вы зашли как Врач.",
                    keyboard=get_doctor_keyboard(),
                    random_id=get_random_id()
                )

            elif text == "🔄 Сменить роль":
                users_db[str_uid]["role"] = None
                save_users(users_db)

                vk.messages.send(
                    user_id=user_id,
                    message="Выберите роль заново:",
                    keyboard=get_role_keyboard(),
                    random_id=get_random_id()
                )

            # ==================== ПАЦИЕНТ ====================

            elif text == "🤖 Начать обследование" and user_role == "patient":

                res = call_server(
                    "start_session",
                    method="POST",
                    data={"user_id": user_id}
                )

                if res.get("status") != "success":
                    vk.messages.send(
                        user_id=user_id,
                        message="❌ Не удалось создать сессию обследования.",
                        random_id=get_random_id()
                    )
                    continue

                session_id_placeholder = res["session_id"]

                vk.messages.send(
                    user_id=user_id,
                    message=(
                        f"⏳ Сессия обследования создана.\n\n"
                        f"🔑 ID СЕССИИ: {session_id_placeholder}\n\n"
                        f"Введите этот номер в эмулятор."
                    ),
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id()
                )


            elif text == "📊 Моя статистика" and user_role == "patient":

                vk.messages.send(
                    user_id=user_id,
                    message="📈 Функция статистики пока в разработке.",
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id()
                )

            # ==================== ВРАЧ ====================

            elif text == "🔎 Посмотреть статистику ИИ" and user_role == "doctor":

                stats_res = call_server("stats", method="GET")

                total_samples = stats_res.get("total_samples", 0)
                history_len = len(stats_res.get("training_history", []))

                msg = (
                    f"📊 СТАТИСТИКА ИИ:\n"
                    f"─ Прецедентов: {total_samples}\n"
                    f"─ Дообучений: {history_len}"
                )

                vk.messages.send(
                    user_id=user_id,
                    message=msg,
                    keyboard=get_doctor_keyboard(),
                    random_id=get_random_id()
                )

            else:
                current_kb = (
                    get_patient_keyboard()
                    if user_role == "patient"
                    else (
                        get_doctor_keyboard()
                        if user_role == "doctor"
                        else get_role_keyboard()
                    )
                )

                vk.messages.send(
                    user_id=user_id,
                    message="❓ Команда не распознана.",
                    keyboard=current_kb,
                    random_id=get_random_id()
                )

except Exception:
    print(f"Критический сбой цикла LongPoll: {traceback.format_exc()}")