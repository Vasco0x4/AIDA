"""NVD API 2.0 critical-CVE digest with a persistent SQL cache."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

import httpx
from sqlalchemy.orm import Session

from models.nvd import NVDCVE, NVDDigestState
from models.platform_settings import PlatformSettings
from utils.crypto import decrypt_secret, encrypt_secret

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_DETAIL_URL = "https://nvd.nist.gov/vuln/detail/"


class NVDRequestError(RuntimeError):
    """A sanitized NVD transport/HTTP failure suitable for cache metadata."""


class NVDService:
    def __init__(
        self,
        db: Session,
        *,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        now: Optional[Callable[[], datetime]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        monotonic: Optional[Callable[[], float]] = None,
        min_request_interval: Optional[float] = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        self.db = db
        self.api_key_source = "explicit" if api_key is not None else None
        if api_key is None:
            stored = self.db.query(PlatformSettings).filter_by(key="nvd_api_key").first()
            if stored and stored.value:
                api_key = decrypt_secret(stored.value)
                self.api_key_source = "encrypted"
            else:
                api_key = os.getenv("NVD_API_KEY")
                self.api_key_source = "environment" if api_key else None
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._last_request_at: Optional[float] = None
        self.min_request_interval = (
            min_request_interval
            if min_request_interval is not None
            else (0.6 if self.api_key else 6.0)
        )
        self.max_retries = max(0, max_retries)
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay

    def _state(self) -> NVDDigestState:
        state = self.db.get(NVDDigestState, 1)
        if state is None:
            state = NVDDigestState(id=1)
            self.db.add(state)
            self.db.commit()
        return state

    @staticmethod
    def _nvd_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _cvss(cve: dict) -> tuple[Optional[float], Optional[str], Optional[str]]:
        for metric_name in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metrics = cve.get("metrics", {}).get(metric_name) or []
            if not metrics:
                continue
            metric = next((m for m in metrics if m.get("type") == "Primary"), metrics[0])
            data = metric.get("cvssData", {})
            return (
                data.get("baseScore"),
                data.get("baseSeverity") or metric.get("baseSeverity"),
                data.get("version"),
            )
        return None, None, None

    @staticmethod
    def _description(cve: dict) -> str:
        descriptions = cve.get("descriptions") or []
        value = next((d.get("value", "") for d in descriptions if d.get("lang") == "en"), "")
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) > 500:
            return value[:497].rstrip() + "..."
        return value

    @staticmethod
    def _products(cve: dict) -> list[str]:
        products = []

        def visit(value):
            if isinstance(value, dict):
                if value.get("vulnerable", True) and value.get("criteria"):
                    products.append(value["criteria"])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(cve.get("configurations") or [])
        return list(dict.fromkeys(products))

    @classmethod
    def _parse_vulnerability(cls, wrapper: dict) -> dict:
        cve = wrapper.get("cve", wrapper)
        score, severity, version = cls._cvss(cve)
        return {
            "cve_id": cve["id"],
            "cvss_score": score,
            "cvss_severity": severity,
            "cvss_version": version,
            "published_at": cls._parse_time(cve["published"]),
            "last_modified_at": cls._parse_time(cve["lastModified"]) if cve.get("lastModified") else None,
            "description": cls._description(cve),
            "affected_products": cls._products(cve),
            "nvd_url": NVD_DETAIL_URL + cve["id"],
        }

    def _retry_delay(self, response: Optional[httpx.Response], attempt: int) -> float:
        exponential = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt))
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(self.retry_max_delay, max(0.0, float(retry_after)))
                except ValueError:
                    try:
                        parsed = parsedate_to_datetime(retry_after)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        seconds = (parsed - self._now()).total_seconds()
                        return min(self.retry_max_delay, max(0.0, seconds))
                    except (TypeError, ValueError):
                        pass
        return exponential

    def _request_page(self, params: dict) -> dict:
        headers = {"apiKey": self.api_key} if self.api_key else {}
        for attempt in range(self.max_retries + 1):
            response = None
            if self._last_request_at is not None:
                elapsed = self._monotonic() - self._last_request_at
                remaining = max(0.0, self.min_request_interval - elapsed)
                if remaining:
                    self._sleep(remaining)
            self._last_request_at = self._monotonic()
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                    response = client.get(NVD_API_URL, params=params, headers=headers)
            except httpx.RequestError:
                if attempt >= self.max_retries:
                    raise NVDRequestError("NVD network request failed after retries") from None
            else:
                if response.status_code not in (429, 500, 502, 503, 504):
                    if response.status_code >= 400:
                        raise NVDRequestError(f"NVD returned HTTP {response.status_code}")
                    return response.json()
                if attempt >= self.max_retries:
                    raise NVDRequestError(
                        f"NVD returned HTTP {response.status_code} after retries"
                    )
            self._sleep(self._retry_delay(response, attempt))
        raise AssertionError("unreachable")

    def _fetch_severity(
        self, state: NVDDigestState, start: datetime, end: datetime, parameter: str,
    ) -> list[dict]:
        items = []
        start_index = 0
        total_results = None
        while len(items) < state.max_items and (total_results is None or start_index < total_results):
            body = self._request_page({
                parameter: "CRITICAL",
                "pubStartDate": self._nvd_time(start),
                "pubEndDate": self._nvd_time(end),
                "startIndex": start_index,
                "resultsPerPage": min(2000, state.max_items),
            })
            page = body.get("vulnerabilities", [])
            total_results = int(body.get("totalResults", len(page)))
            items.extend(self._parse_vulnerability(v) for v in page)
            if not page:
                break
            start_index += len(page)
        return items[:state.max_items]

    def _fetch(self, state: NVDDigestState, end: datetime) -> tuple[datetime, list[dict]]:
        start = end - timedelta(days=state.lookback_days)
        parameters = ["cvssV3Severity"]
        if state.include_cvss_v4:
            parameters.append("cvssV4Severity")
        deduplicated = {}
        for parameter in parameters:
            for item in self._fetch_severity(state, start, end, parameter):
                deduplicated[item["cve_id"]] = item
        items = sorted(deduplicated.values(), key=lambda item: item["published_at"], reverse=True)
        return start, items[:state.max_items]

    @staticmethod
    def _public_item(item: dict) -> dict:
        return {key: value for key, value in item.items() if key != "last_modified_at"}

    @staticmethod
    def _row_item(row: NVDCVE) -> dict:
        return {
            "cve_id": row.cve_id,
            "cvss_score": row.cvss_score,
            "cvss_severity": row.cvss_severity,
            "cvss_version": row.cvss_version,
            "published_at": row.published_at,
            "description": row.description,
            "affected_products": row.affected_products or [],
            "nvd_url": row.nvd_url,
        }

    def _digest(self, state: NVDDigestState, *, refreshed: bool = False) -> dict:
        rows = []
        if state.last_success_at and state.window_start and state.window_end:
            rows = (
                self.db.query(NVDCVE)
                .filter(
                    NVDCVE.last_seen_at == state.last_success_at,
                    NVDCVE.published_at >= state.window_start,
                    NVDCVE.published_at <= state.window_end,
                )
                .order_by(NVDCVE.published_at.desc(), NVDCVE.cve_id)
                .limit(state.max_items)
                .all()
            )
        now = self._now()
        stale = not state.last_success_at or bool(state.last_error) or (
            state.enabled and (not state.next_refresh_at or now >= state.next_refresh_at)
        )
        return {
            "status": "stale" if stale else "fresh",
            "stale": stale,
            "error": state.last_error,
            "refreshed": refreshed,
            "enabled": state.enabled,
            "refresh_interval_hours": state.refresh_interval_hours,
            "lookback_days": state.lookback_days,
            "max_items": state.max_items,
            "include_cvss_v4": state.include_cvss_v4,
            "window_start": state.window_start,
            "window_end": state.window_end,
            "last_attempt_at": state.last_attempt_at,
            "last_success_at": state.last_success_at,
            "next_refresh_at": state.next_refresh_at,
            "cache_age_seconds": (
                max(0, int((now - state.last_success_at).total_seconds()))
                if state.last_success_at else None
            ),
            "consecutive_failures": state.consecutive_failures,
            "api_key_configured": bool(self.api_key),
            "api_key_source": self.api_key_source,
            "item_count": len(rows),
            "items": [self._row_item(row) for row in rows],
        }

    def get_digest(self) -> dict:
        return self._digest(self._state())

    def get_status(self) -> dict:
        status = self.get_digest()
        status.pop("items")
        return status

    def update_schedule(self, **changes) -> dict:
        limits = {
            "refresh_interval_hours": (1, 720),
            "lookback_days": (1, 120),
            "max_items": (1, 5000),
        }
        allowed = set(limits) | {"enabled", "include_cvss_v4"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown NVD schedule fields: {sorted(unknown)}")
        for field, (minimum, maximum) in limits.items():
            if field in changes and not minimum <= changes[field] <= maximum:
                raise ValueError(f"{field} must be between {minimum} and {maximum}")
        state = self._state()
        for field, value in changes.items():
            setattr(state, field, value)
        if not state.enabled:
            state.next_refresh_at = None
        elif changes:
            # Re-evaluate promptly after any schedule/window change.
            state.next_refresh_at = self._now()
        self.db.commit()
        return self.get_status()

    def set_api_key(self, api_key: str) -> dict:
        """Store the optional NVD credential with the platform encryption helper."""
        value = api_key.strip()
        if not value or len(value) > 512:
            raise ValueError("NVD API key must contain 1-512 characters")
        row = self.db.query(PlatformSettings).filter_by(key="nvd_api_key").first()
        if row is None:
            row = PlatformSettings(
                key="nvd_api_key", value=encrypt_secret(value),
                description="NVD API credential (encrypted)")
            self.db.add(row)
        else:
            row.value = encrypt_secret(value)
        self.db.commit()
        self.api_key = value
        self.api_key_source = "encrypted"
        return self.get_status()

    def clear_api_key(self) -> dict:
        self.db.query(PlatformSettings).filter_by(key="nvd_api_key").delete()
        self.db.commit()
        self.api_key = os.getenv("NVD_API_KEY")
        self.api_key_source = "environment" if self.api_key else None
        return self.get_status()

    def refresh_if_due(self) -> dict:
        """Synchronous scheduler hook; call from a worker thread if needed."""
        state = self._state()
        now = self._now()
        if not state.enabled:
            return self._digest(state)
        if state.last_success_at and state.next_refresh_at and now < state.next_refresh_at:
            return self._digest(state)
        return self.refresh(force=False)

    def _safe_error(self, exc: Exception) -> str:
        message = str(exc) or exc.__class__.__name__
        if self.api_key:
            message = message.replace(self.api_key, "[redacted]")
        return message[:500]

    def refresh(self, *, force: bool = True) -> dict:
        state = self._state()
        now = self._now()
        try:
            start, items = self._fetch(state, now)
        except Exception as exc:
            state.last_attempt_at = now
            state.last_error = self._safe_error(exc)
            state.consecutive_failures += 1
            state.next_refresh_at = (
                now + timedelta(hours=min(1, state.refresh_interval_hours))
                if state.enabled else None
            )
            self.db.commit()
            from services.metrics import NVD_REFRESHES
            NVD_REFRESHES.labels(result="stale").inc()
            return self._digest(state, refreshed=True)
        seen_at = now
        for item in items:
            row = self.db.get(NVDCVE, item["cve_id"])
            if row is None:
                row = NVDCVE(cve_id=item["cve_id"], last_seen_at=seen_at)
                self.db.add(row)
            for key, value in item.items():
                if key != "cve_id":
                    setattr(row, key, value)
            row.last_seen_at = seen_at
        state.window_start = start
        state.window_end = now
        state.last_attempt_at = now
        state.last_success_at = now
        state.next_refresh_at = (
            now + timedelta(hours=state.refresh_interval_hours)
            if state.enabled else None
        )
        state.last_error = None
        state.consecutive_failures = 0
        state.item_count = len(items)
        self.db.commit()
        from services.metrics import NVD_REFRESHES
        NVD_REFRESHES.labels(result="fresh").inc()
        return self._digest(state, refreshed=True)
