# src/automation/location_manager.py
"""
Tiered VPN location manager.

Reads 'Small Local locations.txt' and tries locations in priority order:
    Tier 1: Small / Local locations   (highest priority)
    Tier 2: Small / Medium Cities
    Tier 3: Medium / Large Cities
    Tier 4: Major Global Cities       (last resort)

Failed locations are permanently blacklisted for the run and never reused.
Successful locations are also marked as used so each attempt runs on a
different VPN endpoint.
"""

from __future__ import annotations

import random
import threading
from pathlib import Path

from src.logging import logger


# Location file lives at the project root (two levels up from src/automation/).
LOCATION_FILE = Path(__file__).resolve().parents[2] / "Small Local locations.txt"


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

    def __init__(self, file_path: Path | str | None = None):
        self.file_path = Path(file_path) if file_path else LOCATION_FILE
        self._lock = threading.Lock()
        self._tiers: dict[str, list[str]] = {t: [] for t in self.TIER_ORDER}
        self._failed: set[str] = set()
        self._used: set[str] = set()
        self._load()

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
                    logger.info(
                        f"[LocationManager] Selected '{chosen}' "
                        f"(tier={tier}, remaining_in_tier={len(candidates) - 1})"
                    )
                    return chosen
            raise StopIteration("No unused VPN locations remain")

    # ------------------------------------------------------------------ #
    # Result reporting
    # ------------------------------------------------------------------ #
    def mark_success(self, location: str) -> None:
        with self._lock:
            logger.info(f"[LocationManager] SUCCESS: {location}")

    def mark_failed(self, location: str) -> None:
        with self._lock:
            self._failed.add(location)
            logger.warning(
                f"[LocationManager] FAILED (blacklisted): {location}"
            )

    def reset(self) -> None:
        """Clear both the failure blacklist and the used set."""
        with self._lock:
            self._failed.clear()
            self._used.clear()

    @property
    def failed(self) -> set[str]:
        return set(self._failed)

    @property
    def used(self) -> set[str]:
        return set(self._used)