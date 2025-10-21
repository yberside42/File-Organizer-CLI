# organizer.py (English)

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from .cli import build_cli_parser
from .config_loader import load_config
from .file_utils import apply_policies_move, next_name
from .history import generate_batch_id, append_batch, load_history, get_last_batch_id
from .logger import setup_logger
from .planner import (discover_files, filter_files, build_plan, apply_collision_policy, apply_dedupe_policy, render_plan,)

def undo_move_one(dest_str: str, src_str: str, logger) -> str:
    """Reverts from destination to its original src. Reverts the last move. 
    
    The file is restored with an alternative name if src already existed.

    Args:
        dest_str (str): Current path of the file.
        src_str (str): Original path of the file.
        logger (_type_): Logger for the messages. 

    Returns:
        str: Result code: 
            - "restored": Restored in src_str
            - "renamed-dest": Restored with an alternative name avoiding collisions.
            - "missing": There was no destination when trying to undo.
            - "skipped": Error during the operation,
    """
    dest = Path(dest_str)
    src = Path(src_str)
    
    if not dest.exists():
        logger.warning(f"[undo-missing] Does not exist in destination: {dest}")
        return "missing"
    
    src.parent.mkdir(parents=True, exist_ok=True)
    final_src = src
    if final_src.exists():
        final_src = next_name(src)
    try:
        shutil.move(str(dest), str(final_src))
        if str(final_src) == src_str:
            return "restored"
        else:
            logger.info(f"[undo-renamed] {src} already existed; {final_src.name} restored.")
            return "renamed-dest"
    except Exception as e:
        logger.error(f"[undo-error] {dest} -> {final_src}: {e}")
        return "skipped"
        
def resolve_history_path(cli_value: Optional[str]) -> Path:
    """Resolves the path of the history file: history.json.
    
    If a path is provided, it is expanded and converted to absolute. If not, a default path is returned: `~/.fo/history.json`
    
    Args:
        cli_value (Optional[str]): Path received from CLI. The default path is used if the received path is incorrect.

    Returns:
        Path: Absolute path to the history file. 
    """
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    return (Path.home() / ".fo" / "history.json").resolve()  

def resolve_config_path(cli_value: Optional[str]) -> Path:
    """Returns the path to config.json (future flag or next to this file)."""
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    return (Path(__file__).parent / "config.json").resolve()

def extract_src_dest(step: dict) -> tuple[Optional[str], Optional[str]]:
    """Extracts candidate src and destination paths from the dictionary: step.

    Looks for the first key that is valid and returns both. The function does not validate type or existence of them.
    
    Args:
        step (dict): Dictionary with the keys of source and destination. 
            - Source ('src'): "src", "source", "path", "from", "input"
            - Destination ('dest'): "dest", "dst", "destination", "target", "to",
          "dest_path", "final_dest", "proposed_dest"

    Returns:
        tuple[Optional[str], Optional[str]]: Pair with the paths found (src, dest) or None if there are no matches
    """
    src_candidates = ("src", "source", "path", "from", "input")
    dest_candidates = ("dest", "dst", "destination", "target", "to", "dest_path", "final_dest", "proposed_dest")

    src = next((step[k] for k in src_candidates if k in step and step[k]), None)
    dest = next((step[k] for k in dest_candidates if k in step and step[k]), None)
    return src, dest

def cmd_run(args, logger, cfg) -> None:
    """Executes the organization: Discovers, filters, plans and applies the moves. 
    
    Flow:
        1.- Discovers files in dst_root. 
        2.- Applies filters and classifications.
        3.- Plans a plan and applies collision and duplicate policies.
        4.- Applies the real moves. 
        5.- Registers a batch in history.json. 

    Args:
        args: Namespace from CLI with important annotations:
            - path, only_ext, size_min/size_max, by_date and categories.
            - collision ("rename" | "keep-newest" | "skip")
            - dedupe ("skip" | "link" | "delete")
            - history (alternative path for history.json)
        logger: Logger for console outputs. 
        cfg (dict): Configuration.
        
    Return:
        None: Logs progress and all results, adding a record to history.json with:
            - plan (src/dest/action)
            - stats (moved/renamed/skipped/duplicates)
            - metadata (`timestamp`, `command`, `source_dir`, `dest_dir`)
    """
    dst_root = Path(args.path) if args.path else Path.cwd()
    follow_symlinks = bool(cfg.get("behavior", {}).get("followSymlinks", False))
    history_path = resolve_history_path(getattr(args, "history", None))
    logger.info(f"History path (run): {history_path}")
    
    plan = [] 
    
    try: 
        files = discover_files(dst_root, recursive=False, follow_symlinks=follow_symlinks)
        logger.info(f"{len(files)} files found: {dst_root}")

        files = filter_files(
            files,
            only_ext=args.only_ext,
            size_min=args.size_min,
            size_max=args.size_max,
        )
        logger.info(f"{len(files)} files after filters")

        plan = build_plan(files, cfg, dst_root, by_date=args.by_date)

        if args.categories:
            wanted = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
            plan = [it for it in plan if it.get("category") in wanted]
    
        plan = apply_collision_policy(plan, policy=args.collision)   
        plan = apply_dedupe_policy(plan, policy=args.dedupe)        
    
    except Exception as e: 
        logger.error(f"[run:init] Failed to prepare plan: {e}")
        print("Error preparing the plan. Check the log.")
        return 

    if plan is None: 
        logger.error("[run] build_plan returned None")
        print("Invalid plan (None). Check the log.")
        return

    if plan:
        logger.debug(f"[run] example plan[0] keys: {sorted(plan[0].keys())}")
    
    moved = renamed = skipped = duplicates = 0 
    plan_realizado: list[dict] = []
    hash_cache: dict[str, str] = {}
    
    dedupe_by_hash = (args.dedupe == "skip")
    if args.dedupe in ("link", "delete"):
        logger.warning("Dedupe 'link'/'delete' not implemented in run v1; will be ignored.")

    for idx, step in enumerate(plan):
        src_str, dest_str = extract_src_dest(step)
        if not src_str or not dest_str:
            logger.error(f"[run] item without src/dest (keys={list(step.keys())}): {step}")
            skipped += 1
            continue

        src = Path(src_str)
        dest = Path(dest_str)

        try:
            action, final_dest = apply_policies_move(
                src, dest,
                collision_policy=args.collision,    
                dedupe_by_hash=dedupe_by_hash,
                hash_cache=hash_cache,
                logger=logger
            )
        except Exception as e:
            logger.error(f"[run-error] {src} -> {dest}: {e}")
            action, final_dest = "skipped", dest

        if action == "moved":
            moved += 1
        elif action == "renamed":
            renamed += 1
        elif action == "skipped":
            skipped += 1
        elif action == "duplicate":
            duplicates += 1
        
        plan_realizado.append({
            "src": str(src),
            "dest": str(final_dest),
            "action": action 
        })
    
    batch_id = generate_batch_id()
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "command": "run",
        "source_dir": str(dst_root),
        "dest_dir": str(dst_root), 
        "plan": plan_realizado,
        "stats": {
            "moved": moved,
            "renamed": renamed,
            "skipped": skipped,
            "duplicates": duplicates
        }
    }
    append_batch(history_path, batch_id, record)
    
    logger.info(f"[run] OK - batch_id: {batch_id}")
    logger.info(f"Stats -> moved:{moved} renamed:{renamed} skipped:{skipped} duplicates:{duplicates}")
    print(f"[run] OK - batch_id: {batch_id}")
    print(f"Stats -> moved:{moved} renamed:{renamed} skipped:{skipped} duplicates:{duplicates}")

def cmd_undo(args, logger, cfg) -> None:
    """Undoes the last run action registered in history. 

    Args:
        args: Namespace from CLI, history (str) and yes (bool) are used
        logger: Logger for console outputs. 
        cfg (dict): Configuration.
        
    Returns:
        None: Prints the operation summary with the counters: 
            - restored
            - renamed
            - missing
            - skipped
    """
    history_path = resolve_history_path(getattr(args, "history", None))
    logger.info(f"History path (undo): {history_path}")
    last_id = get_last_batch_id(history_path, command="run")
    
    if not last_id:
        logger.info("No batches to undo.")
        print("No batches to undo.")
        return
    
    hist = load_history(history_path)
    batches = hist.get("batches") or []
    ids = [b.get("batch_id") for b in batches if isinstance(b, dict)]
    logger.debug(f"[undo] batches found: {len(batches)}; last IDs: {ids[-5:]}")

    # Finds the record by batch_id
    rec = next((b for b in batches if isinstance(b, dict) and b.get("batch_id") == last_id), None)
    if not rec:
        logger.error(f"The record of batch_id: {last_id}. Not found.")
        print(f"Error: The record of batch_id: {last_id}. Not found.")
        return

    plan = rec.get("plan", [])

    if not isinstance(plan, list) or not plan:
        logger.info(f"Batch {last_id} has no plan for undo.")
        print(f"Batch {last_id} has no plan for undo; not possible to undo.")
        return

    if not getattr(args, "yes", False):
        print(f"Batch will be undone: {last_id} ({rec.get('timestamp','')})")
        ans = input("Continue? [y/N]: ").strip().lower()
        if ans not in ("y", "yes", "s", "si", "sí"):
            print("Operation canceled.")
            return
        
    restored = renamed = missing = skipped = 0
    
    for step in reversed(plan):
        action = step.get("action")
        if action not in ("moved", "renamed"): 
            continue
        
        src = step.get("src")
        dest = step.get("dest")
        
        if not src or not dest: 
            logger.warning(f"[undo-invalid-step] {step}")
            skipped += 1
            continue
        
        result = undo_move_one(dest, src, logger)
        if result == "restored":
            restored += 1
        elif result == "renamed-dest":
            renamed += 1
        elif result == "missing":
            missing += 1
        else:
            skipped += 1
    
    
    logger.info(f"[undo] batch-id: {last_id} -> restored: {restored} renamed: {renamed} missing: {missing} skipped: {skipped}")
    print(f"[undo] batch_id: {last_id}")
    print(f"Stats -> restored: {restored} renamed: {renamed} missing: {missing} skipped: {skipped}")

def cmd_merge(args, logger, cfg) -> None:
    """Merges content from a source directory into a destination directory.

Flow:
    1) Resolves paths src_root and dst_root.
    2) Discovers files in src_root.
    3) Applies filters and classification.
    4) Builds the plan with build_plan and applies collision and duplicate policies.
    5) Displays the plan with render_plan and, after confirmation, executes the
       real actions with apply_policies_move.
    6) Registers a merge batch in history.json with statistics and actions.

Args:
    args: Namespace from the CLI with relevant flags:
        - src (str): Source path
        - dest (str): Destination path.
        - only_ext (str|None): allowed extensions separated by commas.
        - size_min (str|int|float|None): minimum size.
        - size_max (str|int|float|None): maximum size.
        - by_date (str|None): "created" | "modified" for YYYY/MM.
        - categories (str|None): list of allowed categories separated by commas.
        - collision (str): "rename" | "keep-newest" | "skip".
        - dedupe (str): "skip" | "link" | "delete".
        - history (str|None): path to `history.json`.
        - yes (bool): if True, does not ask for interactive confirmation.
    logger: Logger configured to record progress and results.
    cfg (dict): Configuration.

Returns:
    None: Prints/logs the process and results. At the end, adds a
    batch record to `history.json` with:
        - plan (src/dest/action)
        - stats (moved/renamed/skipped/duplicates)
        - metadata (`timestamp`, `command`, `source_dir`, `dest_dir`)
"""
    src_root = Path(args.src).expanduser().resolve()
    dst_root = Path(args.dest).expanduser().resolve()
    if not src_root.exists() or not src_root.is_dir():
        logger.error(f"[merge] Invalid source: {src_root}")
        print("Error: src does not exist.")
        return
    
    dst_root.mkdir(parents=True, exist_ok=True)
    
    history_path = resolve_history_path(getattr(args, "history", None))
    logger.info(f"History Path: {history_path}")
    follow_symlinks = bool(cfg.get("behavior", {}).get("followSymlinks", False))
    
    try: 
        files = discover_files(src_root, recursive=False, follow_symlinks=follow_symlinks)
        logger.info(f"[merge] {len(files)} files detected in src={src_root}")
        files = filter_files(files, only_ext=args.only_ext, size_min=args.size_min, size_max=args.size_max,)
        logger.info(f"[merge] {len(files)} files after filters.")
        
        plan = build_plan(files, cfg, dst_root, by_date=args.by_date)
        
        if args.categories:
            wanted = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
            plan = [it for it in plan if it.get("category") in wanted]
            
        plan = apply_collision_policy(plan, policy=args.collision)
        plan = apply_dedupe_policy(plan, policy=args.dedupe)
        
    except Exception as e:
        logger.error(f"[merge:int] Error preparing the plan: {e}")
        print("Error preparing the merge plan.")
        return
    
    if not isinstance(plan, list):
        logger.error("[merge] build_plan returned an invalid type.")
        print("Invalid plan.")
        return
    
    render_plan(plan, logger, max_rows=50)
    
    if not getattr(args, "yes", False):
        ans = input("Do you want to apply the merge? [y/N]: ").strip().lower()
        if ans not in ("y", "yes", "s", "si", "sí"):
            print("Operation canceled.")
            return
        
    moved = renamed = skipped = duplicates = 0
    
    plan_realizado: list[dict] = []
    hash_cache: dict[str, str] = {}
    dedupe_by_hash = (args.dedupe == "skip")
    if args.dedupe in ("link", "delete"):
        logger.warning("Dedupe link'/'delete' not implemented in merge.")
        
    for step in plan:
        src_str, dest_str = extract_src_dest(step)
        if not src_str or not dest_str:
            logger.error(f"[merge] item in src/dest (keys={list(step.keys())}): {step}")
            skipped += 1
            continue
        
        src = Path(src_str)
        dest = Path(dest_str)
        
        try:
            action, final_dest = apply_policies_move(
                src, dest,
                collision_policy=args.collision,
                dedupe_by_hash=dedupe_by_hash,
                hash_cache=hash_cache,
                logger=logger
            )
        except Exception as e: 
            logger.error(f"[merge-error] {src} -> {dest}: {e}")
            action, final_dest = "skipped", dest
        
        if action == "moved":
            moved += 1
        elif action == "renamed":
            renamed += 1
        elif action == "skipped":
            skipped += 1
        elif action == "duplicate":
            duplicates += 1
            
        plan_realizado.append({
            "src": str(src),
            "dest": str(final_dest),
            "action": action
        })
        
    batch_id = generate_batch_id()
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "command": "merge",
        "source_dir": str(src_root),
        "dest_dir": str(dst_root),
        "plan": plan_realizado,
        "stats": {
            "moved": moved,
            "renamed": renamed,
            "skipped": skipped,
            "duplicates": duplicates
        }
    }
    append_batch(history_path, batch_id, record)
    
    logger.info(f"[merge] OK - batch_id: {batch_id}")
    logger.info(f"Stats -> moved: {moved} renamed: {renamed} skipped: {skipped} duplicates: {duplicates}")
    print(f"[merge] OK - batch_id: {batch_id}")
    print(f"Stats -> moved: {moved} renamed: {renamed} skipped: {skipped} duplicates:{ duplicates}")

def main(argv: Optional[List[str]] = None) -> None:
    """Entry point of the CLI with all its components: logger, parser, config and dispatcher.
    
    Configures the logger, parses arguments, loads the configuration and executes subcommands: preview, run, undo, merge and validate-config.
    
    Args:
        argv(Optional[List[str]]):  List of arguments.
        
    Returns: 
        None
        
    Examples:
    > main(['preview', '--path', './tests', '--by-date', 'modified', '--debug'])
    > main(['run', '--path', './tests'])
    """
    logs_dir = Path(__file__).parent / "logs"
    logger = setup_logger(logs_dir)

    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if getattr(args, "debug", False):
        logger.setLevel(logging.DEBUG)
        for h in logger.handlers:
            h.setLevel(logging.DEBUG)
    logger.debug(f"Args: {args}")

    cfg_path = resolve_config_path(None)
    cfg = load_config(cfg_path)
    logger.info(f"Config path: {cfg_path}")

    if args.command == "preview":
        dst_root = Path(args.path) if args.path else Path.cwd()
        follow_symlinks = bool(cfg.get("behavior", {}).get("followSymlinks", False))

        files = discover_files(dst_root, recursive=False, follow_symlinks=follow_symlinks)
        logger.info(f"{len(files)} files found in {dst_root}")

        files = filter_files(
            files,
            only_ext=args.only_ext,
            size_min=args.size_min,
            size_max=args.size_max,
        )
        logger.info(f"{len(files)} files after filters")

        plan = build_plan(files, cfg, dst_root, by_date=args.by_date)

        if args.categories:
            wanted: Set[str] = {c.strip().lower() for c in args.categories.split(",") if c.strip()}
            plan = [it for it in plan if it.get("category") in wanted]

        plan = apply_collision_policy(plan, policy=args.collision)

        plan = apply_dedupe_policy(plan, policy=args.dedupe)

        render_plan(plan, logger, max_rows=getattr(args, "max_rows", 50) if hasattr(args, "max_rows") else 50)

    elif args.command == "run":
        cmd_run(args, logger, cfg)

    elif args.command == "undo":
        cmd_undo(args, logger, cfg)

    elif args.command == "merge":
        cmd_merge(args, logger, cfg)

    elif args.command == "validate-config":
        cats = cfg.get("categories", {})
        logger.info(f"Available categories ({len(cats)}): {', '.join(sorted(cats.keys()))}")

    else:
        logger.error("Unrecognized command.")

if __name__ == "__main__":
    main()
