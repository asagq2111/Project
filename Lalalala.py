#!/usr/bin/env python3
"""
DrHouse UDP Server - Digital Doctor
Receives binary packets from ESP32, analyzes via AI and displays in terminal.
"""

import socket
import time
import json
import requests
import threading
from collections import deque
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List

# ==================== AI ENGINE ====================
try:
    from ai_engine import DigitalDoctorAI
except ImportError:
    # Simple AI based on rules
    class DigitalDoctorAI:
        STATES = ["Normal", "Tension", "Fatigue", "Recovery", "Stress", "Overload", "Arrhythmia (AF)"]
        
        def predict_state(self, pulse, rhythm, emg, alpha, beta):
            # Simple logic based on pulse
            if pulse > 140:
                state = "Arrhythmia (AF)"
                conf = 0.85
            elif pulse > 95:
                state = "Stress"
                conf = 0.75
            elif pulse > 85:
                state = "Tension"
                conf = 0.70
            elif pulse > 70:
                state = "Normal"
                conf = 0.80
            else:
                state = "Recovery"
                conf = 0.75
            return {"state": state, "confidence": conf, "risk_level": "Medium"}
        
        def generate_draft_report(self, patient_id, measurements):
            return f"Report for {patient_id}"


# ==================== SETTINGS ====================
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

SESSION_FILE = "patient_sessions.json"

# Global variables
last_peak_time = 0
bpm = 0.0
stress = 50
muscle = 0
alpha_ratio = 50
beta_ratio = 50
rhythm = "sinus"
pulse_history = deque(maxlen=10)
ESP_IP = "192.168.0.100"

SERVER_URL = "https://digital-doctor-zwr7.onrender.com"

frames_buffer = []
BATCH_SIZE = 500


# ==================== DATA PROCESSING ====================

def calculate_bpm(raw_pulse):
    """Calculate BPM from raw signal"""
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
    """Calculate stress level (0-100%) from GSR"""
    stress_val = int((raw_gsr - GSR_MIN) / ((GSR_MAX - GSR_MIN) / 100))
    return max(0, min(100, stress_val))

def calculate_muscle(raw_emg):
    """Calculate muscle activity (0-100%) from EMG"""
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
    """Calculate alpha and beta rhythms from raw EEG"""
    global alpha_ratio, beta_ratio
    
    raw_norm = max(0, min(100, int(raw_eeg / 4095 * 100)))
    alpha_ratio = int(30 + (100 - raw_norm) * 0.5)
    alpha_ratio = max(0, min(100, alpha_ratio))
    beta_ratio = int(raw_norm * 0.8)
    beta_ratio = max(0, min(100, beta_ratio))
    
    return alpha_ratio, beta_ratio

def detect_rhythm_type(bpm: float, history: List = None) -> str:
    """Detect rhythm type: 'sinus' or 'arrhythmia'"""
    if 130 < bpm < 200:
        return "arrhythmia"
    
    if history and len(history) >= 3:
        variability = max(history) - min(history)
        if variability > 40:
            return "arrhythmia"
    
    return "sinus"

def decode_esp_packet(data):
    """Decode binary packet from ESP32"""
    if len(data) != BUFFER_SIZE or data[0] != 0xAA or data[10] != 0x55:
        return None
    
    crc = 0
    for i in range(1, 9):
        crc ^= data[i]
    if crc != data[9]:
        return None
    
    pulse = (data[1] << 8) | data[2]
    emg   = (data[3] << 8) | data[4]
    eeg   = (data[5] << 8) | data[6]
    gsr   = (data[7] << 8) | data[8]
    
    return (pulse, emg, eeg, gsr)


# ==================== ESP COMMUNICATION ====================

def send_stats_to_esp(bpm, stress, muscle):
    """Send statistics back to ESP"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    message = f"STATS:{bpm:.1f},{stress},{muscle}"
    try:
        sock.sendto(message.encode(), (ESP_IP, UDP_RECV_PORT))
        print(f"[SENT] {message}")
    except Exception as e:
        print(f"Send error: {e}")
    finally:
        sock.close()

def send_mode_command(mode):
    """Send mode command to ESP"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    message = f"MODE:{mode}"
    try:
        sock.sendto(message.encode(), (ESP_IP, UDP_RECV_PORT))
        print(f"[CMD] {message}")
    except Exception as e:
        print(f"Send error: {e}")
    finally:
        sock.close()


def send_to_server(frames):
    try:
        payload = {
            "user_id": 396418403,
            "frames": frames
        }

        response = requests.post(
            f"{SERVER_URL}/upload_batch",
            json=payload,
            timeout=30
        )

        print(f"[SERVER] Sent {len(frames)} frames")

    except Exception as e:
        print("SERVER ERROR:", e)


# ==================== AI AND SESSIONS ====================

@dataclass
class SensorFrame:
    pulse: int
    rhythm: str
    emg: int
    alpha: int
    beta: int
    ts: float

class DrHouseServer:
    def __init__(self, patient_id: str = "Patient_001", esp_ip: str = "192.168.0.100"):
        self.patient_id = patient_id
        self.esp_ip = esp_ip
        self.ai = DigitalDoctorAI()
        self.sessions = self.load_sessions()
        self.current_session = {
            "start_time": datetime.now().isoformat(),
            "frames": [],
            "diagnoses": []
        }
        
    def load_sessions(self) -> Dict:
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_sessions(self):
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.sessions, f, indent=2, ensure_ascii=False)
    
    def process_frame(self, frame: SensorFrame) -> Dict:
        result = self.ai.predict_state(
            pulse=frame.pulse,
            rhythm=frame.rhythm,
            emg=frame.emg,
            alpha=frame.alpha,
            beta=frame.beta
        )
        
        self.current_session["frames"].append(asdict(frame))
        self.current_session["diagnoses"].append(result)
        return result
    
    def end_session(self) -> str:
        if not self.current_session["frames"]:
            return "No data for analysis"
        
        last_frame = self.current_session["frames"][-1]
        report = self.ai.generate_draft_report(self.patient_id, last_frame)
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.sessions[session_id] = {
            "patient_id": self.patient_id,
            "session": self.current_session
        }
        self.save_sessions()
        
        self.current_session = {
            "start_time": datetime.now().isoformat(),
            "frames": [],
            "diagnoses": []
        }
        return report


# ==================== VISUALIZATION ====================

def bar(value: int, max_val: int = 100, width: int = 20) -> str:
    filled = min(max(0, round(value / max_val * width)), width)
    return f"[{'#' * filled}{'.' * (width - filled)}]"

def render_frame(frame: SensorFrame, diagnosis: Dict, frame_num: int):
    # State colors
    state_color_map = {
        "Normal": "green", "Recovery": "green",
        "Tension": "yellow", "Fatigue": "yellow",
        "Stress": "red", "Overload": "red", "Arrhythmia (AF)": "magenta"
    }
    state_color = state_color_map.get(diagnosis['state'], "white")
    
    # Color codes
    colors = {
        'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m',
        'magenta': '\033[95m', 'cyan': '\033[96m', 'white': '\033[97m', 'reset': '\033[0m'
    }
    
    print("\033[2J\033[H", end="")
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           📊 DIGITAL DOCTOR - TELEMETRY                     ║
╠══════════════════════════════════════════════════════════════╣
║  ❤️  PULSE:    {bar(frame.pulse, 200)} {frame.pulse:>3} BPM                       ║
║  📈  RHYTHM:   {frame.rhythm:<12}                                   ║
║  💪  EMG:      {bar(frame.emg)} {frame.emg:>3}%                         ║
║  🧠  ALPHA:    {bar(frame.alpha)} {frame.alpha:>3}%                         ║
║  ⚡  BETA:     {bar(frame.beta)} {frame.beta:>3}%                         ║
╠══════════════════════════════════════════════════════════════╣
║  🤖 AI DIAGNOSIS:                                            ║
║  → State: {colors.get(state_color, '')}{diagnosis['state']}{colors['reset']}                           ║
║  → Confidence: {diagnosis['confidence']*100:.0f}%                                  ║
╠══════════════════════════════════════════════════════════════╣
║  📦 Frame #{frame_num}  |  ⏱️  {datetime.now().strftime('%H:%M:%S')}
╚══════════════════════════════════════════════════════════════╝

Commands: q - quit, s - save, r - report, STATS - send to ESP
""")


# ==================== MAIN LOOP ====================

def udp_listener(server: DrHouseServer):
    """Listen to ESP32, process data and send to AI"""
    global bpm, stress, muscle, alpha_ratio, beta_ratio, rhythm, pulse_history
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', UDP_SEND_PORT))
    sock.settimeout(0.5)
    print(f"Listening for ESP on port {UDP_SEND_PORT}...")
    
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
                
                # Process signals
                new_bpm = calculate_bpm(pulse_raw)
                if new_bpm > 0:
                    bpm = new_bpm
                    pulse_history.append(bpm)
                
                stress = calculate_stress(gsr_raw)
                muscle = calculate_muscle(emg_raw)
                alpha_ratio, beta_ratio = calculate_eeg_rhythms(eeg_raw)
                rhythm = detect_rhythm_type(bpm, list(pulse_history))
                
                # Create frame for AI
                frame = SensorFrame(
                    pulse=int(bpm) if bpm > 0 else 70,
                    rhythm=rhythm,
                    emg=muscle,
                    alpha=alpha_ratio,
                    beta=beta_ratio,
                    ts=time.time()
                )
                
                frame_count += 1
                diagnosis = server.process_frame(frame)

                frames_buffer.append(asdict(frame))

                if len(frames_buffer) >= BATCH_SIZE:

                    send_to_server(frames_buffer.copy())

                    frames_buffer.clear()
                
                # Display
                render_frame(frame, diagnosis, frame_count)
                
                # Debug output
                var = max(pulse_history)-min(pulse_history) if pulse_history else 0
                print(f"\nRaw: P={pulse_raw} EMG={emg_raw} EEG={eeg_raw} GSR={gsr_raw}")
                print(f"Debug: BPM={bpm:.0f}, Rhythm={rhythm}, Variability={var:.0f}")
                
                # Send stats to ESP
                now = time.time()

                if now - last_send_time >= send_interval:

                    send_stats_to_esp(bpm, stress, muscle)

                    frame_data = {
                        "pulse": int(bpm) if bpm > 0 else 70,
                        "rhythm": rhythm,
                        "emg": muscle,
                        "alpha": alpha_ratio,
                        "beta": beta_ratio
                    }

                    frames_buffer.append(frame_data)

                    print(f"[BUFFER] {len(frames_buffer)}/{BATCH_SIZE}")

                    if len(frames_buffer) >= BATCH_SIZE:

                        send_to_server(frames_buffer)

                        frames_buffer.clear()

                    last_send_time = now
                
            except socket.timeout:
                pass
            except KeyboardInterrupt:
                break
                
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        sock.close()


def console_handler(server: DrHouseServer):
    """Handle console commands"""
    while True:
        cmd = input("\n[CMD] (ALL, PLS, EMG, EEG, GSR, STATS, S, R, Q): ").strip().upper()
        
        if cmd == "Q":
            save = input("Save session? (y/n): ").lower()
            if save == 'y':
                server.save_sessions()
            print("Goodbye!")
            break
        
        elif cmd == "S":
            server.save_sessions()
            print("Session saved")
        
        elif cmd == "R":
            report = server.end_session()
            print(f"\nREPORT:\n{report}")
        
        elif cmd in ["ALL", "PLS", "EMG", "EEG", "GSR", "STATS"]:
            send_mode_command(cmd)
        
        else:
            print("Unknown. Available: ALL, PLS, EMG, EEG, GSR, STATS, S, R, Q")


# ==================== START ====================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║        🏥 DrHouse - Digital Doctor (UDP Server) v3.0        ║
    ║        Receiving binary data from ESP32 + AI diagnosis       ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    ESP_IP = input("ESP32 IP address (Enter = 192.168.0.100): ").strip()
    if not ESP_IP:
        ESP_IP = "192.168.0.100"
    
    patient_id = input("Patient ID (Enter for Patient_001): ").strip() or "Patient_001"
    
    server = DrHouseServer(patient_id=patient_id, esp_ip=ESP_IP)
    
    listener_thread = threading.Thread(target=udp_listener, args=(server,), daemon=True)
    listener_thread.start()
    
    console_handler(server)