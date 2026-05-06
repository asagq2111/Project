import requests
import json

data = {
    "user_id": 123,
    "pulse": 96,
    "rhythm": "синусовый",
    "emg": 100,
    "alpha": 46,
    "beta": 54
}

response = requests.post("http://127.0.0.1:5000/upload", json=data)
print(response.json())