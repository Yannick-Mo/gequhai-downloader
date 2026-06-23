import json
import os
import re
import time
import random

import requests

CONFIG_FILE = "config.json"
HISTORY_FILE = "download_history.json"

MAX_RETRIES = 3
RETRY_DELAY = 2

PROXY_KEY = 'proxy'

def get_proxies() -> dict | None:
    cfg = load_config()
    proxy = cfg.get(PROXY_KEY, '')
    if proxy:
        return {'http': proxy, 'https': proxy}
    return None


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_config(config: dict) -> None:
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


def load_history() -> list:
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_history(history: list) -> None:
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)


def retry_request(method: str, url: str, **kwargs) -> requests.Response:
    proxies = get_proxies()
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=15, proxies=proxies, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY + random.uniform(0, 0.5))
    raise last_exc


def download_file(url: str, filepath: str, cookie: str = '',
                  progress_callback=None) -> None:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    if cookie:
        headers['Cookie'] = cookie

    proxies = get_proxies()
    last_exc = None
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=60, proxies=proxies)
            resp.raise_for_status()
            total = int(resp.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                            progress_callback(downloaded / total, f"{speed:.1f} MB/s")
            return
        except Exception as e:
            last_exc = e
            if os.path.exists(filepath):
                os.remove(filepath)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY + random.uniform(0, 0.5))
    raise last_exc
