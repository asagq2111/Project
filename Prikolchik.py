#!/usr/bin/env python3
"""
interactive_ai.py - ИИ-доктор для диагностики по показателям
"""

import numpy as np
import os
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pickle

class InteractiveDoctorAI:
    """
    ИИ-доктор - ставит диагноз по показателям пульс, ЭМГ, ЭЭГ
    """
    
    STATES = [
        "Normal",
        "Tension",  
        "Fatigue",
        "Recovery",
        "Stress",
        "Overload",
        "Arrhythmia"
    ]
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.X_train = []
        self.y_train = []
        self.is_fitted = False
        self.training_history = []
        
        self._load_base_knowledge()
        
    def _load_base_knowledge(self):
        """Загружает медицинские правила из PDF"""
        
        base_examples = [
            (72, "sinus", 12, 65, 30, "Normal"),
            (75, "sinus", 15, 70, 35, "Normal"),
            (80, "sinus", 10, 60, 25, "Normal"),
            (85, "sinus", 45, 40, 50, "Tension"),
            (90, "sinus", 50, 35, 55, "Tension"),
            (88, "sinus", 40, 45, 45, "Tension"),
            (78, "sinus", 25, 40, 30, "Fatigue"),
            (82, "sinus", 30, 35, 35, "Fatigue"),
            (75, "sinus", 20, 45, 25, "Fatigue"),
            (68, "sinus", 12, 65, 30, "Recovery"),
            (65, "sinus", 10, 70, 25, "Recovery"),
            (70, "sinus", 15, 60, 35, "Recovery"),
            (100, "sinus", 70, 20, 75, "Stress"),
            (105, "sinus", 75, 15, 80, "Stress"),
            (95, "sinus", 65, 25, 70, "Stress"),
            (105, "sinus", 90, 10, 90, "Overload"),
            (110, "sinus", 95, 5, 95, "Overload"),
            (100, "sinus", 85, 15, 85, "Overload"),
            (150, "arrhythmic", 35, 30, 45, "Arrhythmia"),
            (160, "arrhythmic", 40, 25, 50, "Arrhythmia"),
            (140, "arrhythmic", 30, 35, 40, "Arrhythmia"),
        ]
        
        for pulse, rhythm, emg, alpha, beta, state in base_examples:
            rhythm_val = 1 if rhythm in ["sinus", "синусовый"] else 0
            self.X_train.append([pulse, rhythm_val, emg, alpha, beta])
            self.y_train.append(self.STATES.index(state))
        
        self._train_model()
        print(f"📚 Загружено {len(base_examples)} медицинских правил из PDF")
    
    def _train_model(self):
        if len(self.X_train) < 3:
            return
        
        X = np.array(self.X_train)
        y = np.array(self.y_train)
        
        X_scaled = self.scaler.fit_transform(X)
        
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            class_weight='balanced',
            random_state=42
        )
        self.model.fit(X_scaled, y)
        self.is_fitted = True
        
        predictions = self.model.predict(X_scaled)
        accuracy = np.mean(predictions == y)
        
        self.training_history.append({
            'timestamp': datetime.now(),
            'samples': len(self.X_train),
            'accuracy': accuracy
        })
        
        return accuracy
    
    def predict(self, pulse, rhythm, emg, alpha, beta):
        """Предсказывает состояние"""
        if not self.is_fitted or self.model is None:
            return {"state": "Недостаточно данных", "confidence": 0, "need_training": True}
        
        rhythm_val = 1 if rhythm.lower() in ["sinus", "синусовый"] else 0
        features = np.array([[pulse, rhythm_val, emg, alpha, beta]])
        features_scaled = self.scaler.transform(features)
        
        probabilities = self.model.predict_proba(features_scaled)[0]
        predicted_class = np.argmax(probabilities)
        confidence = max(probabilities)
        
        return {
            "state": self.STATES[predicted_class],
            "confidence": confidence,
            "all_probabilities": dict(zip(self.STATES, probabilities))
        }
    
    def teach(self, pulse, rhythm, emg, alpha, beta, correct_state):
        """ОБУЧЕНИЕ! Врач говорит правильный ответ"""
        if correct_state not in self.STATES:
            print(f"❌ Неизвестное состояние: {correct_state}")
            return False
        
        rhythm_val = 1 if rhythm.lower() in ["sinus", "синусовый"] else 0
        self.X_train.append([pulse, rhythm_val, emg, alpha, beta])
        self.y_train.append(self.STATES.index(correct_state))
        
        accuracy = self._train_model()
        
        print(f"✅ ИИ запомнил: {correct_state}")
        print(f"📊 Точность: {accuracy*100:.1f}% на {len(self.X_train)} примерах")
        
        return True
    

    # ↓↓↓ ВСТАВЬ НОВЫЙ МЕТОД ЗДЕСЬ ↓↓↓
    def generate_synthetic_data(self, count=100):
        import random
        
        templates = {
            "Normal": {"pulse": (60, 90), "rhythm": "sinus", "emg": (5, 25), "alpha": (50, 80), "beta": (20, 40)},
            "Tension": {"pulse": (80, 95), "rhythm": "sinus", "emg": (35, 60), "alpha": (30, 50), "beta": (40, 65)},
            "Fatigue": {"pulse": (70, 85), "rhythm": "sinus", "emg": (15, 40), "alpha": (35, 55), "beta": (25, 45)},
            "Recovery": {"pulse": (60, 75), "rhythm": "sinus", "emg": (8, 20), "alpha": (55, 80), "beta": (20, 35)},
            "Stress": {"pulse": (90, 110), "rhythm": "sinus", "emg": (55, 80), "alpha": (15, 35), "beta": (60, 85)},
            "Overload": {"pulse": (95, 115), "rhythm": "sinus", "emg": (75, 95), "alpha": (5, 20), "beta": (80, 95)},
            "Arrhythmia": {"pulse": (120, 170), "rhythm": "arrhythmia", "emg": (25, 55), "alpha": (20, 40), "beta": (35, 60)}
        }
        
        added = 0
        for state, params in templates.items():
            for _ in range(count):
                pulse = random.randint(*params["pulse"])
                rhythm = params["rhythm"]
                emg = random.randint(*params["emg"])
                alpha = random.randint(*params["alpha"])
                beta = random.randint(*params["beta"])
                
                total = alpha + beta
                if total > 100:
                    alpha = int(alpha * 100 / total)
                    beta = 100 - alpha
                
                rhythm_val = 1 if rhythm in ["sinus", "синусовый"] else 0
                self.X_train.append([pulse, rhythm_val, emg, alpha, beta])
                self.y_train.append(self.STATES.index(state))
                added += 1
        
        accuracy = self._train_model()
        self.save()
        print(f"✅ Сгенерировано {added} примеров (по {count} на каждое состояние)")
        print(f"📊 Всего примеров: {len(self.X_train)}")
        print(f"🎯 Точность: {accuracy*100:.1f}%")
    # ↑↑↑ КОНЕЦ НОВОГО МЕТОДА ↑↑↑
    
    def save(self, filename="ai_model.pkl"):
        data = {
            'model': self.model,
            'scaler': self.scaler,
            'X_train': self.X_train,
            'y_train': self.y_train,
            'is_fitted': self.is_fitted,
            'training_history': self.training_history
        }
        with open(filename, 'wb') as f:
            pickle.dump(data, f)
        print(f"💾 Модель сохранена в {filename}")
    
    def load(self, filename="ai_model.pkl"):
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                data = pickle.load(f)
            self.model = data['model']
            self.scaler = data['scaler']
            self.X_train = data['X_train']
            self.y_train = data['y_train']
            self.is_fitted = data['is_fitted']
            self.training_history = data['training_history']
            print(f"📀 Загружена модель ({len(self.X_train)} примеров)")
            return True
        return False


def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                 🤖 ИИ-ДОКТОР - ДИАГНОСТИКА                   ║
    ║                                                              ║
    ║  Ставит диагноз по показателям:                             ║
    ║    • Пульс (уд/мин)                                         ║
    ║    • Ритм (синусовый/аритмичный)                            ║
    ║    • ЭМГ (0-100%) - активность мышц                         ║
    ║    • Альфа-ритм (0-100%)                                    ║
    ║    • Бета-ритм (0-100%)                                     ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    ai = InteractiveDoctorAI()
    ai.load()
    
    while True:
        print("\n" + "─"*50)
        print("1. Поставить диагноз")
        print("2. Обучить ИИ (исправить ошибку)")
        print("3. Статистика")
        print("0. Выход")
        print("─"*50)
        
        choice = input("\n👉 Выбор: ").strip()
        
        if choice == '0':
            save = input("Сохранить модель? (y/n): ").lower()
            if save == 'y':
                ai.save()
            print("👋 До свидания!")
            break
        
        elif choice == '1':  # ДИАГНОЗ
            print("\n🏥 ВВЕДИТЕ ПОКАЗАТЕЛИ:")
            try:
                pulse = int(input("   Пульс (уд/мин): "))
                rhythm = input("   Ритм (синусовый/аритмичный): ").strip().lower()
                emg = int(input("   ЭМГ (0-100%): "))
                alpha = int(input("   Альфа-ритм (0-100%): "))
                beta = int(input("   Бета-ритм (0-100%): "))
                
                result = ai.predict(pulse, rhythm, emg, alpha, beta)
                
                print("\n" + "="*40)
                print("🤖 ДИАГНОЗ:")
                print(f"   ➤ Состояние: {result['state']}")
                print(f"   ➤ Уверенность: {result['confidence']*100:.1f}%")
                
                if result['confidence'] < 0.5:
                    print("   ⚠️ Низкая уверенность - нужен врач")
                print("="*40)
                
                # Спрашиваем, правильный ли диагноз
                correct = input("\nДиагноз верный? (y/n): ").lower()
                if correct == 'n':
                    print("\n📚 Правильный диагноз:")
                    for i, state in enumerate(ai.STATES, 1):
                        print(f"   {i}. {state}")
                    correct_idx = int(input("   Выберите (1-7): ")) - 1
                    correct_state = ai.STATES[correct_idx]
                    
                    ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
                    ai.save()
                    
            except ValueError as e:
                print(f"❌ Ошибка: {e}")
        
        elif choice == '2':  # ОБУЧЕНИЕ
            print("\n📚 ОБУЧЕНИЕ ИИ")
            try:
                pulse = int(input("   Пульс: "))
                rhythm = input("   Ритм: ").strip().lower()
                emg = int(input("   ЭМГ: "))
                alpha = int(input("   Альфа: "))
                beta = int(input("   Бета: "))
                
                print("\n   Правильный диагноз:")
                for i, state in enumerate(ai.STATES, 1):
                    print(f"   {i}. {state}")
                correct_idx = int(input("   Выберите (1-7): ")) - 1
                correct_state = ai.STATES[correct_idx]
                
                ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
                ai.save()
                
            except ValueError as e:
                print(f"❌ Ошибка: {e}")
        
        elif choice == '3':  # СТАТИСТИКА
            print("\n" + "="*40)
            print("📊 СТАТИСТИКА")
            print("="*40)
            print(f"📚 Примеров в обучении: {len(ai.X_train)}")
            if ai.training_history:
                print(f"🎯 Точность: {ai.training_history[-1]['accuracy']*100:.1f}%")
            print("="*40)
        
        else:
            print("❌ Неверный выбор")


if __name__ == "__main__":
    main()