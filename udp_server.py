import os
import socket
import time
import json
import logging
import requests
import threading
from collections import deque
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List

from dotenv import load_dotenv
from doctor_ai import InteractiveDoctorAI

load_dotenv()

logger = logging.getLogger(__name__)

UDP_SEND_PORT = 5005
UDP_RECV_PORT = 5006
BUFFER_SIZE = 11

PEAK_THRESHOLD = 2800
MIN_INTERVAL_MS = 400
MAX_INTERVAL_MS = 1500

EMG_WINDOW = 50
emg_buffer = deque(maxlen=EMG_WINDOW)

GSR_MIN = 500
GSR_MAX = 3800

last_peak_time = 0
bpm = 0.0
stress = 50
muscle = 0
alpha_ratio = 50
beta_ratio = 50
rhythm = "sinus"
pulse_history = deque(maxlen=10)

ESP_IP = os.getenv("ESP_IP", "192.168.0.100")
VK_USER_ID = int(os.getenv("VK_USER_ID", "0"))
SERVER_URL = os.getenv("SERVER_URL", "https://digital-doctor-zwr7.onrender.com").rstrip("/")

frames_buffer = []
BATCH_SIZE = 100

CURRENT_SESSION_ID = None

ai_model = InteractiveDoctorAI()
model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_model.pkl")
if os.path.exists(model_path):
    ai_model.load(model_path)
    logger.info("AI model loaded: %d examples", len(ai_model.X_train))


def calculate_bpm(raw_pulse):
    global last_peak_time, bpm
    if raw_pulse > PEAK_THRESHOLD:
        now_ms = time.time() * 1000
        interval = now_ms - last_peak_time
        if MIN_INTERVAL_MS < interval < MAX_INTERVAL_MS:
            bpm = 60000.0 / interval
            last_peak_time = now_ms
            return bpm
        if last_peak_time == 0:
            last_peak_time = now_ms
    return bpm if bpm > 0 else 0


def calculate_stress(raw_gsr):
    stress_val = int((raw_gsr - GSR_MIN) / ((GSR_MAX - GSR_MIN) / 100))
    return max(0, min(100, stress_val))


def calculate_muscle(raw_emg):
    global muscle
    emg_buffer.append(raw_emg)
    if len(emg_buffer) == EMG_WINDOW:
        emin = min(emg_buffer)
        emax = max(emg_buffer)
        amplitude = emax - emin
        if amplitude > 100:
            muscle_val = int((amplitude - 100) / 24)
            muscle = max(0, min(100, muscle_val))
        else:
            muscle = 0
    return muscle


def calculate_eeg_rhythms(raw_eeg):
    global alpha_ratio, beta_ratio
    raw_norm = max(0, min(100, int(raw_eeg / 4095 * 100)))
    alpha_ratio = int(30 + (100 - raw_norm) * 0.5)
    alpha_ratio = max(0, min(100, alpha_ratio))
    beta_ratio = int(raw_norm * 0.8)
    beta_ratio = max(0, min(100, beta_ratio))
    return alpha_ratio, beta_ratio


def detect_rhythm_type(bpm_val: float, history: List = None) -> str:
    if 130 < bpm_val < 200:
        return "arrhythmia"
    if history and len(history) >= 3:
        variability = max(history) - min(history)
        if variability > 40:
            return "arrhythmia"
    return "sinus"


def decode_esp_packet(data):
    if len(data) != BUFFER_SIZE or data[0] != 0xAA or data[10] != 0x55:
        return None
    crc = 0
    for i in range(1, 9):
        crc ^= data[i]
    if crc != data[9]:
        return None

    pulse = (data[1] << 8) | data[2]
    emg = (data[3] << 8) | data[4]
    eeg = (data[5] << 8) | data[6]
    gsr = (data[7] << 8) | data[8]
    return (pulse, emg, eeg, gsr)


def send_stats_to_esp(bpm_val, stress_val, muscle_val):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    message = f"STATS:{bpm_val:.1f},{stress_val},{muscle_val}"
    try:
        sock.sendto(message.encode(), (ESP_IP, UDP_RECV_PORT))
    except Exception as e:
        logger.warning("Failed to send stats to ESP: %s", e)
    finally:
        sock.close()


def send_mode_command(mode):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    message = f"MODE:{mode}"
    try:
        sock.sendto(message.encode(), (ESP_IP, UDP_RECV_PORT))
        logger.info("Sent command to ESP: %s", message)
    except Exception as e:
        logger.warning("Failed to send command to ESP: %s", e)
    finally:
        sock.close()


def send_to_server(frames):
    def _send():
        try:
            payload = {
                "user_id": VK_USER_ID,
                "session_id": CURRENT_SESSION_ID,
                "frames": frames,
            }
            response = requests.post(f"{SERVER_URL}/upload_batch", json=payload, timeout=15)
            if response.status_code == 200:
                logger.info("Sent %d frames to server successfully", len(frames))
            else:
                logger.error("Server error: %d %s", response.status_code, response.text)
        except Exception as e:
            logger.error("Failed to send frames to server: %s", e)

    threading.Thread(target=_send, daemon=True).start()


@dataclass
class SensorFrame:
    pulse: int
    rhythm: str
    emg: int
    alpha: int
    beta: int
    ts: float


def bar(value: int, max_val: int = 100, width: int = 20) -> str:
    filled = min(max(0, round(value / max_val * width)), width)
    return f"[{'#' * filled}{'.' * (width - filled)}]"


def render_frame(frame: SensorFrame, diagnosis: Dict, frame_num: int):
    state = diagnosis["state"]
    state_color_map = {
        "Норма": "green", "Восстановление": "green", "Напряжение": "yellow",
        "Усталость": "yellow", "Стресс": "red", "Перегрузка": "red", "Аритмия": "magenta",
    }
    state_color = state_color_map.get(state, "white")
    colors = {
        'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m',
        'magenta': '\033[95m', 'cyan': '\033[96m', 'white': '\033[97m', 'reset': '\033[0m',
    }
    print("\033[2J\033[H", end="")
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           DIGITAL DOCTOR - ТЕЛЕМЕТРИЯ                       ║
╠══════════════════════════════════════════════════════════════╣
║  ПУЛЬС:    {bar(frame.pulse, 200)} {frame.pulse:>3} BPM    ║
║  РИТМ:     {frame.rhythm:<12}                              ║
║  ЭМГ:      {bar(frame.emg)} {frame.emg:>3}%                ║
║  АЛЬФА:    {bar(frame.alpha)} {frame.alpha:>3}%            ║
║  БЕТА:     {bar(frame.beta)} {frame.beta:>3}%              ║
╠══════════════════════════════════════════════════════════════╣
║  ДИАГНОЗ ИИ:                                                ║
║  -> {colors.get(state_color, '')}{state}{colors['reset']}                           ║
║  -> Уверенность: {diagnosis['confidence'] * 100:.0f}%       ║
╠══════════════════════════════════════════════════════════════╣
║  Буфер: {len(frames_buffer)}/{BATCH_SIZE} | Кадр #{frame_num} | VK сессия: #{CURRENT_SESSION_ID}
╚══════════════════════════════════════════════════════════════╝
""")


def console_handler():
    while True:
        cmd = input().strip().upper()
        if cmd == "Q":
            print("Выход...")
            break
        elif cmd in ["ALL", "PLS", "EMG", "EEG", "GSR", "STATS"]:
            send_mode_command(cmd)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not VK_USER_ID:
        logger.error("VK_USER_ID not set in .env. Set it to your VK user ID.")
        exit(1)

    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║        Digital Doctor — UDP приёмник                        ║
    ║        Приём бинарных данных с ESP32 + диагностика ИИ       ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    esp_input = input(f"IP адрес ESP32 (Enter = {ESP_IP}): ").strip()
    if esp_input:
        ESP_IP = esp_input

    while True:
        try:
            CURRENT_SESSION_ID = int(input("Введите ID сессии VK бота: ").strip())
            break
        except ValueError:
            print("Ошибка! ID должен быть числом.")

    threading.Thread(target=console_handler, daemon=True).start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_SEND_PORT))
    sock.settimeout(1.0)

    logger.info("Ожидание данных ESP на порту %d...", UDP_SEND_PORT)
    frame_count = 0
    last_send_time = 0
    send_interval = 1.0

    try:
        while True:
            try:
                data, addr = sock.recvfrom(BUFFER_SIZE)
                decoded = decode_esp_packet(data)
                if not decoded:
                    continue

                pulse_raw, emg_raw, eeg_raw, gsr_raw = decoded

                new_bpm = calculate_bpm(pulse_raw)
                if new_bpm > 0:
                    bpm = new_bpm
                    pulse_history.append(bpm)

                stress = calculate_stress(gsr_raw)
                muscle = calculate_muscle(emg_raw)
                alpha_ratio, beta_ratio = calculate_eeg_rhythms(eeg_raw)
                rhythm = detect_rhythm_type(bpm, list(pulse_history))

                frame = SensorFrame(
                    pulse=int(bpm) if bpm > 0 else 70,
                    rhythm=rhythm,
                    emg=muscle,
                    alpha=alpha_ratio,
                    beta=beta_ratio,
                    ts=time.time(),
                )

                frame_count += 1
                diagnosis = ai_model.predict(frame.pulse, frame.rhythm, frame.emg, frame.alpha, frame.beta)

                frames_buffer.append(asdict(frame))

                if len(frames_buffer) >= BATCH_SIZE:
                    send_to_server(frames_buffer.copy())
                    frames_buffer.clear()

                render_frame(frame, diagnosis, frame_count)

                now = time.time()
                if now - last_send_time >= send_interval:
                    send_stats_to_esp(bpm, stress, muscle)
                    last_send_time = now

            except socket.timeout:
                pass
            except Exception as e:
                logger.error("Ошибка обработки пакета: %s", e)

    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем.")
    finally:
        sock.close()
