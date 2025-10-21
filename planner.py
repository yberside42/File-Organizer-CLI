# planner.py (English)

from __future__ import annotations

import logging
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union, Set, Tuple

def discover_files(root: Union[Path, str], recursive: bool = False, follow_symlinks: bool = False) -> List[Path]:
    """Scans a directory and returns a list of found files.

    Args:
        root (Path | str): Folder that will be scanned.
        recursive (bool, optional): If True, includes subdirectories recursively.
        follow_symlinks (bool, optional): If True, follows symbolic links. 

    Returns:
        List[Path]: Returns a list of the found files, if 'root' does not exist returns an empty list.
        
    Notes:
        - Symlinks to files are included only if `follow_symlinks=True`.
        - Files inaccessible due to permissions or other I/O errors are ignored.
        - Directories are not returned, only file paths.
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return []

    files: List[Path] = []
    if recursive:
        for p in root.rglob("*"):
            try:
                if follow_symlinks:
                    if p.is_file():
                        files.append(p)
                else:
                    if not p.is_symlink() and p.is_file():
                        files.append(p)
            except OSError:
                continue
    else:
        try:
            for p in root.iterdir():
                try:
                    if p.is_file() and (follow_symlinks or not p.is_symlink()):
                        files.append(p)
                except OSError:
                    continue
        except OSError:
            return []
    return sorted(files, key=lambda x: str(x).lower())

def parse_size(text: Union[str, int, float]) -> int:
    """Converts a file size value to bytes.

    Args:
        text (str | int | float): Input value. It can be:
            - Positive integer or float (interpreted directly as bytes).
            - String with number and optional unit. Valid examples:
              "100", "512B", "1 KB", "2.5mb", "0.5 GB", "1tb".

    Returns:
        int: Size in bytes (rounded to the nearest integer if the input
        contains decimals).

    Raises:
        ValueError: If the format is invalid, the size is negative or the unit
        is not supported.

    Notes:
        - Supported units: B, KB, MB, GB, TB (case-insensitive).
        - Space between number and unit is allowed (it is normalized).
        - Decimals are accepted (e.g., "1.5KB" → 1536).
        - Negative values are not allowed.
    """
    if isinstance(text, (int, float)):
        if text < 0:
            raise ValueError(f"Invalid size. Negatives are not allowed: {text}")
        return int(text)

    if not isinstance(text, str):
        raise ValueError(f"Invalid size type: {type(text)}")
    s = re.sub(r"\s+", "", text.strip().lower())
    if not s:
        raise ValueError("Invalid size. Empty string.")
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([a-z]*)", s)
    if not m:
        raise ValueError("Invalid size. Unrecognized format.")
    num_str, unit_raw = m.groups()
    try:
        v = float(num_str)
    except ValueError:
        raise ValueError(f"Invalid size. Not a valid number: {text!r}") from None
    if v < 0:
        raise ValueError(f"Invalid size. Negatives are not allowed: {text!r}")

    unit_raw = unit_raw or "b"
    aliases = {
        "b": "b",
        "k": "kb", "kb": "kb", "kib": "kib",
        "m": "mb", "mb": "mb", "mib": "mib",
        "g": "gb", "gb": "gb", "gib": "gib",
        "t": "tb", "tb": "tb", "tib": "tib",
    }
    unit = aliases.get(unit_raw)
    if unit is None:
        raise ValueError("Invalid unit. Use: B, KB, MB, GB, TB, KiB, MiB, GiB, TiB.")

    factors = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }

    bytes_value = int(round(v * factors[unit]))
    return bytes_value
    
def filter_files(files: Iterable[Path], *, only_ext: Optional[str]=None, size_min: Optional[Union[str, int, float]] = None, size_max: Optional[Union[str, int, float]] = None) -> List[Path]:
    """Applies filters to the file list and normalizes.

    Args:
        files (Iterable[Path]): Paths to evaluate. If they are not files they are ignored. 
        only_ext (str, optional): Allowed extensions, separated by commas. 
        size_min (str | int | float, optional): Minimum file size.
        size_max (str | int | float, optional): Maximum file size.

    Returns:
        List[Path]: List of files that pass all filters. 
    
    Raises:
        ValueError: If `size_min` > `size_max` or if sizes are not valid
            (propagated from `parse_size`).
    
     Notes:
        - Extensions are normalized to lowercase and without leading dot.
        - Sizes are interpreted in base 1024.
        - I/O errors (permissions, etc.) are ignored to not interrupt filtering.
    """
    extension_allow: Optional[Set[str]] = None
    if only_ext:
        parts = [e.strip().lower().lstrip(".") for e in only_ext.split(",")]
        extension_allow = {e for e in parts if e} or None

    min_b: Optional[int] = parse_size(size_min) if size_min is not None else None
    max_b: Optional[int] = parse_size(size_max) if size_max is not None else None
    if min_b is not None and max_b is not None and min_b > max_b:
        raise ValueError(f"Invalid size range: size_min ({min_b}) > size_max ({max_b}).")

    out: List[Path] = []
    for p in files:
        try:
            if not p.is_file():
                continue
            if extension_allow is not None:
                ext = p.suffix.lower().lstrip(".")
                if ext not in extension_allow:
                    continue
            st = p.stat()
            sz = int(st.st_size)
            if (min_b is not None and sz < min_b) or (max_b is not None and sz > max_b):
                continue
            out.append(p)
        except OSError:
            continue

    return sorted(out, key=lambda x: str(x).lower())

def classify_by_extension(file_path: Path, cfg: Dict[str, Any]) -> Optional[str]:
    """Classifies a file, assigning it a category according to its extension.

    Args:
        file_path (Path): Path to the file.
        cfg (Dict[str, Any]): Configuration dictionary with keys:
            - "categories": {category:[ext1, ext2, ...]}
            - "behavior": {"othersEnabled": bool}

    Returns:
        Optional[str]: 
            - Category name if there is a match by extension.
            - "others" if there is no match and `othersEnabled` is True and the
              category "others" exists in `categories`.
            - None if there is no valid category available.

    Notes:
        - Files without extension will be assigned to "others" if it is enabled and exists,
          otherwise it will return None.
        - It is assumed that `load_config` already normalized extensions (lowercase,
          without dot, without duplicates).
    """
    ext = file_path.suffix.lower().lstrip(".")
    categories = cfg.get("categories", {}) or {}

    if isinstance(categories, dict):
        exts = categories.get  
        for cat, lst in categories.items():
            if isinstance(lst, list) and ext in lst:
                return cat

    behavior = cfg.get("behavior", {}) or {}
    if behavior.get("othersEnabled", True) and "others" in categories:
        return "others"
    return None

def build_plan(files: List[Path], cfg: Dict[str, Any], root: Path, by_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Builds the organization plan for the list of files. 

    Args:
        files: List of file paths.
        cfg: Loaded configuration. 
        root: Root folder where destination folders will be created.
        by_date: None, "created" or "modified" → subfolders YYYY/MM.

    Returns:
        List of dicts:
            - src: Original Path
            - dst: Destination Path
            - category: str
            - reason: str
    """
    plan: List[Dict[str, Any]] = []

    files_sorted = sorted(files, key=lambda p: str(p).lower())
    categories = cfg.get("categories", {}) or {}
    ext_to_cat: Dict[str, str] = {}
    for cat, lst in categories.items():
        if isinstance(lst, list):
            for e in lst:
                if isinstance(e, str) and e:
                    ext_to_cat[e] = cat

    others_enabled = bool((cfg.get("behavior", {}) or {}).get("othersEnabled", True))
    have_others = "others" in categories

    by_date = by_date if by_date in (None, "created", "modified") else None

    for file_path in files_sorted:
        ext = file_path.suffix.lower().lstrip(".")
        category = ext_to_cat.get(ext)

        reason = "match-extension"
        if not category:
            if others_enabled and have_others:
                category = "others"
                reason = "others"
            else:
                continue

        dest_dir = root / category

        if by_date is not None:
            try:
                st = file_path.stat()
                ts = st.st_ctime if by_date == "created" else st.st_mtime
                dt = datetime.fromtimestamp(ts)
                dest_dir = dest_dir / f"{dt.year:04d}" / f"{dt.month:02d}"
            except OSError:
                pass

        dst_path = dest_dir / file_path.name
        plan.append(
            {
                "src": file_path,
                "dst": dst_path,
                "category": category,
                "reason": reason,
            }
        )

    return plan

def next_incremental_name(dst: Path) -> Path: 
    """Generates a non-existing filename with an incremental suffix. 
    
    If 'dst' does not exist it is returned as is. If it exists, it is added or updated.
        - "file.txt" → "file (2).txt" → "file (3).txt" → …
        
    Args:
        dst (Path): Destination path. 

    Returns:
        Path: Free path that does not exist in the system. 
    """
    if not dst.exists():
        return dst

    stem = dst.stem
    suffix = dst.suffix

    m = re.match(r"^(?P<base>.*?)(?:\s\((?P<num>\d+)\))?$", stem)
    if m and m.group("num"):
        base = m.group("base")
        n = int(m.group("num")) + 1
    else:
        base = stem
        n = 2

    while True:
        candidate = dst.with_name(f"{base} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1

def apply_collision_policy(plan: List[Dict[str, Any]], policy: str = "rename") -> List[Dict[str, Any]]:
    """Applies the collision policy to all entries of the plan 
    
    Gives the option that, when there is a collision it can move, rename or skip. 
        
    Policy:
        - rename: Uses next_incremental_name() to not overwrite.
        - keep-newest: In case a file already exists and is newer than src, then skip;
                       If src is newer uses the increment and does not overwrite. 
        - skip: If it exists in destination, skip. 
    
    Args:
        plan(List[Dict[str, Any]]): Plan entries. 
            - "src" (Path): Source path.
            - "dst" (Path): Destination path.
            - (optional) "notes" (str): previous notes.
    
    Returns: 
        List[Dict[str, Any]]: A new list.
            - "decision" (str): "move" or "skip".
            - "dst_final" (Path): final destination decided.
            - "notes" (str, optional): accumulated notes.
    """
    p = (policy or "rename").lower()
    if p not in {"rename", "keep-newest", "skip"}:
        p = "rename"

    out: List[Dict[str, Any]] = []

    for item in plan:
        src: Path = item["src"]
        dst: Path = item["dst"]
        note = ""
        decision = "move"
        dst_final = dst

        collision = dst.exists()

        if p == "rename":
            if collision:
                dst_final = next_incremental_name(dst)
                note = f"collision: rename -> {dst_final.name}"
        elif p == "keep-newest":
            if collision:
                try:
                    dst_mtime = dst.stat().st_mtime
                    src_mtime = src.stat().st_mtime
                except OSError:
                    decision = "skip"
                    note = "collision: keep-newest (stat error)"
                else:
                    if dst_mtime >= src_mtime:
                        decision = "skip"
                        note = "collision: keep-newest (dst newer or same)"
                    else:
                        dst_final = next_incremental_name(dst)
                        note = f"collision: keep-newest -> rename to {dst_final.name}"
        elif p == "skip":
            if collision:
                decision = "skip"
                note = "collision: skip (dst exists)"

        new_item = dict(item)
        new_item["decision"] = decision
        new_item["dst_final"] = dst_final
        if note:
            prev = item.get("notes")
            new_item["notes"] = (prev + "; " if prev else "") + note
        out.append(new_item)

    return out

def quick_hash(path: Path, *, first_bytes: int = 256 * 1024):
    """Returns a quick signature of the file to be able to detect duplicates.
    
    Args: 
        path (Path): File path.
        first_bytes (int, optrional): Number of initial bytes. Must be > 0.
        
    Returns: 
        Optional: If it could be read returns a tuple. If not returns None.
        
    Raises:
        ValueError: If `first_bytes <= 0`.
    """
    if first_bytes <= 0:
        raise ValueError("Invalid size, must be > 0.")

    try:
        if not path.is_file():
            return None
        st = path.stat()
        size = int(st.st_size)
        h = hashlib.blake2b()
        with path.open("rb") as f:
            chunk = f.read(first_bytes)
            h.update(chunk)
        return (size, h.hexdigest())
    except OSError:
        return None

def full_hash(path: Path, chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Calculates the full hash of the file to check if there are duplicates.
    
    Args: 
        path (Path): File path.
        chunk_size (int, optional): Read block size in bytes.
    
    Returns: 
        Optional[str]: If the file could be read returns a Hexadecimal Digest, if not returns None.
    
    Raises:
        ValueError: If `chunk_size <= 0`.
    """
    if chunk_size <= 0:
        raise ValueError("Invalid size, must be > 0.")

    try:
        if not path.is_file():
            return None
        h = hashlib.blake2b()
        with path.open("rb") as f:
            while True:
                b = f.read(chunk_size)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None

def apply_dedupe_policy(plan: List[Dict[str, Any]], policy: str = "skip") -> List[Dict[str, Any]]:
    """Marks duplicates by content inside the plan and allows deciding its action.
    
    Uses the functions quick_hash and full_hash to be able to configure duplicates.
    
    Policy:
        - skip: subsequent ones remain "skip".
        - link: (preview) notes that hardlink will be used in run.
        - delete: (preview) notes and marks skip (does not perform it). 
        
    Args:
        plan(List[Dict[str, any]]): Plan list.
            - "src" (Path): Source file.
            - "dst" (Path): Destination. 
    
    Returns: 
        List: A new list with items that have: 
            - decision (str): "skip" or "move".
            - duplicate_of (path): src path of the original.
            - notes (str): Accumulated notes describing the decision taken.
            - dst_final (path): Ensured.
    """
    p = (policy or "skip").lower()
    if p not in {"skip", "link", "delete"}:
        p = "skip"

    out: List[Dict[str, Any]] = []

    buckets: Dict[Tuple[int, str], List[int]] = defaultdict(list)
    for idx, item in enumerate(plan):
        sig = quick_hash(item["src"])
        if sig:
            buckets[sig].append(idx)
    duplicate_i: Set[int] = set()
    confirmed_groups: List[List[int]] = []
    for _, idxs in buckets.items():
        if len(idxs) < 2:
            continue
        fh_map: Dict[str, List[int]] = defaultdict(list)
        for i in idxs:
            fh = full_hash(plan[i]["src"])
            if fh:
                fh_map[fh].append(i)
        for dup_idxs in fh_map.values():
            if len(dup_idxs) > 1:
                dup_idxs.sort()
                confirmed_groups.append(dup_idxs)
                duplicate_i.update(dup_idxs[1:])

    for idx, item in enumerate(plan):
        new_item = dict(item)
        notes = str(new_item.get("notes", ""))
        is_dup = idx in duplicate_i

        if is_dup:
            orig_src: Optional[Path] = None
            for grp in confirmed_groups:
                if idx in grp:
                    orig_src = plan[grp[0]]["src"]
                    break
            if p in {"skip", "delete"}:
                new_item["decision"] = "skip"
                extra = "duplicate: delete (preview)" if p == "delete" else "duplicate: skip"
            elif p == "link":
                new_item["decision"] = new_item.get("decision", "move")
                extra = "duplicate: link (preview)"
            else:
                new_item["decision"] = "skip"
                extra = f"duplicate: unknown policy '{p}' -> skip"
            if orig_src is not None:
                new_item["duplicate_of"] = orig_src
            new_item["notes"] = (notes + ("; " if notes else "") + extra)
        else:
            new_item.setdefault("decision", "move")

        new_item.setdefault("dst_final", new_item.get("dst"))
        out.append(new_item)

    return out
                  
def render_plan(plan: List[Dict[str, Any]], logger: logging.Logger, max_rows: int = 50) -> Dict[str, Any]:
    """Renders the whole plan in a table and shows a summary by category.

    Args:
        plan (List[Dict[str, Any]]): List of plan entries. Each item should
            include at least:
              - "src" (Path)
              - "dst" (Path)
              - "category" (str, optional)
              - "decision" (str, optional: "move"|"skip")
              - "dst_final" (Path, optional)
              - "notes" (str, optional)
        logger(logging.Logger): Logger configured to print to console / file.
        max_rows(int, optional): Maximum rows to display in the table.

    Returns:
        A dict with summary metrics:
        {
            "total": int,
            "by_category": dict[str, int],
            "by_decision": Dict[str, int],
            "shown": int
        }
        
    Raises:
        ValueError: If `max_rows < 0`.
    """
    if max_rows < 0:
        raise ValueError("Invalid size. 'max_rows' must be >= 0.")

    total = len(plan)
    if total == 0:
        logger.info("No proposed actions (empty plan).")
        return {"total": 0, "by_category": {}, "by_decision": {}, "shown": 0}

    headers = ["#", "ACTION", "SRC", "→", "DST_FINAL", "CATEGORY", "DECISION", "NOTES"]
    rows: List[List[str]] = []

    for idx, item in enumerate(plan[:max_rows], start=1):
        src = str(item.get("src", ""))
        dst_final = str(item.get("dst_final", item.get("dst", "")))
        category = str(item.get("category", ""))
        decision = str(item.get("decision", "move"))
        notes = str(item.get("notes", ""))
        action = "MOVE"

        rows.append([str(idx), action, src, "→", dst_final, category, decision, notes])

    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    logger.info(header_line)
    logger.info(sep_line)
    for r in rows:
        logger.info("  ".join(r[i].ljust(widths[i]) for i in range(len(headers))))

    shown = len(rows)
    if total > shown:
        logger.info(f"... ({total - shown} more not shown; use filters to narrow)")

    cat_counts = Counter(str(it.get("category", "")) for it in plan)
    dec_counts = Counter(str(it.get("decision", "move")) for it in plan)

    logger.info("Summary by category:")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: (-x[1], x[0])):
        logger.info(f"  {cat}: {cnt}")

    logger.info("Summary by decision:")
    for dec, cnt in sorted(dec_counts.items(), key=lambda x: (-x[1], x[0])):
        logger.info(f"  {dec}: {cnt}")

    logger.info(f"Total proposed actions: {total}")
    return {
        "total": total,
        "by_category": dict(cat_counts),
        "by_decision": dict(dec_counts),
        "shown": shown,
    }

