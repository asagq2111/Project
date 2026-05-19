import logging
import random
import numpy as np
import os
import pickle
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class InteractiveDoctorAI:
    STATES = [
        "Норма",
        "Напряжение",
        "Усталость",
        "Восстановление",
        "Стресс",
        "Перегрузка",
        "Аритмия",
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
        base_examples = [
            (72, "sinus", 12, 65, 30, "Норма"),
            (75, "sinus", 15, 70, 35, "Норма"),
            (80, "sinus", 10, 60, 25, "Норма"),
            (85, "sinus", 45, 40, 50, "Напряжение"),
            (90, "sinus", 50, 35, 55, "Напряжение"),
            (88, "sinus", 40, 45, 45, "Напряжение"),
            (78, "sinus", 25, 40, 30, "Усталость"),
            (82, "sinus", 30, 35, 35, "Усталость"),
            (75, "sinus", 20, 45, 25, "Усталость"),
            (68, "sinus", 12, 65, 30, "Восстановление"),
            (65, "sinus", 10, 70, 25, "Восстановление"),
            (70, "sinus", 15, 60, 35, "Восстановление"),
            (100, "sinus", 70, 20, 75, "Стресс"),
            (105, "sinus", 75, 15, 80, "Стресс"),
            (95, "sinus", 65, 25, 70, "Стресс"),
            (105, "sinus", 90, 10, 90, "Перегрузка"),
            (110, "sinus", 95, 5, 95, "Перегрузка"),
            (100, "sinus", 85, 15, 85, "Перегрузка"),
            (150, "arrhythmic", 35, 30, 45, "Аритмия"),
            (160, "arrhythmic", 40, 25, 50, "Аритмия"),
            (140, "arrhythmic", 30, 35, 40, "Аритмия"),
        ]

        for pulse, rhythm, emg, alpha, beta, state in base_examples:
            rhythm_val = 1 if rhythm in ["sinus", "синусовый"] else 0
            self.X_train.append([pulse, rhythm_val, emg, alpha, beta])
            self.y_train.append(self.STATES.index(state))

        self._train_model()
        logger.info("Loaded %d base medical knowledge examples", len(base_examples))

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
            "all_probabilities": dict(zip(self.STATES, probabilities)),
        }

    def teach(self, pulse, rhythm, emg, alpha, beta, correct_state):
        if correct_state not in self.STATES:
            logger.error("Unknown state: %s", correct_state)
            return False

        rhythm_val = 1 if rhythm.lower() in ["sinus", "синусовый"] else 0
        self.X_train.append([pulse, rhythm_val, emg, alpha, beta])
        self.y_train.append(self.STATES.index(correct_state))

        accuracy = self._train_model()

        logger.info("AI learned: %s (accuracy: %.1f%% on %d samples)", correct_state, accuracy * 100, len(self.X_train))

        return True

    def generate_synthetic_data(self, count=100):
        templates = {
            "Норма": {"pulse": (60, 90), "rhythm": "sinus", "emg": (5, 25), "alpha": (50, 80), "beta": (20, 40)},
            "Напряжение": {"pulse": (80, 95), "rhythm": "sinus", "emg": (35, 60), "alpha": (30, 50), "beta": (40, 65)},
            "Усталость": {"pulse": (70, 85), "rhythm": "sinus", "emg": (15, 40), "alpha": (35, 55), "beta": (25, 45)},
            "Восстановление": {"pulse": (60, 75), "rhythm": "sinus", "emg": (8, 20), "alpha": (55, 80), "beta": (20, 35)},
            "Стресс": {"pulse": (90, 110), "rhythm": "sinus", "emg": (55, 80), "alpha": (15, 35), "beta": (60, 85)},
            "Перегрузка": {"pulse": (95, 115), "rhythm": "sinus", "emg": (75, 95), "alpha": (5, 20), "beta": (80, 95)},
            "Аритмия": {"pulse": (120, 170), "rhythm": "arrhythmia", "emg": (25, 55), "alpha": (20, 40), "beta": (35, 60)},
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
        logger.info("Generated %d synthetic examples (%d per state)", added, count)
        logger.info("Total examples: %d, accuracy: %.1f%%", len(self.X_train), accuracy * 100)

    def save(self, filename="ai_model.pkl"):
        data = {
            'model': self.model,
            'scaler': self.scaler,
            'X_train': self.X_train,
            'y_train': self.y_train,
            'is_fitted': self.is_fitted,
            'training_history': self.training_history,
        }
        with open(filename, 'wb') as f:
            pickle.dump(data, f)
        logger.info("Model saved to %s", filename)

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
            logger.info("Loaded model (%d examples)", len(self.X_train))
            return True
        return False


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                 Interactive Doctor AI                        ║
    ║                                                              ║
    ║  Diagnoses based on:                                        ║
    ║    - Pulse (bpm)                                            ║
    ║    - Rhythm (sinus/arrhythmic)                              ║
    ║    - EMG (0-100%) - muscle activity                         ║
    ║    - Alpha rhythm (0-100%)                                  ║
    ║    - Beta rhythm (0-100%)                                   ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    ai = InteractiveDoctorAI()
    ai.load()

    while True:
        print("\n" + "─" * 50)
        print("1. Diagnose")
        print("2. Train AI (correct a mistake)")
        print("3. Statistics")
        print("0. Exit")
        print("─" * 50)

        choice = input("\nChoice: ").strip()

        if choice == '0':
            save = input("Save model? (y/n): ").lower()
            if save == 'y':
                ai.save()
            print("Goodbye!")
            break

        elif choice == '1':
            print("\nEnter parameters:")
            try:
                pulse = int(input("   Pulse (bpm): "))
                rhythm = input("   Rhythm (sinus/arrhythmic): ").strip().lower()
                emg = int(input("   EMG (0-100%): "))
                alpha = int(input("   Alpha (0-100%): "))
                beta = int(input("   Beta (0-100%): "))

                result = ai.predict(pulse, rhythm, emg, alpha, beta)

                print("\n" + "=" * 40)
                print(f"DIAGNOSIS: {result['state']}")
                print(f"Confidence: {result['confidence'] * 100:.1f}%")
                if result['confidence'] < 0.5:
                    print("   Low confidence - doctor review needed")
                print("=" * 40)

                correct = input("\nDiagnosis correct? (y/n): ").lower()
                if correct == 'n':
                    print("\nCorrect diagnosis:")
                    for i, state in enumerate(ai.STATES, 1):
                        print(f"   {i}. {state}")
                    correct_idx = int(input("   Choose (1-7): ")) - 1
                    correct_state = ai.STATES[correct_idx]

                    ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
                    ai.save()

            except ValueError as e:
                print(f"Error: {e}")

        elif choice == '2':
            print("\nTrain AI")
            try:
                pulse = int(input("   Pulse: "))
                rhythm = input("   Rhythm: ").strip().lower()
                emg = int(input("   EMG: "))
                alpha = int(input("   Alpha: "))
                beta = int(input("   Beta: "))

                print("\n   Correct diagnosis:")
                for i, state in enumerate(ai.STATES, 1):
                    print(f"   {i}. {state}")
                correct_idx = int(input("   Choose (1-7): ")) - 1
                correct_state = ai.STATES[correct_idx]

                ai.teach(pulse, rhythm, emg, alpha, beta, correct_state)
                ai.save()

            except ValueError as e:
                print(f"Error: {e}")

        elif choice == '3':
            print("\n" + "=" * 40)
            print("STATISTICS")
            print("=" * 40)
            print(f"Training examples: {len(ai.X_train)}")
            if ai.training_history:
                print(f"Accuracy: {ai.training_history[-1]['accuracy'] * 100:.1f}%")
            print("=" * 40)

        else:
            print("Invalid choice")


if __name__ == "__main__":
    main()
