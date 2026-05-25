import json
import os

STATE_FILE = os.path.expanduser("~/.jobcan_state.json")


class State:
    def __init__(self):
        self._working = self._load()

    def _load(self) -> bool:
        try:
            with open(STATE_FILE) as f:
                return json.load(f).get("working", False)
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    @property
    def is_working(self) -> bool:
        return self._working

    def set_working(self, working: bool):
        self._working = working
        with open(STATE_FILE, "w") as f:
            json.dump({"working": working}, f)
