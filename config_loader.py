# config_loader.py (English)

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

import json
import copy


DEFAULT_CONFIG: dict[str, Any] = {
    "categories": {
        "media": ["jpg","jpeg","png","gif","webp","svg","heic","mp4","mkv","avi","mov","mp3","wav","flac","m4a"],
        "docs": ["pdf","doc","docx","xls","xlsx","ppt","pptx","txt","md","rtf","csv"] ,
        "code": ["py","js","ts","html","css","json","yml","yaml","sql","sh","bat","ps1"],
        "archives": ["zip","rar","7z","tar","gz","bz2"],
        "executables": ["exe","msi","dmg","app","bin"],
        "others": []
        },
    "behavior": {
        "collision": "rename",
        "dedupe": "skip",
        "followSymlinks": False,
        "othersEnabled": True
    }
}

def _unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def load_config(config_path):
    """Loads and normalizes the File Organizer configuration from a JSON file.
    
    If this file does not exist, returns a copy of 'DEFAULT_CONFIG'.
    It does not raise any exception to not interrupt the program. 

    Args:
        config_path (Path): Path to the config.json file

    Returns:
        Dict[str, Any]: Dictionary with the form:
            {
                "categories": Dict[str, List[str]],
                "behavior": {
                    "collision": Literal["rename", "keep-newest", "skip"],
                    "dedupe": Literal["skip", "link", "delete"],
                    "followSymlinks": bool,
                    "othersEnabled": bool,
                }
            }

    Notes:
        - If the file does not exist or there are read/parse errors, default values are returned.
        - Extensions in `categories` are **normalized**:
            * to lowercase,
            * the leading dot is removed (".pdf" → "pdf"),
            * spaces are trimmed,
            * empty entries are discarded.
        - Unknown keys are ignored; only expected keys are combined.
        - No exceptions are raised: any error is treated as “use defaults”.
          This avoids breaking the CLI, but can hide faulty configurations.
    """
    path = Path(config_path)
    cfg: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)

    if not path.exists():
        return cfg

    try:
        raw: Dict[str, Any]
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return cfg
    
    categories = raw.get("categories")
    if isinstance(categories, dict):
        cleaned: Dict[str, List[str]] = {}
        for cat, exts in categories.items():
            if not isinstance(cat, str) or not isinstance(exts, list):
                continue
            norm: List[str] = []
            for e in exts:
                if not isinstance(e, str):
                    continue
                s = e.lower().strip()
                if s.startswith("."):
                    s = s[1:]
                if s:
                    norm.append(s)
            cleaned[cat.strip().lower()] = _unique_preserve_order(norm)

        if cleaned:
            cfg["categories"] = cleaned

    behavior = raw.get("behavior")
    if isinstance(behavior, dict):
        beh = cfg["behavior"].copy()
        if behavior.get("collision") in {"rename", "keep-newest", "skip"}:
            beh["collision"] = behavior["collision"]
        if behavior.get("dedupe") in {"skip", "link", "delete"}:
            beh["dedupe"] = behavior["dedupe"]
        if isinstance(behavior.get("followSymlinks"), bool):
            beh["followSymlinks"] = behavior["followSymlinks"]
        if isinstance(behavior.get("othersEnabled"), bool):
            beh["othersEnabled"] = behavior["othersEnabled"]
        cfg["behavior"] = beh

    return cfg
