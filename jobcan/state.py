import json
import os
from datetime import date

STATE_FILE = os.path.expanduser("~/.jobcan_state.json")


class State:
    def __init__(self):
        self._working = self._load()

    def _load(self) -> bool:
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            working = data.get("working", False)
            # 出勤中だが保存日が今日でなければ日をまたいだとみなしリセット
            if working:
                saved_date = data.get("date", "")
                if saved_date != date.today().isoformat():
                    print(f"[state] 日付変更を検出({saved_date} → {date.today()})。出勤状態をリセット", flush=True)
                    self._save(False)
                    return False
            return working
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    @property
    def is_working(self) -> bool:
        return self._working

    def reset_if_stale(self) -> bool:
        """出勤中だが保存日が今日でなければリセット。リセットしたら True を返す。"""
        if not self._working:
            return False
        try:
            with open(STATE_FILE) as f:
                saved_date = json.load(f).get("date", "")
        except (FileNotFoundError, json.JSONDecodeError):
            saved_date = ""
        if saved_date != date.today().isoformat():
            print(f"[state] 日付変更を検出({saved_date} → {date.today()})。出勤状態をリセット", flush=True)
            self.set_working(False)
            return True
        return False

    def set_working(self, working: bool):
        self._working = working
        self._save(working)

    def _save(self, working: bool):
        data = {"working": working}
        if working:
            data["date"] = date.today().isoformat()
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
