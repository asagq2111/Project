import logging
from doctor_ai import InteractiveDoctorAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ai = InteractiveDoctorAI()

examples = []

for _ in range(40):
    examples.append((72, "синусовый", 12, 65, 30, "Normal"))
    examples.append((75, "синусовый", 15, 60, 35, "Normal"))
    examples.append((78, "синусовый", 10, 70, 25, "Normal"))

for _ in range(80):
    examples.append((80, "синусовый", 50, 30, 70, "Stress"))
    examples.append((82, "синусовый", 55, 28, 72, "Stress"))
    examples.append((78, "синусовый", 48, 32, 68, "Stress"))
    examples.append((85, "синусовый", 60, 25, 75, "Stress"))
    examples.append((88, "синусовый", 62, 20, 80, "Stress"))

for _ in range(20):
    examples.append((150, "аритмичный", 35, 30, 45, "Arrhythmia"))
    examples.append((160, "аритмичный", 40, 25, 50, "Arrhythmia"))

for pulse, rhythm, emg, alpha, beta, state in examples:
    rhythm_val = 1 if rhythm.lower() in ["sinus", "синусовый"] else 0
    ai.X_train.append([pulse, rhythm_val, emg, alpha, beta])
    ai.y_train.append(ai.STATES.index(state))

ai._train_model()
ai.save("ai_model.pkl")

logger.info("New model trained: %d examples", len(ai.X_train))
