import os
import time
import requests
import urllib3
from notifier import send_message, send_document
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL")
USR = os.getenv("USR")
PASSWORD = os.getenv("PASSWORD")

print(BASE_URL)
print(USR)
print(PASSWORD)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# !!! сюда совать папки для прослушивания !!!
TARGET_FOLDERS = [
    "/Для_студентов_ФИТ_БГТУ/ПРЕПОДАВАТЕЛИ/Мущук/Тестирование программного обеспечения/Лабораторные работы",
    "/Для_студентов_ФИТ_БГТУ/ПРЕПОДАВАТЕЛИ/Нистюк/Облачные системы/Лабораторные работы",
    "/Для_студентов_ФИТ_БГТУ/ПРЕПОДАВАТЕЛИ/Подрез/ИППРПО/Лабораторные работы",
    "/Для_студентов_ФИТ_БГТУ/ПРЕПОДАВАТЕЛИ/Смелов/IV КУРС/СТСР-ИС-4/2026_осень/Лабораторные_рвботы"
]
CHECK_INTERVAL = 300
LOCAL_DOWNLOAD_DIR = "downloads"


class BelstuClient:
    def __init__(self, base_url, user, password):
        self.base_url = base_url
        self.user = user
        self.password = password
        self.session = requests.Session()
        self.session.verify = False
        self.sid = None

    def login(self):
        url = f"{self.base_url}/auth.cgi"
        params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": self.user,
            "passwd": self.password,
            "session": "FileStation",
            "format": "sid",
        }
        res = self.session.get(url, params=params).json()
        if res.get("success"):
            self.sid = res["data"]["sid"]
            return True
        raise RuntimeError(f"Ошибка логина: {res}")

    def download_file(self, remote_path, local_destination_dir):
        os.makedirs(local_destination_dir, exist_ok=True)
        filename = os.path.basename(remote_path)
        local_path = os.path.join(local_destination_dir, filename)

        url = f"{self.base_url}/entry.cgi"
        params = {
            "api": "SYNO.FileStation.Download",
            "version": "2",
            "method": "download",
            "path": remote_path,
            "mode": "open",
            "_sid": self.sid,
        }

        with self.session.get(url, params=params, stream=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return local_path

    def _list_single_folder(self, folder_path):
        url = f"{self.base_url}/entry.cgi"
        params = {
            "api": "SYNO.FileStation.List",
            "version": "2",
            "method": "list",
            "folder_path": folder_path,
            "_sid": self.sid,
            "additional": "time,size",
        }
        res = self.session.get(url, params=params).json()

        if not res.get("success") and res.get("error", {}).get("code") == 119:
            self.login()
            params["_sid"] = self.sid
            res = self.session.get(url, params=params).json()

        if not res.get("success"):
            raise RuntimeError(f"Ошибка получения списка {folder_path}: {res}")

        return res.get("data", {}).get("files", [])

    def list_files_recursive(self, root_folder):
        all_files = {}
        folders_queue = [root_folder]

        while folders_queue:
            current_folder = folders_queue.pop(0)
            try:
                items = self._list_single_folder(current_folder)
                for item in items:
                    if item.get("isdir", False):
                        folders_queue.append(item["path"])
                    else:
                        all_files[item["path"]] = item
            except Exception as e:
                print(f"  [-] Ошибка при обходе подпапки {current_folder}: {e}")

        return all_files

def run_watcher():
    client = BelstuClient(BASE_URL, USR, PASSWORD)
    client.login()
    print("Успешный вход в Synology DSM")

    folder_state = {}

    print("Первоначальное рекурсивное сканирование папок...")
    for root_folder in TARGET_FOLDERS:
        try:
            files_dict = client.list_files_recursive(root_folder)
            folder_state[root_folder] = set(files_dict.keys())
            print(f"  [+] {root_folder} (всего файлов во всех подпапках: {len(folder_state[root_folder])})")
        except Exception as e:
            print(f"  [-] Ошибка при стартовом чтении {root_folder}: {e}")
            folder_state[root_folder] = set()

    print(f"\n[{time.strftime('%X')}] Мониторинг запущен. Опрос каждые {CHECK_INTERVAL} сек.")
    send_message("Мониторинг запущен")

    while True:
        time.sleep(CHECK_INTERVAL)
        for root_folder in TARGET_FOLDERS:
            try:
                current_files = client.list_files_recursive(root_folder)
                known_paths = folder_state.get(root_folder, set())
                new_paths = set(current_files.keys()) - known_paths

                if new_paths:
                    print(f"\n[{time.strftime('%X')}] Новые файлы в ветке: {root_folder}")
                    for remote_path in new_paths:
                        item_info = current_files[remote_path]
                        filename = item_info["name"]

                        rel_subfolder = os.path.dirname(remote_path)[len(root_folder):].strip("/")
                        target_local_dir = os.path.join(LOCAL_DOWNLOAD_DIR, os.path.basename(root_folder), rel_subfolder)

                        print(f"  -> Скачиваем: {remote_path} ...", end="", flush=True)
                        saved_path = client.download_file(remote_path, target_local_dir)
                        print(f" Готово! Сохранено в: {saved_path}")

                        subfolder_hint = f"/{rel_subfolder}" if rel_subfolder else ""
                        send_message(
                            f"🔔 *Новый файл!*\n"
                            f"Курс: `{os.path.basename(root_folder)}`\n"
                            f"Подпапка: `{subfolder_hint or 'корень'}`\n"
                            f"Файл: `{filename}`"
                        )

                        if os.path.exists(saved_path) and os.path.getsize(saved_path) < 50 * 1024 * 1024:
                            send_document(saved_path, caption=f"Новая лаба: {filename}")

                    folder_state[root_folder].update(new_paths)

            except Exception as e:
                print(f"[{time.strftime('%X')}] Ошибка при проверке {root_folder}: {e}")


if __name__ == "__main__":
    run_watcher()
