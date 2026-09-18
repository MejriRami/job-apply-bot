import json

from . import config


def load_profile(path: str = config.PROFILE_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
