"""
User Data Manager — Persistent storage & rate limiting untuk multi-user bot.
Menyimpan modal per user dan melakukan rate limiting agar API tidak disalahgunakan.
"""
import json
import os
import time
import threading

USER_DATA_FILE = "user_data.json"
DEFAULT_MODAL = 1_000_000  # Rp 1.000.000

# Rate limit config
MAX_REQUESTS_PER_HOUR = 5
COOLDOWN_SECONDS = 30


class UserDataManager:
    """Thread-safe persistent user data manager."""

    def __init__(self, filepath=USER_DATA_FILE):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.data = self._load()

    # ── Persistence ──────────────────────────────────────────

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.data, f, indent=2)
        except IOError as e:
            print(f"⚠️ Gagal menyimpan user data: {e}")

    def _ensure_user(self, user_id: str):
        if user_id not in self.data:
            self.data[user_id] = {
                "modal": DEFAULT_MODAL,
                "request_timestamps": [],
                "total_analyses": 0,
            }

    # ── Modal Management ─────────────────────────────────────

    def get_modal(self, user_id) -> float:
        uid = str(user_id)
        with self.lock:
            self._ensure_user(uid)
            return self.data[uid].get("modal", DEFAULT_MODAL)

    def set_modal(self, user_id, modal: float):
        uid = str(user_id)
        with self.lock:
            self._ensure_user(uid)
            self.data[uid]["modal"] = modal
            self._save()

    # ── Rate Limiting ────────────────────────────────────────

    def check_rate_limit(self, user_id) -> tuple[bool, str]:
        """
        Cek apakah user boleh melakukan request.
        Returns: (allowed: bool, message: str)
        """
        uid = str(user_id)
        now = time.time()

        with self.lock:
            self._ensure_user(uid)
            timestamps = self.data[uid].get("request_timestamps", [])

            # Bersihkan timestamp yang sudah > 1 jam
            one_hour_ago = now - 3600
            timestamps = [t for t in timestamps if t > one_hour_ago]
            self.data[uid]["request_timestamps"] = timestamps

            # Cek cooldown (30 detik sejak request terakhir)
            if timestamps:
                last_request = max(timestamps)
                elapsed = now - last_request
                if elapsed < COOLDOWN_SECONDS:
                    remaining = int(COOLDOWN_SECONDS - elapsed)
                    return False, (
                        f"⏳ Mohon tunggu {remaining} detik sebelum request berikutnya.\n"
                        f"Cooldown ini mencegah overload pada server."
                    )

            # Cek limit per jam
            if len(timestamps) >= MAX_REQUESTS_PER_HOUR:
                oldest = min(timestamps)
                reset_in = int((oldest + 3600) - now)
                minutes = reset_in // 60
                seconds = reset_in % 60
                return False, (
                    f"🚫 Limit tercapai ({MAX_REQUESTS_PER_HOUR} analisis/jam).\n"
                    f"Reset dalam {minutes} menit {seconds} detik.\n\n"
                    f"Limit ini menjaga kualitas layanan untuk semua pengguna."
                )

            return True, ""

    def record_request(self, user_id):
        """Catat bahwa user melakukan request analisis."""
        uid = str(user_id)
        now = time.time()

        with self.lock:
            self._ensure_user(uid)
            self.data[uid]["request_timestamps"].append(now)
            self.data[uid]["total_analyses"] = (
                self.data[uid].get("total_analyses", 0) + 1
            )
            self._save()

    # ── Statistics ───────────────────────────────────────────

    def get_total_users(self) -> int:
        return len(self.data)

    def get_total_analyses(self) -> int:
        return sum(u.get("total_analyses", 0) for u in self.data.values())

    def get_remaining_requests(self, user_id) -> int:
        uid = str(user_id)
        now = time.time()
        with self.lock:
            self._ensure_user(uid)
            timestamps = self.data[uid].get("request_timestamps", [])
            one_hour_ago = now - 3600
            recent = [t for t in timestamps if t > one_hour_ago]
            return max(0, MAX_REQUESTS_PER_HOUR - len(recent))
