import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

DEFAULT_PATH = Path("data/users.json")


class Storage:
    """
    JSON-backed storage.
    Data shape:
    {
      "user_id": {
         "channel_id": "...",
         "username": "...",
         "replies_per_day": int,
         "start_date": "YYYY-MM-DD",
         "status": "active"/"pending"/"paused"
      },
      ...
    }
    """

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: dict):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    # ---- Create / modify ----
    def add_user(self,
                 user_id: str,
                 channel_id: str,
                 username: str,
                 replies_per_day: int,
                 status: str = "active",
                 start_date: Optional[str] = None):
        data = self._read()
        data[user_id] = {
            "channel_id": str(channel_id),
            "username": str(username),
            "replies_per_day": int(replies_per_day),
            "start_date": start_date or datetime.utcnow().date().isoformat(),
            "status": status
        }
        self._write(data)

    def set_user(self,
                 discord_id: str,
                 channel_id: Optional[str] = None,
                 username: Optional[str] = None,
                 replies_per_day: Optional[int] = None,
                 start_date: Optional[str] = None,
                 status: Optional[str] = None):
        data = self._read()
        if discord_id not in data:
            # initialize with defaults to ensure consistent shape
            data[discord_id] = {
                "channel_id": "",
                "username": f"user_{discord_id}",
                "replies_per_day": 0,
                "start_date": datetime.utcnow().date().isoformat(),
                "status": "pending"
            }
        if channel_id is not None:
            data[discord_id]["channel_id"] = str(channel_id)
        if username is not None:
            data[discord_id]["username"] = str(username)
        if replies_per_day is not None:
            data[discord_id]["replies_per_day"] = int(replies_per_day)
        if start_date is not None:
            data[discord_id]["start_date"] = start_date
        if status is not None:
            data[discord_id]["status"] = status
        self._write(data)

    # ---- Read helpers ----
    def get_user(self, user_id: str) -> Optional[dict]:
        data = self._read()
        return data.get(user_id)

    def get_user_by_discord_id(
            self,
            discord_id: str) -> Optional[Tuple[str, str, str, int, str, str]]:
        """
        Return a tuple (user_id, channel_id, username, replies_per_day, start_date, status)
        This keeps compatibility with code that expects a 6-value row.
        """
        data = self._read()
        udata = data.get(str(discord_id))
        if not udata:
            return None
        return (str(discord_id), udata.get("channel_id", ""),
                udata.get("username", f"user_{discord_id}"),
                int(udata.get("replies_per_day", 0) or 0),
                udata.get("start_date",
                          datetime.utcnow().date().isoformat()),
                udata.get("status", "pending"))

    def get_user_by_channel(self,
                            channel_id: str) -> Optional[Tuple[str, dict]]:
        data = self._read()
        for uid, udata in data.items():
            if str(udata.get("channel_id")) == str(channel_id):
                return uid, udata
        return None

    # ---- Update / remove ----
    def update_user(self, user_id: str, **kwargs):
        data = self._read()
        if user_id in data:
            data[user_id].update(kwargs)
            self._write(data)

    def update_replies_per_day(self, user_id: str, replies_per_day: int):
        """Convenience method used by /settarget"""
        data = self._read()
        if user_id in data:
            data[user_id]["replies_per_day"] = int(replies_per_day)
            self._write(data)

    def pause_user(self, user_id: str):
        self.set_user(discord_id=user_id, status="paused")

    def resume_user(self, user_id: str):
        self.set_user(discord_id=user_id, status="active")

    def remove_user(self, user_id: str):
        data = self._read()
        if user_id in data:
            del data[user_id]
            self._write(data)

    # ---- Listing ----
    def list_users(self) -> List[Tuple[str, str, str, int, str, str]]:
        data = self._read()
        out = []
        for uid, udata in data.items():
            out.append(
                (uid, udata.get("channel_id"), udata.get("username"),
                 int(udata.get("replies_per_day", 0)
                     or 0), udata.get("start_date"), udata.get("status")))
        return out

    # ---- raw load/save (compat) ----
    def load_users(self) -> dict:
        return self._read()

    def save_users(self, users: dict):
        self._write(users)


# Compatibility helpers for older code
_default_storage = Storage(DEFAULT_PATH)


def load_users() -> dict:
    return _default_storage.load_users()


def save_users(users: dict):
    return _default_storage.save_users(users)


def get_storage_instance(path: str | Path = DEFAULT_PATH) -> Storage:
    return Storage(path)
