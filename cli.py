# cli.py (English)

import argparse

def build_cli_parser() -> argparse.ArgumentParser:
    """Builds and configures the command parser for File Organizer.
    
    Workflow: 
    1.- preview: Generates an organization plan without modifying files. 
    2.- run: Applies the plan with collision and duplicate policies. 
    3.- undo: Reverts all the last applied batch. 
    4.- merge: Merges subfolders with the same name between different directories. 
    5.- validate-config: Validates the structure of the config.json file.
    
    Subcommands:
        - preview / run: 
            --path: destination path.
            --only-ext: filter by extensions (e.g. ".jpg,.pdf").
            --categories: logical categories (e.g. "media,docs,code").
            --by-date: partition by date ("created" | "modified") → YYYY/MM.
            --size-min/--size-max: size limits (e.g. "10MB", "2GB").
            --move/--copy: operation mode (mutually exclusive in practice).
            --skip-empties: do not create empty folders.
            --dedupe: policy for duplicates ("skip" | "link" | "delete").
            --collision: name conflict policy ("rename" | "keep-newest" | "skip").
            --dry-run: force simulation.
            --confirm: do not ask interactive confirmation.
            --debug: debug output.
        - undo:
            --debug
        - merge:
            --name: subfolder that will be merged.
            --from / --into: source and destination directories respectively.
            --dedupe, --dry-run, --confirm, --debug
        - validate-config

    Returns:
        argparse.ArgumentParser: Parser configured with subcommands and options.
    
    Notes:
        - The parser sets "dest='command'" and "required=True" to ensure one subcommand is chosen.
        - The option "--version" shows the CLI version.
    """
    
    parser = argparse.ArgumentParser(prog="fo", description="File Organizer CLI - Preview -> Run -> Undo, with merge and validate / config.")
    parser.add_argument("--version", action="version", version="File Organizer CLI v.1")
    parser.add_argument("--history", help="Path to history.json (default: '/Users/yberside/Desktop/Programación/SQLite/File Organizer (Prueba)/history.json')")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_preview = subparsers.add_parser("preview", help="Shows the organization of the files without modifying them.")
    p_preview.add_argument("--path", type=str, help="Destination path.")
    p_preview.add_argument("--only-ext", type=str, help="Filter by file extensions. Comma separated: (.jpg, .pdf, etc.)")
    p_preview.add_argument("--categories", type=str,help="List of categories. Comma separated: (media, docs, code, etc.)")
    p_preview.add_argument("--by-date", choices=["created", "modified"], help="Split by date. (YYYY/MM)")
    p_preview.add_argument("--size-min", type=str, help="Minimum size.")
    p_preview.add_argument("--size-max", type=str, help="Maximum size.")
    p_preview.add_argument("--move", action="store_true", help="Plan move.")
    p_preview.add_argument("--copy", action="store_true", help="Plan copy.")
    p_preview.add_argument("--skip-empties", action="store_true", help="Do not create empty folders.")
    p_preview.add_argument("--dedupe", choices=["skip", "link", "delete"], default="skip", help="Duplicates policy.")
    p_preview.add_argument("--collision", choices=["rename", "keep-newest", "skip"], default="rename", help="Policy for name collisions.")
    p_preview.add_argument("--dry-run", action="store_true", help="Force simulation.")
    p_preview.add_argument("--confirm", action="store_true", help="Do not ask interactive confirmation.")
    p_preview.add_argument("--debug", action="store_true", help="Debug output.")

    p_run = subparsers.add_parser("run", help="Applies the organization.")
    p_run.add_argument("--path", type=str, help="Destination path.")
    p_run.add_argument("--only-ext", type=str, help="Filter by file extensions. Comma separated: (.jpg, .pdf, etc.)")
    p_run.add_argument("--categories", type=str,help="List of categories. Comma separated: (media, docs, code, etc.)")
    p_run.add_argument("--by-date", choices=["created", "modified"], help="Split by date. (YYYY/MM)")
    p_run.add_argument("--size-min", type=str, help="Minimum size.")
    p_run.add_argument("--size-max", type=str, help="Maximum size.")
    p_run.add_argument("--move", action="store_true", help="Move.")
    p_run.add_argument("--copy", action="store_true", help="Copy.")
    p_run.add_argument("--skip-empties", action="store_true", help="Do not create empty folders.")
    p_run.add_argument("--dedupe", choices=["skip", "link", "delete"], default="skip", help="Duplicates policy.")
    p_run.add_argument("--collision", choices=["rename", "keep-newest", "skip"], default="rename", help="Policy for name collisions.")
    p_run.add_argument("--dry-run", action="store_true", help="Simulate without applying.")
    p_run.add_argument("--confirm", action="store_true", help="Do not ask interactive confirmation.")
    p_run.add_argument("--debug", action="store_true", help="Debug output.")

    p_undo = subparsers.add_parser("undo", help="Reverts the last successful batch.")
    p_undo.add_argument("--debug", action="store_true", help="Debug output.")
    p_undo.add_argument("-y", "--yes", action="store_true", help="Automatically confirm the undo without asking.")

    p_merge = subparsers.add_parser("merge", help="Merges homonymous subfolders between directories.")
    p_merge.add_argument("--src", required=True, help="Source directory to merge.")
    p_merge.add_argument("--dest", required=True, help="Final destination directory.")
    p_merge.add_argument("--only-ext", default=None, help="Filter by file extensions. Comma separated: (.jpg, .pdf, etc.)")
    p_merge.add_argument("--categories", default=None, help="Limit to categories (csv) defined in config.json.")
    p_merge.add_argument("--by_date", action="store_true", help="Classify by date if config supports it.")
    p_merge.add_argument("--size_min", type=int, default=None, help="Minimum size.")
    p_merge.add_argument("--size_max", type=int, default=None, help="Maximum size.")
    p_merge.add_argument("--collision", choices=["rename", "keep-newest", "skip"], default="rename", help="Policy for name collision.")
    p_merge.add_argument("--dedupe", choices=["skip", "link", "delete"], default="skip", help="Policy for duplicates by hash.")
    p_merge.add_argument("--debug", action="store_true", help="Debug output.")
    p_merge.add_argument("-y", "--yes", action="store_true", help="Automatically confirm execution (without asking).")

    subparsers.add_parser("validate-config", help="Validates the config.json file.")
    
    return parser
