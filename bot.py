import os
import json
import logging
import threading
import time
import traceback

from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import requests

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    raise ValueError("VK_TOKEN environment variable is not set")

GROUP_ID = int(os.getenv("GROUP_ID", "0"))
if not GROUP_ID:
    raise ValueError("GROUP_ID environment variable is not set")

SERVER_URL = os.getenv("SERVER_URL", "https://digital-doctor-zwr7.onrender.com").rstrip("/")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")

vk_session = vk_api.VkApi(token=TOKEN, api_version='5.131')
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)


def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load users file: %s", e)
            return {}
    return {}


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)


def call_server(endpoint, method="GET", data=None):
    try:
        url = f"{SERVER_URL}/{endpoint.lstrip('/')}"
        if method == "GET":
            r = requests.get(url, timeout=10)
        else:
            r = requests.post(url, json=data, timeout=10)
        return r.json()
    except requests.RequestException as e:
        logger.warning("Server request failed (%s): %s", endpoint, e)
        return {"status": "error", "error": str(e)}


def get_role_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button("Patient", color=VkKeyboardColor.PRIMARY)
    kb.add_button("Doctor", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


def get_patient_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("Start examination", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("My statistics", color=VkKeyboardColor.SECONDARY)
    kb.add_button("Change role", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()


def get_doctor_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("AI statistics", color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("Change role", color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()


def get_decision_keyboard(session_id):
    kb = VkKeyboard(inline=True)
    kb.add_button(
        "Confirm",
        color=VkKeyboardColor.POSITIVE,
        payload={"command": "approve_conclusion", "session_id": session_id},
    )
    kb.add_button(
        "Correct",
        color=VkKeyboardColor.NEGATIVE,
        payload={"command": "show_fix_menu", "session_id": session_id},
    )
    return kb.get_keyboard()


def get_fix_keyboard(session_id):
    kb = VkKeyboard(inline=True)
    states = ["Normal", "Tension", "Fatigue", "Recovery", "Stress", "Overload", "Arrhythmia"]

    for i, state in enumerate(states):
        kb.add_button(
            state,
            color=VkKeyboardColor.SECONDARY,
            payload={"command": "fix_conclusion", "state": state, "session_id": session_id},
        )
        if (i + 1) % 2 == 0 and i < len(states) - 1:
            kb.add_line()

    return kb.get_keyboard()


def check_session_status(vk_client, user_id, session_id):
    start_time = time.time()
    timeout = 300

    logger.info("Monitoring session #%d for user %d", session_id, user_id)

    while time.time() - start_time < timeout:
        try:
            res = call_server(f"session_status/{session_id}")

            if res.get("status") == "data_received":
                report_res = call_server(f"get_report/{session_id}")
                ai_text = report_res.get("ai_conclusion", "Analysis completed successfully.")

                msg_patient = (
                    f"ESP data received successfully!\n\n"
                    f"AI preliminary conclusion:\n{ai_text}\n\n"
                    f"Status: Report sent to the attending physician for moderation."
                )
                vk_client.messages.send(
                    user_id=user_id,
                    message=msg_patient,
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id(),
                )

                users = load_users()
                msg_doctor = (
                    f"New examination data received!\n"
                    f"Patient ID: {user_id}\n"
                    f"Session: #{session_id}\n\n"
                    f"AI verdict:\n{ai_text}\n\n"
                    f"Please review and confirm/correct the result to train the model."
                )

                for uid, info in users.items():
                    if info.get("role") == "doctor":
                        try:
                            vk_client.messages.send(
                                user_id=int(uid),
                                message=msg_doctor,
                                keyboard=get_decision_keyboard(session_id),
                                random_id=get_random_id(),
                            )
                        except Exception as e:
                            logger.warning("Failed to notify doctor %s: %s", uid, e)
                return

        except Exception as e:
            logger.error("Session monitoring error: %s", e)

        time.sleep(10)

    vk_client.messages.send(
        user_id=user_id,
        message="ESP data was not received within 5 minutes. Session timed out.",
        keyboard=get_patient_keyboard(),
        random_id=get_random_id(),
    )


logger.info("Bot started, listening for LongPoll events...")
users_db = load_users()

try:
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_id = event.obj.message['from_id']
            text = event.obj.message['text'].strip()
            payload = event.obj.message.get('payload')

            str_uid = str(user_id)

            if str_uid not in users_db:
                users_db[str_uid] = {"role": None}
                save_users(users_db)
                vk.messages.send(
                    user_id=user_id,
                    message="Welcome to Digital Doctor! Who are you?",
                    keyboard=get_role_keyboard(),
                    random_id=get_random_id(),
                )
                continue

            user_data = users_db.get(str_uid)

            if user_data is None:
                users_db[str_uid] = {"role": None}
                save_users(users_db)
                user_data = users_db[str_uid]
            elif isinstance(user_data, str):
                users_db[str_uid] = {"role": user_data}
                save_users(users_db)
                user_data = users_db[str_uid]
            elif not isinstance(user_data, dict):
                users_db[str_uid] = {"role": None}
                save_users(users_db)
                user_data = users_db[str_uid]

            user_role = user_data.get("role")

            if payload:
                try:
                    payload_data = json.loads(payload)
                    command = payload_data.get("command")
                    sid = payload_data.get("session_id")

                    if command == "approve_conclusion":
                        res = call_server("approve", method="POST", data={"session_id": sid})

                        if res.get("status") == "success":
                            msg = f"Thank you! Diagnosis for session #{sid} confirmed. AI recorded this case as reference."
                        else:
                            msg = f"Failed to send confirmation to server: {res.get('error', 'server error')}"

                        vk.messages.send(
                            user_id=user_id,
                            message=msg,
                            keyboard=get_doctor_keyboard(),
                            random_id=get_random_id(),
                        )
                        continue

                    elif command == "show_fix_menu":
                        vk.messages.send(
                            user_id=user_id,
                            message=f"Select correct diagnosis for session #{sid}:",
                            keyboard=get_fix_keyboard(sid),
                            random_id=get_random_id(),
                        )
                        continue

                    elif command == "fix_conclusion":
                        correct_state = payload_data.get("state")
                        teach_res = call_server(
                            "teach",
                            method="POST",
                            data={"session_id": sid, "correct_state": correct_state},
                        )

                        if teach_res.get("trained"):
                            msg = f"Model successfully retrained!\n\nSession: #{sid}\nCorrect diagnosis: {correct_state}"
                        else:
                            msg = f"Retraining error: {teach_res.get('error', 'unknown error')}"

                        vk.messages.send(
                            user_id=user_id,
                            message=msg,
                            keyboard=get_doctor_keyboard(),
                            random_id=get_random_id(),
                        )
                        continue

                except Exception as ex:
                    logger.error("Payload handling error: %s", ex)

            if text == "Patient":
                users_db[str_uid]["role"] = "patient"
                save_users(users_db)
                vk.messages.send(
                    user_id=user_id,
                    message="You are logged in as Patient.",
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id(),
                )

            elif text == "Doctor":
                users_db[str_uid]["role"] = "doctor"
                save_users(users_db)
                vk.messages.send(
                    user_id=user_id,
                    message="You are logged in as Doctor.",
                    keyboard=get_doctor_keyboard(),
                    random_id=get_random_id(),
                )

            elif text == "Change role":
                users_db[str_uid]["role"] = None
                save_users(users_db)
                vk.messages.send(
                    user_id=user_id,
                    message="Select your role again:",
                    keyboard=get_role_keyboard(),
                    random_id=get_random_id(),
                )

            elif text == "Start examination" and user_role == "patient":
                res = call_server("start_session", method="POST", data={"user_id": user_id})

                if res.get("status") != "success":
                    vk.messages.send(
                        user_id=user_id,
                        message="Failed to create examination session.",
                        random_id=get_random_id(),
                    )
                    continue

                session_id = res["session_id"]
                vk.messages.send(
                    user_id=user_id,
                    message=f"Examination session created.\n\nSession ID: {session_id}\n\nEnter this ID in the emulator.",
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id(),
                )

                threading.Thread(
                    target=check_session_status,
                    args=(vk, user_id, session_id),
                    daemon=True,
                ).start()

            elif text == "My statistics" and user_role == "patient":
                vk.messages.send(
                    user_id=user_id,
                    message="Statistics feature is under development.",
                    keyboard=get_patient_keyboard(),
                    random_id=get_random_id(),
                )

            elif text == "AI statistics" and user_role == "doctor":
                stats_res = call_server("stats", method="GET")
                total_examples = stats_res.get("total_examples", 0)
                states_str = ", ".join(stats_res.get("states", []))

                msg = f"AI STATISTICS:\nTotal examples: {total_examples}\nStates: {states_str}"

                vk.messages.send(
                    user_id=user_id,
                    message=msg,
                    keyboard=get_doctor_keyboard(),
                    random_id=get_random_id(),
                )

            else:
                current_kb = (
                    get_patient_keyboard()
                    if user_role == "patient"
                    else (get_doctor_keyboard() if user_role == "doctor" else get_role_keyboard())
                )
                vk.messages.send(
                    user_id=user_id,
                    message="Command not recognized.",
                    keyboard=current_kb,
                    random_id=get_random_id(),
                )

except Exception:
    logger.critical("LongPoll loop crashed: %s", traceback.format_exc())
