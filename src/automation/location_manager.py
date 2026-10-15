
# src/automation/location_manager.py

"""
Tiered VPN location manager with persistent usage/status tracking.

Selection strategy:
1. First cycle: randomize between local and small_medium locations.
2. When both are exhausted, use medium_large, then major.
3. Never reuse a location within the same cycle.
4. In later cycles, prioritize previously successful locations.
5. Failed locations can be retried in a later cycle.
6. Persist statistics across program runs.
"""

from __future__ import annotations

import json
import random
import threading

from datetime import datetime, timezone
from pathlib import Path

from src.logging import logger


# Project-root paths
LOCATION_FILE = (
    Path(__file__).resolve().parents[2]
    / "Small Local locations.txt"
)

STATS_FILE = (
    Path(__file__).resolve().parents[2]
    / "location_stats.json"
)


class LocationManager:
    """Manage VPN locations using tier priority and cycle-based rotation."""

    _SECTIONS = {
        "small / local locations": "local",
        "small / medium cities": "small_medium",
        "medium / large cities": "medium_large",
        "major global cities": "major",
    }

    TIER_ORDER = [
        "local",
        "small_medium",
        "medium_large",
        "major",
    ]

    # Include failed locations from earlier runs in the current
    # failure blacklist when enabled.
    CROSS_RUN_BLACKLIST = False

    # Maximum number of cycles per manager instance.
    # Set to None to allow unlimited cycles.
    MAX_CYCLES = 2

    def __init__(self, file_path: Path | str | None = None):
        self.file_path = Path(file_path) if file_path else LOCATION_FILE

        self._lock = threading.RLock()

        self._tiers: dict[str, list[str]] = {
            tier: [] for tier in self.TIER_ORDER
        }

        # Locations attempted in the current cycle.
        self._used: set[str] = set()

        # Failed locations in the current cycle.
        self._failed: set[str] = set()

        # Persistent location statistics.
        self._stats: dict[str, dict] = {}

        # Current cycle number, starting at 1.
        self._cycle_number = 1

        # Locations that have succeeded in this or previous runs.
        self._successful: set[str] = set()

        self._load_stats()
        self._load()
        self._load_successful_locations()
        self._load_cross_run_blacklist()

        logger.info(
            f"[LocationManager] Initialized cycle "
            f"#{self._cycle_number}; "
            f"known successful locations={len(self._successful)}"
        )

    # ---------------------------------------------------------- #
    # Location file parsing
    # ---------------------------------------------------------- #

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

            matched_tier = self._SECTIONS.get(header)

            if matched_tier:
                current_tier = matched_tier
                continue

            if current_tier is None:
                continue

            for entry in line.split(","):
                location = entry.strip()

                if location and location not in self._tiers[current_tier]:
                    self._tiers[current_tier].append(location)

        # Remove duplicates across tiers while preserving the first
        # occurrence and its assigned priority.
        seen: set[str] = set()

        for tier in self.TIER_ORDER:
            unique_locations = []

            for location in self._tiers[tier]:
                if location not in seen:
                    unique_locations.append(location)
                    seen.add(location)

            self._tiers[tier] = unique_locations

        total = sum(len(locations) for locations in self._tiers.values())

        logger.info(
            f"[LocationManager] Loaded {total} locations "
            f"({', '.join(f'{tier}={len(self._tiers[tier])}' for tier in self.TIER_ORDER)})"
        )

    # ---------------------------------------------------------- #
    # Persistent statistics
    # ---------------------------------------------------------- #

    def _load_stats(self) -> None:
        if not STATS_FILE.exists():
            self._stats = {}
            return

        try:
            loaded = json.loads(
                STATS_FILE.read_text(encoding="utf-8")
            )

            self._stats = loaded if isinstance(loaded, dict) else {}

            logger.info(
                f"[LocationManager] Loaded statistics for "
                f"{len(self._stats)} locations"
            )

        except (json.JSONDecodeError, OSError) as error:
            logger.warning(
                f"[LocationManager] Could not load "
                f"{STATS_FILE.name}: {error}"
            )
            self._stats = {}

    def _save_stats(self) -> None:
        """Atomically save statistics to avoid partial JSON files."""
        try:
            temporary_file = STATS_FILE.with_suffix(".tmp")

            temporary_file.write_text(
                json.dumps(
                    self._stats,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            temporary_file.replace(STATS_FILE)

        except OSError as error:
            logger.warning(
                f"[LocationManager] Could not save statistics: {error}"
            )

    def _record(self, location: str, status: str) -> None:
        """
        Record a location event.

        status: selected, success, or failed
        """
        entry = self._stats.setdefault(
            location,
            {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_status": None,
                "last_used": None,
            },
        )

        if status == "selected":
            entry["attempts"] += 1

        elif status == "success":
            entry["successes"] += 1
            entry["last_status"] = "success"

        elif status == "failed":
            entry["failures"] += 1
            entry["last_status"] = "failed"

        if status in ("success", "failed"):
            entry["last_used"] = datetime.now(
                timezone.utc
            ).isoformat()

        self._save_stats()

    def _load_successful_locations(self) -> None:
        """Load previously successful locations from persistent history."""
        self._successful = {
            location
            for location, stats in self._stats.items()
            if stats.get("successes", 0) > 0
        }

    def _load_cross_run_blacklist(self) -> None:
        """Optionally blacklist locations that failed in the previous run."""
        if not self.CROSS_RUN_BLACKLIST:
            return

        for location, stats in self._stats.items():
            if stats.get("last_status") == "failed":
                self._failed.add(location)

        if self._failed:
            logger.info(
                f"[LocationManager] Loaded {len(self._failed)} "
                f"locations into the cross-run failure blacklist"
            )

    def stats(self) -> dict[str, dict]:
        """Return a deep copy of all statistics."""
        return json.loads(json.dumps(self._stats))

    def stats_for(self, location: str) -> dict | None:
        """Return statistics for one location."""
        entry = self._stats.get(location)
        return dict(entry) if entry else None

    # ---------------------------------------------------------- #
    # Location queries
    # ---------------------------------------------------------- #

    def tiers(self) -> dict[str, list[str]]:
        """Return a copy of the configured location tiers."""
        return {
            tier: list(locations)
            for tier, locations in self._tiers.items()
        }

    def _available_in_tier(self, tier: str) -> list[str]:
        """Return locations not yet attempted in the current cycle."""
        return [
            location
            for location in self._tiers[tier]
            if location not in self._used
            and location not in self._failed
        ]

    def _all_locations_attempted(self) -> bool:
        """Check whether every configured location was used this cycle."""
        all_locations = {
            location
            for locations in self._tiers.values()
            for location in locations
        }

        return bool(all_locations) and all_locations.issubset(self._used)

    def _start_new_cycle(self) -> bool:
        """
        Start a new cycle once all locations have been attempted.

        Returns False when the configured cycle limit is reached.
        """
        if (
            self.MAX_CYCLES is not None
            and self._cycle_number >= self.MAX_CYCLES
        ):
            logger.info(
                f"[LocationManager] Maximum cycle limit "
                f"({self.MAX_CYCLES}) reached"
            )
            return False

        self._cycle_number += 1
        self._used.clear()
        self._failed.clear()

        logger.info(
            f"[LocationManager] Starting cycle #{self._cycle_number}. "
            f"Previously successful locations will be tried first."
        )

        return True

    def has_next(self) -> bool:
        """
        Return whether a location can be selected.

        Automatically starts the next cycle after every configured
        location has been attempted, subject to MAX_CYCLES.
        """
        with self._lock:
            if any(
                self._available_in_tier(tier)
                for tier in self.TIER_ORDER
            ):
                return True

            if self._all_locations_attempted():
                return self._start_new_cycle()

            return False

    def _choose_by_tier_priority(
        self,
        candidates: dict[str, list[str]],
    ) -> str:
        """
        Randomize local and small_medium as one combined priority pool.
        Fall back to medium_large and then major.
        """
        priority_pool = (
            candidates["local"]
            + candidates["small_medium"]
        )

        if priority_pool:
            return random.choice(priority_pool)

        for tier in ("medium_large", "major"):
            if candidates[tier]:
                return random.choice(candidates[tier])

        raise StopIteration("No available VPN locations")

    def next(self) -> str:
        """
        Select the next location.

        Cycle 1:
            Random local/small_medium pool, then medium_large, then major.

        Later cycles:
            Previously successful locations first, randomized.
            Remaining locations then follow tier priority.
        """
        with self._lock:
            candidates = {
                tier: self._available_in_tier(tier)
                for tier in self.TIER_ORDER
            }

            if not any(candidates.values()):
                if self._all_locations_attempted():
                    if not self._start_new_cycle():
                        raise StopIteration(
                            "Maximum VPN location cycles reached"
                        )

                    candidates = {
                        tier: self._available_in_tier(tier)
                        for tier in self.TIER_ORDER
                    }
                else:
                    raise StopIteration(
                        "No unused VPN locations remain"
                    )

            chosen: str

            if self._cycle_number > 1:
                successful_candidates = [
                    location
                    for tier in self.TIER_ORDER
                    for location in candidates[tier]
                    if location in self._successful
                ]

                if successful_candidates:
                    chosen = random.choice(successful_candidates)

                    logger.info(
                        "[LocationManager] Prioritizing a previously "
                        "successful location"
                    )
                else:
                    chosen = self._choose_by_tier_priority(candidates)

            else:
                chosen = self._choose_by_tier_priority(candidates)

            self._used.add(chosen)
            self._record(chosen, "selected")

            selected_tier = next(
                tier
                for tier in self.TIER_ORDER
                if chosen in self._tiers[tier]
            )

            remaining = sum(
                len(self._available_in_tier(tier))
                for tier in self.TIER_ORDER
            )

            logger.info(
                f"[LocationManager] Selected '{chosen}' "
                f"(tier={selected_tier}, "
                f"cycle={self._cycle_number}, "
                f"remaining={remaining})"
            )

            return chosen

    # ---------------------------------------------------------- #
    # Result reporting
    # ---------------------------------------------------------- #

    def mark_success(self, location: str) -> None:
        """Record success and prioritize this location in later cycles."""
        with self._lock:
            self._successful.add(location)
            self._record(location, "success")

            logger.info(
                f"[LocationManager] SUCCESS: {location}"
            )

    def mark_failed(self, location: str) -> None:
        """Exclude this location from the remainder of the current cycle."""
        with self._lock:
            self._failed.add(location)
            self._record(location, "failed")

            logger.warning(
                f"[LocationManager] FAILED in cycle "
                f"#{self._cycle_number}: {location}"
            )

    def reset(self) -> None:
        """
        Manually reset the current cycle's used and failed sets.

        Persistent statistics and successful-location history are retained.
        """
        with self._lock:
            self._failed.clear()
            self._used.clear()

            logger.info(
                "[LocationManager] Current cycle manually reset"
            )

    @property
    def failed(self) -> set[str]:
        return set(self._failed)

    @property
    def used(self) -> set[str]:
        return set(self._used)

    @property
    def successful(self) -> set[str]:
        return set(self._successful)

    @property
    def cycle_number(self) -> int:
        return self._cycle_number
