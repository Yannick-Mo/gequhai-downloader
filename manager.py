import os
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal

import threading


class DownloadStatus(Enum):
    PENDING = '\u5f85\u4e0b\u8f7d'
    DOWNLOADING = '\u4e0b\u8f7d\u4e2d'
    SUCCESS = '\u2705 \u5b8c\u6210'
    FAILED = '\u274c \u5931\u8d25'
    DEGRADED = '\u26a0 \u5df2\u964d\u7ea7'


class DownloadTask:
    def __init__(self, song_info: dict):
        self.song_id = song_info['id']
        self.title = song_info['title']
        self.artist = song_info['artist']
        self.play_url = song_info['play_url']
        self.status = DownloadStatus.PENDING
        self.progress = 0.0
        self.speed = ''
        self.error_msg = ''


class DownloadManager(QObject):
    progress_updated = pyqtSignal(int, float, str)
    status_changed = pyqtSignal(int, str)
    log_message = pyqtSignal(str)
    queue_finished = pyqtSignal()
    task_finished = pyqtSignal(int)

    def __init__(self, save_path: str, quark_cookie: str = ''):
        super().__init__()
        self.save_path = save_path
        self.quark_cookie = quark_cookie
        os.makedirs(save_path, exist_ok=True)
        self.queue: list[DownloadTask] = []
        self._running = False
        self._thread: threading.Thread | None = None

    def add_tasks(self, song_list: list[dict]):
        for song in song_list:
            self.queue.append(DownloadTask(song))

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_queue, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_queue(self):
        for idx, task in enumerate(self.queue):
            if not self._running:
                break
            if task.status == DownloadStatus.PENDING:
                self._download_single(idx, task)
        self.queue_finished.emit()

    def _download_single(self, idx: int, task: DownloadTask):
        from gequhai import parse_play_page, get_low_quality_url
        from quark import download_from_quark
        from utils import safe_filename, download_file, get_proxies
        import requests
        import os

        try:
            task.status = DownloadStatus.DOWNLOADING
            self.status_changed.emit(idx, task.status.value)
            self.log_message.emit(f"  ├ 解析页面 {task.play_url}...")
            info = parse_play_page(task.song_id)
            title = info.get('title', task.title)
            artist = info.get('author', task.artist)
            unified_name = safe_filename(f"{title}-{artist}")

            audio_path = None
            degraded = False
            quark_url = info.get('quark_url', '')

            if quark_url:
                self.log_message.emit(f"  \u251c \u89e3\u6790\u5230 Quark \u94fe\u63a5")
                success, path, err = download_from_quark(
                    quark_url, title, self.save_path, self.quark_cookie,
                    lambda p, s: self.progress_updated.emit(idx, p, s)
                )
                if success:
                    audio_path = path
                    self.log_message.emit(f"  \u251c \u2705 Quark \u9ad8\u54c1\u8d28\u4e0b\u8f7d\u5b8c\u6210")
                else:
                    self.log_message.emit(f"  \u251c \u26a0 Quark \u5931\u8d25: {err}\uff0c\u5c1d\u8bd5\u964d\u7ea7")
                    degraded = True

            if not audio_path:
                self.log_message.emit(f"  \u251c \u83b7\u53d6\u4f4e\u54c1\u8d28\u76f4\u94fe...")
                play_id = info.get('play_id', '')
                mp3_type = info.get('mp3_type', 0)
                low_url = get_low_quality_url(play_id, mp3_type)
                if low_url:
                    audio_path = os.path.join(self.save_path, f"{unified_name}.mp3")
                    download_file(low_url, audio_path, progress_callback=lambda p, s: self.progress_updated.emit(idx, p, s))
                    self.log_message.emit(f"  \u251c {'\u26a0 \u5df2\u964d\u7ea7\u4e3a\u4f4e\u54c1\u8d28' if degraded else '\u2705 \u4e0b\u8f7d\u5b8c\u6210'}")
                else:
                    raise Exception("\u6240\u6709\u4e0b\u8f7d\u65b9\u5f0f\u5747\u5931\u8d25")

            if audio_path:
                ext = os.path.splitext(audio_path)[1]
                final_audio = os.path.join(self.save_path, f"{unified_name}{ext}")
                if audio_path != final_audio:
                    os.rename(audio_path, final_audio)

            lrc_text = info.get('lrc_text', '')
            if lrc_text:
                lrc_path = os.path.join(self.save_path, f"{unified_name}.lrc")
                with open(lrc_path, 'w', encoding='utf-8') as f:
                    f.write(lrc_text)
                self.log_message.emit(f"  \u251c \u2705 \u6b4c\u8bcd\u5df2\u4fdd\u5b58")
            else:
                self.log_message.emit(f"  \u251c \u26a0 \u672a\u627e\u5230\u6b4c\u8bcd")

            cover_url = info.get('cover_url', '')
            if cover_url:
                cover_path = os.path.join(self.save_path, f"{unified_name}.jpg")
                resp = requests.get(cover_url, timeout=15, proxies=get_proxies())
                if resp.ok:
                    with open(cover_path, 'wb') as f:
                        f.write(resp.content)
                    self.log_message.emit(f"  \u251c \u2705 \u5c01\u9762\u5df2\u4fdd\u5b58")
                else:
                    self.log_message.emit(f"  \u251c \u26a0 \u5c01\u9762\u4e0b\u8f7d\u5931\u8d25 (HTTP {resp.status_code})")
            else:
                self.log_message.emit(f"  \u251c \u26a0 \u672a\u627e\u5230\u5c01\u9762")

            task.status = DownloadStatus.DEGRADED if degraded else DownloadStatus.SUCCESS
            self.status_changed.emit(idx, task.status.value)
            self.log_message.emit(f"  \u2705 \u5b8c\u6210: {unified_name}")

        except Exception as e:
            task.status = DownloadStatus.FAILED
            task.error_msg = str(e)
            self.status_changed.emit(idx, task.status.value)
            self.log_message.emit(f"  \u274c \u5931\u8d25: {str(e)}")
        finally:
            self.task_finished.emit(idx)
