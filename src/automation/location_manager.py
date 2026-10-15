# src/automation/location_manager.py
"""
Tiered VPN location manager with persistent usage/status tracking.

Reads 'Small Local locations.txt' and tries locations in priority order:
    Tier 1: Small / Local locations   (highest priority)
    Tier 2: Small / Medium Cities
    Tier 3: Medium / Large Cities
    Tier 4: Major Global Cities       (last resort)

Failed locations are permanently blacklisted for the run and never reused.
Successful locations are also marked as used so each attempt runs on a
different VPN endpoint.

NEW: per-location statistics are persisted to 'location_stats.json' so that
usage counts and success/failure status survive across separate runs.
"""

from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.logging import logger


# Location file lives at the project root (two levels up from src/automation/).
LOCATION_FILE = Path(__file__).resolve().parents[2] / "Small Local locations.txt"

# Persistent stats file (also at project root).
STATS_FILE = Path(__file__).resolve().parents[2] / "location_stats.json"


class LocationManager:
    """
    Parses the location file once, then hands out locations tier-by-tier.

    Usage:
        lm = LocationManager()
        while lm.has_next():
            location = lm.next()
            try:
                run_with(location)
                lm.mark_success(location)
                break
            except Exception:
                lm.mark_failed(location)
    """

    # Mapping of section header -> tier name (order matters).
    _SECTIONS = {
        "small / local locations":   "local",
        "small / medium cities":     "small_medium",
        "medium / large cities":     "medium_large",
        "major global cities":       "major",
    }

    TIER_ORDER = ["local", "small_medium", "medium_large", "major"]

    # ---------- tunables ----------
    # If True, locations whose *persisted* last status is "failed" are treated
    # as blacklisted at startup (cross-run blacklist). Set False to always
    # start with a clean failure set.
    CROSS_RUN_BLACKLIST = False

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def __init__(self, file_path: Path | str | None = None):
        self.file_path = Path(file_path) if file_path else LOCATION_FILE
        self._lock = threading.Lock()
        self._tiers: dict[str, list[str]] = {t: [] for t in self.TIER_ORDER}
        self._failed: set[str] = set()
        self._used: set[str] = set()
        self._stats: dict[str, dict] = {}

        self._load_stats()          # load persisted per-location stats
        self._load()                # parse the locations file
        self._load_cross_run_blacklist()   # OPTIONAL

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Location file not found: {self.file_path}"
            )

        text = self.file_path.read_text(encoding="utf-8")
        current_tier: str | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            header = line.lower()
            matched = next(
                (tier for key, tier in self._SECTIONS.items() if key == header),
                None,
            )
            if matched:
                current_tier = matched
                continue

            if current_tier is None:
                continue  # preamble text

            # Split on commas and normalize.
            for entry in line.split(","):
                name = entry.strip()
                if name:
                    self._tiers[current_tier].append(name)

        total = sum(len(v) for v in self._tiers.values())
        logger.info(
            f"[LocationManager] Loaded {total} locations "
            f"({', '.join(f'{t}={len(self._tiers[t])}' for t in self.TIER_ORDER)})"
        )

    # ------------------------------------------------------------------ #
    # Persistent stats
    # ------------------------------------------------------------------ #
    def _load_stats(self) -> None:
        if STATS_FILE.exists():
            try:
                self._stats = json.loads(
                    STATS_FILE.read_text(encoding="utf-8")
                )
                logger.info(
                    f"[LocationManager] Loaded stats for "
                    f"{len(self._stats)} locations from {STATS_FILE.name}"
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"[LocationManager] Could not read {STATS_FILE.name} "
                    f"({e}); starting with empty stats."
                )
                self._stats = {}
        else:
            self._stats = {}

    def _save_stats(self) -> None:
        """Atomic write so a crash mid-write can't corrupt the file."""
        try:
            tmp = STATS_FILE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._stats, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(STATS_FILE)   # atomic on POSIX and Windows
        except OSError as e:
            logger.warning(
                f"[LocationManager] Could not persist stats to "
                f"{STATS_FILE.name}: {e}"
            )

    def _record(self, location: str, status: str) -> None:
        """
        status: 'selected' | 'success' | 'failed'
        """
        entry = self._stats.setdefault(location, {
            "attempts":    0,
            "successes":   0,
            "failures":    0,
            "last_status": None,
            "last_used":   None,
        })

        if status == "selected":
            entry["attempts"] += 1
        elif status == "success":
            entry["successes"] += 1
            entry["last_status"] = "success"
        elif status == "failed":
            entry["failures"] += 1
            entry["last_status"] = "failed"

        if status in ("success", "failed"):
            entry["last_used"] = datetime.now(timezone.utc).isoformat()

        self._save_stats()

    def stats(self) -> dict[str, dict]:
        """Return a copy of the full stats dict."""
        return json.loads(json.dumps(self._stats))  # deep copy

    def stats_for(self, location: str) -> dict | None:
        """Return the stats entry for a single location (or None)."""
        e = self._stats.get(location)
        return dict(e) if e else None

    def _load_cross_run_blacklist(self) -> None:
        """OPTIONAL: seed self._failed from persisted failures."""
        if not self.CROSS_RUN_BLACKLIST:
            return
        seeded = {
            loc for loc, e in self._stats.items()
            if e.get("last_status") == "failed"
        }
        if seeded:
            self._failed |= seeded
            logger.info(
                f"[LocationManager] Cross-run blacklist seeded with "
                f"{len(seeded)} location(s) that failed last run."
            )

    # ------------------------------------------------------------------ #
    # Query API
    # ------------------------------------------------------------------ #
    def tiers(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._tiers.items()}

    def _available_in_tier(self, tier: str) -> list[str]:
        return [
            loc for loc in self._tiers[tier]
            if loc not in self._failed and loc not in self._used
        ]

    def has_next(self) -> bool:
        """True if any non-failed, non-used location remains."""
        with self._lock:
            return any(
                self._available_in_tier(t) for t in self.TIER_ORDER
            )

    def next(self) -> str:
        """
        Return a random unused location, preferring lower tiers.
        Falls through to the next tier only when the current tier is empty.
        Raises StopIteration when nothing is left.
        """
        with self._lock:
            for tier in self.TIER_ORDER:
                candidates = self._available_in_tier(tier)
                if candidates:
                    chosen = random.choice(candidates)
                    self._used.add(chosen)
                    self._record(chosen, "selected")

                    # OPTIONAL: log its history so you can see how it did before.
                    hist = self._stats.get(chosen, {})
                    logger.info(
                        f"[LocationManager] Selected '{chosen}' "
                        f"(tier={tier}, remaining_in_tier={len(candidates) - 1}, "
                        f"attempts={hist.get('attempts', 0)}, "
                        f"successes={hist.get('successes', 0)}, "
                        f"failures={hist.get('failures', 0)})"
                    )
                    return chosen
            raise StopIteration("No unused VPN locations remain")

    # ------------------------------------------------------------------ #
    # Result reporting
    # ------------------------------------------------------------------ #
    def mark_success(self, location: str) -> None:
        with self._lock:
            self._record(location, "success")
            logger.info(f"[LocationManager] SUCCESS: {location}")

    def mark_failed(self, location: str) -> None:
        with self._lock:
            self._failed.add(location)
            self._record(location, "failed")
            logger.warning(
                f"[LocationManager] FAILED (blacklisted): {location}"
            )

    def reset(self) -> None:
        """
        Clear the in-memory failure blacklist and used set for this run.
        Does NOT touch the persisted stats file.
        """
        with self._lock:
            self._failed.clear()
            self._used.clear()

    @property
    def failed(self) -> set[str]:
        return set(self._failed)

    @property
    def used(self) -> set[str]:
        return set(self._used)