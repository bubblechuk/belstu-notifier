import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[TG Error] Ошибка отправки сообщения: {e}")


def send_document(file_path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    data = {"chat_id": CHAT_ID, "caption": caption}
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            requests.post(url, data=data, files=files, timeout=60)
    except Exception as e:
        print(f"[TG Error] Ошибка отправки файла: {e}")
