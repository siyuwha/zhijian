import logging
import sys
import os

def setup_logging(debug: bool = True):
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    os.makedirs("logs", exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/app.log", encoding="utf-8"),
    ]

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers
    )

logger = logging.getLogger("trading_system")
