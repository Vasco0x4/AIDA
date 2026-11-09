"""Small, restart-safe scheduler for the persistent NVD digest policy."""
from __future__ import annotations

import asyncio
import random

from database import SessionLocal
from services.nvd_service import NVDService
from utils.logger import get_logger

logger = get_logger(__name__)

TICK_SECONDS = 60.0


class NVDScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="aida-nvd-scheduler")
        logger.info("NVD scheduler started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        logger.info("NVD scheduler stopped")

    def _refresh(self) -> None:
        db = SessionLocal()
        try:
            NVDService(db).refresh_if_due()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def tick(self) -> None:
        """Run blocking HTTP/DB work off the event loop and contain failures."""
        try:
            await asyncio.to_thread(self._refresh)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Cache/error state is persisted by NVDService where possible. The
            # scheduler remains alive for the next policy interval.
            logger.warning("NVD scheduled refresh failed", error=str(exc)[:200])

    async def _loop(self) -> None:
        while not self._stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=TICK_SECONDS + random.uniform(0, 5))
            except asyncio.TimeoutError:
                pass


nvd_scheduler = NVDScheduler()
