# history.py (English)

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import secrets
import string
import logging
import copy

from .logger import setup_logger

DEFAULT_HISTORY: Dict[str, Any] = {"version": 1, "batches": []}
_logger = logging.getLogger("File_Organizer")

def parent_dir(path: Path) -> None:
    """Creates the parent directory for path if it does not exist.

    Args:
        path (Path): Target path. 
        
    Raises:
        OSError: Only if it is not possible to create the parent directory due to permissions or paths.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

def generate_batch_id(prefix: str= "") -> str:
    """Generates a unique ID to make it readable. 
    
    The ID consists of a format by date and a randomly created suffix: ``YYYYMMDD-HHMMSSZ-XXXXX`
    
    Args:
        prefix (str, optional): Prefix for the ID. Defaults to "".

    Returns:
        str: Unique batch ID. 
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    alphabet = string.ascii_uppercase + string.digits
    rand = "".join(secrets.choice(alphabet) for _ in range(5))
    core = f"{ts}-{rand}"
    norm = prefix.strip("-") if prefix else ""
    return f"{norm}-{core}" if norm else core

def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Writes JSON atomically.
    
    Args:
        path (Path): Destination path for the JSON file.
        data (Dict[str, Any]): Structure to serialize. 

    Raises:
        ValueError: If data is not a dictionary. 
        OSError: If an I/O error occurs when creating or replacing the file. 
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid data: a dict was expected.")
    path = Path(path)
    parent_dir(path)
    tmp_name = f"{path.name}.tmp-{secrets.token_hex(4)}"
    tmp_path = path.with_name(tmp_name)
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    with tmp_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(json_text)
        file.flush()
        os.fsync(file.fileno())

    os.replace(tmp_path, path)
    
def load_history(path: Path) -> Dict[str, Any]:
    """Loads a history. If it does not exist or is invalid returns a default history.

    Args:
        path (Path): Path to the history.json file.

    Returns:
        Dict[str, Any]: Structure of the history. 
    """
    p = Path(path)
    try:
        if not p.exists():
            _logger.info(f"history.json does not exist, creating a new one in: {p}")
            atomic_write_json(p, DEFAULT_HISTORY)
            return copy.deepcopy(DEFAULT_HISTORY)

        raw = p.read_text(encoding="utf-8").strip()
        if not raw:
            _logger.warning("history.json is empty; using defaults.")
            return copy.deepcopy(DEFAULT_HISTORY)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            _logger.error(f"history.json corrupted ({p}): {e}; using defaults.")
            return copy.deepcopy(DEFAULT_HISTORY)

        if not isinstance(data, dict):
            _logger.warning("history.json is not a dict; using defaults.")
            return copy.deepcopy(DEFAULT_HISTORY)
        if "version" not in data or not isinstance(data["version"], int):
            data["version"] = DEFAULT_HISTORY["version"]
        if "batches" not in data or not isinstance(data["batches"], list):
            data["batches"] = []

        return copy.deepcopy(data)

    except OSError as e:
        _logger.error(f"Could not read history.json ({p}): {e}; using defaults.")
        return copy.deepcopy(DEFAULT_HISTORY)

def save_history(path: Path, data: Dict[str, Any]) -> None: 
    """Saves the history using atomic write.
    
    Args:
        path (Path): Destination path of the history.json file.
        data (Dict[str, Any]): Complete structure to persist. 
        
    Raises: 
        ValueError: If data is not a dictionary. 
        OSError: If an I/O error occurs when creating or replacing the file. 
    """
    try:
        atomic_write_json(path, data)
        _logger.info(f"history.json saved: {path}")
    except Exception as e:
        _logger.error(f"Error saving history.json: {e}")
        raise

def to_jsonable(obj: Any) -> Any:
    """Converts non-serializable objects to JSON types."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj

def append_batch(path: Path, batch_id: str, record: Dict[str, Any]) -> None:
    """Adds a batch to the history.json file safely. Normalizes the record, validates fields,
    and adds to batches. 

    Args:
        path (Path): Path to the history.json file.
        batch_id (str): Batch ID. 
        record (Dict[str, Any]): Total record of the batch: 
            - timestamp: str. 
            - command: str.
            - source_dir: str | Path.
            - dest_dir: str | Path.
            - plan: List.
            - stats: Dict.

    Raises:
        ValueError: In case the ID is invalid.
        OSError: If an I/O error occurs when saving the history.
    """
    if not batch_id or not isinstance(batch_id, str):
        raise ValueError("invalid batch_id")

    needed = ["timestamp", "command", "source_dir", "dest_dir", "plan", "stats"]
    missing = [k for k in needed if k not in record]
    if "timestamp" in missing and "created_at" in record:
        missing.remove("timestamp")
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    rec: Dict[str, Any] = dict(record)

    if "created_at" not in rec:
        ts = rec.get("timestamp")
        if isinstance(ts, str) and ts.strip():
            rec["created_at"] = ts
        else:
            rec["created_at"] = (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )

    plan = rec.get("plan")
    stats = rec.get("stats")
    if not isinstance(plan, list):
        raise ValueError("Invalid plan. A list is required.")
    if not isinstance(stats, dict):
        raise ValueError("Invalid stats. A dictionary is required.")
    if "source_dir" in rec and isinstance(rec["source_dir"], Path):
        rec["source_dir"] = str(rec["source_dir"])
    if "dest_dir" in rec and isinstance(rec["dest_dir"], Path):
        rec["dest_dir"] = str(rec["dest_dir"])
    rec["plan"] = to_jsonable(plan)
    rec["stats"] = to_jsonable(stats)
    hist = load_history(path)
    if "batches" not in hist or not isinstance(hist["batches"], list):
        hist["batches"] = []

    batch_record: Dict[str, Any] = {"batch_id": batch_id, **rec}
    hist["batches"].append(batch_record)
    save_history(path, hist)
    _logger.info(f"Batch added to history: {batch_id}")

def get_last_batch_id(path: Path, command: Optional[str] = None) -> Optional[str]:
    """Gets the ID of the last batch, using a timestamp.

    Args:
        path (Path): Path to the history.json file.
        command (str | None, optional): Only consider batches with a matching command (must be indicated). Defaults to None.

    Returns:
        Optional[str]: The most recent ID according to time. 
    """
    def _parse_ts(ts: Any) -> float:
        if not isinstance(ts, str) or not ts.strip():
            return 0.0
        s = ts.strip()
        try:
            if s.endswith("Z"):
                dt = datetime.fromisoformat(s[:-1] + "+00:00")
            else:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            try:
                dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                return 0.0

    hist = load_history(path)
    batches = hist.get("batches")
    if not isinstance(batches, list) or not batches:
        return None

    cand: List[Tuple[str, float]] = []
    for rec in batches:
        if not isinstance(rec, dict):
            continue
        if command:
            cmd = rec.get("command")
            if not isinstance(cmd, str) or cmd.lower() != command.lower():
                continue
        bid = rec.get("batch_id")
        if not isinstance(bid, str) or not bid:
            continue
        ts = rec.get("created_at") or rec.get("timestamp")
        cand.append((bid, _parse_ts(ts)))

    if not cand:
        return None

    cand.sort(key=lambda x: x[1], reverse=True)
    return cand[0][0]
