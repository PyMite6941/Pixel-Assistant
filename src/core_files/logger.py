import logging
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


def setup_logger(name: str = "pixel") -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"pixel_{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
    return logger


def log_conversation(prompt: str, response: str, provider: str):
    logger = setup_logger("conversations")
    logger.info(f"[{provider.upper()}] USER: {prompt}")
    logger.info(f"[{provider.upper()}] PIXEL: {response}")
