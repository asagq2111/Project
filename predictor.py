# predictor.py
import os
from Prikolchik import InteractiveDoctorAI

# Создаём один экземпляр ИИ на всё приложение
ai = InteractiveDoctorAI()

# Загружаем сохранённую модель (если есть)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_file = os.path.join(BASE_DIR, "ai_model.pkl")
if os.path.exists(model_file):
    ai.load(model_file)
    print(f"📀 ИИ загружен: {len(ai.X_train)} примеров")
else:
    print("⚠️ Файл модели не найден. Будет использована базовая модель.")

def analyze(pulse, rhythm, emg, alpha, beta):
    """
    Принимает 5 параметров с датчиков.
    Возвращает словарь с диагнозом и уверенностью.
    """
    result = ai.predict(pulse, rhythm, emg, alpha, beta)
    
    return {
        "state": result["state"],
        "confidence": result["confidence"],
        "all_probabilities": result.get("all_probabilities", {})
    }

def get_diagnosis_text(pulse, rhythm, emg, alpha, beta):
    """
    Возвращает готовый текст для отчёта.
    """
    result = analyze(pulse, rhythm, emg, alpha, beta)
    
    confidence_pct = result["confidence"] * 100
    
    if confidence_pct < 50:
        warning = "\n⚠️ Низкая уверенность модели. Требуется проверка врачом."
    else:
        warning = ""
    
    return f"Диагноз: {result['state']} (уверенность: {confidence_pct:.1f}%){warning}"

def teach_model(pulse, rhythm, emg, alpha, beta, correct_state):
    """
    Дообучение модели (вызывается, когда врач исправляет диагноз).
    """
    success = ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
    if success:
        ai.save(model_file)
    return success

def get_statistics():
    """
    Возвращает статистику модели для отладки.
    """
    return {
        "total_examples": len(ai.X_train),
        "states": ai.STATES,
        "is_fitted": ai.is_fitted
    }