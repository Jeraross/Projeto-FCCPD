import json
from pathlib import Path
from typing import Any


def load_data(data_file: str, seed_file: str | None = None) -> list[dict[str, Any]]:
    path = Path(data_file)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if seed_file and Path(seed_file).exists():
        with open(seed_file, "r", encoding="utf-8") as f:
            seed = json.load(f)
    else:
        seed = []

    save_data(data_file, seed)
    return seed


def save_data(data_file: str, data: list[dict[str, Any]]) -> None:
    path = Path(data_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
