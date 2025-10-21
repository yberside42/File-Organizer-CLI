# logger.py (English)

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(log_dir: Path,
    name: str = "File_Organizer",
    level: int = logging.INFO,
    max_bytes: int = 1_000_000, 
    backup_count: int = 3) -> logging.Logger:
    """Configures a rotating logger with output to file and console for File Organizer.

    Args:
        log_dir (Path): Directory where the log files will be stored.
        name (str, optional): Main logger name. Defaults to "File_Organizer".
        level (int, optional): Logging level (for example, logging.INFO, logging.DEBUG).
            Defaults to logging.INFO.
        max_bytes (int, optional): Maximum size in **bytes** per log file before
            rotation. Must be > 0. Defaults to 1_000_000 (~1 MB).
        backup_count (int, optional): Maximum number of backup files that will be
            kept after rotation. Must be >= 0. Defaults to 3.

    Returns:
        logging.Logger: Logger configured and ready to use.

    Raises:
        ValueError: If `max_bytes <= 0` or `backup_count < 0`.

    Notes:
        - Creates `log_dir` automatically if it does not exist.
        - Main file: ``log_dir / f"{name}.log"``.
        - Includes:
            * `RotatingFileHandler` (file with rotation).
            * `StreamHandler` (console output).
        - Avoids adding duplicate handlers if the logger was already configured.
        - `propagate = False` prevents duplicating output with the Root Logger.
        - The first configuration with a given `name` fixes the file destination; calls
          later with the same `name` **do not** relocate the log to another `log_dir`.

    Example:
        > from pathlib import Path
        > logger = setup_logger(Path("./logs"), name="organizer", level=logging.DEBUG)
        > logger.info("Starting File Organizer")
    """
    
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")
    if backup_count < 0:
        raise ValueError("backup_count must be >= 0")

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    logger = logging.getLogger(name)
    logger.propagate = False

    if logger.handlers:
        logger.setLevel(level)
        for h in logger.handlers:
            h.setLevel(level)
        return logger

    file_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_format = logging.Formatter("%(levelname)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True, 
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_format)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_format)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.debug("Logger started")

    return logger
