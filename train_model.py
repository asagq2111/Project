from Prikolchik import InteractiveDoctorAI

# Создаем НОВУЮ модель
ai = InteractiveDoctorAI()

# =========================
# NORMAL
# =========================

for _ in range(40):
    ai.teach(72, "синусовый", 12, 65, 30, "Normal")
    ai.teach(75, "синусовый", 15, 60, 35, "Normal")
    ai.teach(78, "синусовый", 10, 70, 25, "Normal")

# =========================
# STRESS
# =========================

for _ in range(80):
    ai.teach(80, "синусовый", 50, 30, 70, "Stress")
    ai.teach(82, "синусовый", 55, 28, 72, "Stress")
    ai.teach(78, "синусовый", 48, 32, 68, "Stress")
    ai.teach(85, "синусовый", 60, 25, 75, "Stress")
    ai.teach(88, "синусовый", 62, 20, 80, "Stress")

# =========================
# ARRHYTHMIA
# =========================

for _ in range(20):
    ai.teach(150, "аритмичный", 35, 30, 45, "Arrhythmia")
    ai.teach(160, "аритмичный", 40, 25, 50, "Arrhythmia")

# =========================

ai.save("ai_model.pkl")

print("✅ Новая модель обучена")
print("📊 Примеров:", len(ai.X_train))