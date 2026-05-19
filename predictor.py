import os
import logging
from doctor_ai import InteractiveDoctorAI

logger = logging.getLogger(__name__)

ai = InteractiveDoctorAI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_file = os.path.join(BASE_DIR, "ai_model.pkl")
if os.path.exists(model_file):
    ai.load(model_file)
    logger.info("AI loaded: %d examples", len(ai.X_train))
else:
    logger.warning("Model file not found. Using base model.")


def analyze(pulse, rhythm, emg, alpha, beta):
    result = ai.predict(pulse, rhythm, emg, alpha, beta)
    return {
        "state": result["state"],
        "confidence": result["confidence"],
        "all_probabilities": result.get("all_probabilities", {}),
    }


def get_diagnosis_text(pulse, rhythm, emg, alpha, beta):
    result = analyze(pulse, rhythm, emg, alpha, beta)
    confidence_pct = result["confidence"] * 100

    if confidence_pct < 50:
        warning = "\nLow model confidence. Doctor review required."
    else:
        warning = ""

    return f"Diagnosis: {result['state']} (confidence: {confidence_pct:.1f}%){warning}"


def teach_model(pulse, rhythm, emg, alpha, beta, correct_state):
    success = ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
    if success:
        ai.save(model_file)
    return success


def get_statistics():
    return {
        "total_examples": len(ai.X_train),
        "states": ai.STATES,
        "is_fitted": ai.is_fitted,
    }
