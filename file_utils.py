# file_utils.py (English)

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple
import re
import shutil
import hashlib


def compute_file_hash(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    """Calculates the hash using SHA-256 of a file reading by blocks. 

    Args:
        path (Path): Path of the file to hash. 
        block_size (int, optional): Read block size (in bytes). Defaults to 8*1024*1024.

    Raises:
        IsADirectoryError, FileNotFoundError, PermissionError, OSError: 
            If the file does not exist or presents errors to be read or format issues. 

    Returns:
        str: Returns the hexdigest.
    """
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"The path is a directory: {path}")

    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(block_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def next_name(dest: Path, *, max_tries: int = 9999) -> Path: 
    """Returns a free Path in destination, applies an incremental suffix if the file already exists.

    Args:
        dest (Path): Desired destination path
        max_tries (int, optional): Attempts available to avoid infinite loops. Defaults to 9999.

    Raises:
        ValueError: If attempts are less than 1. 
        FileExistsError: If there is no free name within the attempts. 

    Returns:
        Path: Available path that does not exist on disk. 
    """
    if max_tries < 1: 
        raise ValueError("max_tries must be >= 1")
    if not dest.exists():
        return dest
    
    parent = dest.parent
    stem = dest.stem
    suffix = dest.suffix
    
    m = re.search(r" \((\d+)\)$", stem)
    start_name = int(m.group(1)) + 1 if m else 1
    base_stem = stem[:m.start()] if m else stem
    
    for name in range(start_name, start_name + max_tries):
        cand = parent / f"{base_stem} ({name}){suffix}"
        if not cand.exists():
            return cand
        
    raise FileExistsError(f"No free name for {dest} after {max_tries} attempts")

def apply_policies_move(src: Path, dest: Path, *, collision_policy: str, dedupe_by_hash: bool, hash_cache: Optional[Dict[str, str]] = None, logger=None) -> Tuple[str, Path]: 
    """Applies collision and duplicate policies, executes the action and returns it and the destination. 

    Args:
        src (Path): Path to the file.
        dest (Path): Path to the destination.
        collision_policy (str): Collision policies. 
        dedupe_by_hash (bool): Duplicate with hash. 
        hash_cache (Optional[Dict[str, str]], optional): Cache of duplicates. Defaults to None.
        logger (_type_, optional): Logs of the actions performed. Defaults to None.

    Raises:
        IsADirectoryError: If the directory is incorrect 
        ValueError: If the collision policy is invalid.

    Returns:
        Tuple[str, Path]: Tuple that contains the action and the final destination. 
    """
    if logger is None: 
        class _Nop:
            def debug(self, *a, **k): pass
            def info(self, *a, **k): pass
            def warning(self, *a, **k): pass
            def error(self, *a, **k): pass
        logger = _Nop() 
        
    src = src if isinstance(src, Path) else Path(src)
    dest = dest if isinstance(dest, Path) else Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    file_hash = None
    
    if dedupe_by_hash:
        file_hash = compute_file_hash(src)
        if hash_cache is not None:
            existing = hash_cache.get(file_hash)
            if existing:
                existing_path = Path(existing)
                if existing_path.exists() and existing_path.is_file():
                    logger.info(f"[duplicate] {src} == {existing_path}")
                    return "duplicate", existing_path
            
    if dest.exists():
        if collision_policy == "rename":
            final_destination = next_name(dest)
            logger.debug(f"[rename] {dest.name} -> {final_destination.name}")
            shutil.move(str(src), str(final_destination))
            if hash_cache and dedupe_by_hash is not None and file_hash:
                hash_cache[file_hash] = str(final_destination)
            return "renamed", final_destination
        
        elif collision_policy == "keep-newest": 
            src_mtime = src.stat().st_mtime
            dest_mtime = dest.stat().st_mtime
            if src_mtime > dest_mtime:
                try:
                    if dest.exists():
                        if dest.is_file() or dest.is_symlink(): dest.unlink()
                        else:
                            raise IsADirectoryError(f"The destination is not a file: {dest}")
                    shutil.move(str(src), str(dest))
                except Exception as e: 
                    logger.error(f"[replace-failed] {src} -> {dest}: {e}")
                    raise
                if hash_cache and dedupe_by_hash is not None and file_hash: 
                    hash_cache[file_hash] = str(dest)
                return "moved", dest
            else: 
                logger.debug(f"[keep-newest:skipped] {src} (older-or-equal) vs {dest}")
                return "skipped", dest
            
        elif collision_policy == "skip":
            logger.debug(f"[skip] {src} -> {dest} (exists)")
            return "skipped", dest
        
        else: 
            raise ValueError(f"invalid collision_policy: {collision_policy}")
    
    shutil.move(str(src), str(dest))
    if hash_cache and dedupe_by_hash is not None and file_hash:
        hash_cache[file_hash] = str(dest)
    return "moved", dest
