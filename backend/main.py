from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from .bot import CommandHandler, TelegramPoller
from .config import load_config
from .database import Database
from .filters import FilterManager
from .notifier import TelegramNotifier
from .orchestrator import ScraperOrchestrator


def setup_logging(logs_dir: str, level: str = "INFO") -> None:
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%d-%m-%Y")
    log_file = logs_path / f"{today}.log"

    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root.addHandler(ch)

    fh = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    fh.suffix = "%d-%m-%Y"

    def namer(default_name: str) -> str:
        p = Path(default_name)
        date_part = p.suffix.lstrip(".")
        return str(p.parent / f"{date_part}.log")

    fh.namer = namer
    fh.setFormatter(formatter)
    root.addHandler(fh)


def main() -> None:
    """
    1. Load config.yaml, validate
    2. Setup logging
    3. Khởi tạo DB, FilterManager, seed defaults
    4. Seed admin user
    5. Khởi tạo Notifier, Orchestrator, CommandHandler, TelegramPoller
    6. Start APScheduler + polling
    """
    base_dir = Path(__file__).resolve().parent
    config = load_config(base_dir / "config.yaml")

    setup_logging(
        logs_dir=str(base_dir.parent / config.logging.get("dir", "logs")),
        level=str(config.logging.get("level", "INFO")),
    )

    db = Database(base_dir / config.database["path"])

    fm = FilterManager(db, config.default_filters)
    fm.initialize()

    # Seed admin user nếu chưa có
    admin_chat_id = str(config.telegram["admin_chat_id"])
    if admin_chat_id:
        existing = db.get_user(admin_chat_id)
        if not existing:
            db.add_user(admin_chat_id, "admin", is_admin=True)

    notifier = TelegramNotifier(config.telegram["bot_token"], db)

    # Truyền config dạng dict đơn giản cho scrapers/orchestrator
    cfg_dict = {
        "scraper": config.scraper,
    }
    orchestrator = ScraperOrchestrator(cfg_dict, db, fm, notifier)

    handler = CommandHandler(db, fm, orchestrator, notifier)
    poller = TelegramPoller(config.telegram["bot_token"], handler)

    LOGGER = logging.getLogger(__name__)

    def _scheduled_run() -> None:
        LOGGER.info("Cron job triggered at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        orchestrator.run()
        LOGGER.info("Cron job finished at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    scheduler = BackgroundScheduler()
    schedule_mode = str(config.scheduler.get("mode", "interval")).lower()
    if schedule_mode == "daily":
        run_hour = int(config.scheduler.get("daily_hour", 9))
        run_minute = int(config.scheduler.get("daily_minute", 0))
        scheduler.add_job(_scheduled_run, "cron", hour=run_hour, minute=run_minute)
        LOGGER.info("Scheduler mode=daily at %02d:%02d", run_hour, run_minute)
    else:
        interval_minutes = int(config.scheduler.get("interval_minutes", 30))
        scheduler.add_job(_scheduled_run, "interval", minutes=interval_minutes)
        LOGGER.info("Scheduler mode=interval every %s minutes", interval_minutes)
    scheduler.start()

    try:
        poller.start()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
        scheduler.shutdown()


if __name__ == "__main__":
    main()

