# src/vpn/vpn_automation.py
"""
ExpressVPN CLI wrapper with friendly-name -> CLI-slug translation and a
verified connect() that raises when the tunnel is not actually up.

The tiered LocationManager (location_manager.py) is the source of truth for
which location to try.  This class only knows how to talk to expressvpnctl.

Cross-platform: Windows and Linux are both supported.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

from src.logging import logger


IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# CREATE_NO_WINDOW is a Windows-only flag; 0 elsewhere.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


class ExpressVPN:
    # Legacy helper (kept for backwards compat); the LocationManager now
    # supplies the location list from the .txt file.
    VPN_LOCATIONS = [
        "usa", "uk", "germany", "spain", "france",
        "netherlands", "canada", "australia", "singapore",
    ]

    # ExpressVPN region slugs sometimes differ from the display name.
    _SLUG_ALIASES = {
        "united states": "usa",
        "united kingdom": "uk",
        "south korea": "south-korea",
        "czech republic": "czech-republic",
    }

    def __init__(self):
        self.system = platform.system()
        if IS_WINDOWS:
            self.cli = self.find_windows_cli()
        elif IS_LINUX:
            self.cli = self.find_linux_cli()
        else:
            raise RuntimeError(f"Unsupported operating system: {self.system}")
        logger.info(f"ExpressVPN CLI: {self.cli}")

    # ------------------------------------------------------------------ #
    # CLI discovery
    # ------------------------------------------------------------------ #
    def find_windows_cli(self) -> str:
        possible_paths = [
            os.path.expandvars(
                r"%PROGRAMFILES%\ExpressVPN\services\expressvpnctl.exe"
            ),
            os.path.expandvars(
                r"%PROGRAMFILES(X86)%\ExpressVPN\services\expressvpnctl.exe"
            ),
            os.path.expandvars(
                r"%PROGRAMFILES%\ExpressVPN\expressvpnctl.exe"
            ),
            os.path.expandvars(
                r"%PROGRAMFILES(X86)%\ExpressVPN\expressvpnctl.exe"
            ),
            os.path.expandvars(
                r"%LOCALAPPDATA%\ExpressVPN\services\expressvpnctl.exe"
            ),
        ]
        for path in possible_paths:
            if os.path.isfile(path):
                return path

        cli = shutil.which("expressvpnctl") or shutil.which("expressvpnctl.exe")
        if cli:
            return cli

        # Last resort: shallow recursive search of Program Files.
        for root in filter(None, [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
        ]):
            base = Path(root)
            if base.is_dir():
                try:
                    for candidate in base.rglob("expressvpnctl.exe"):
                        return str(candidate)
                except OSError:
                    pass

        raise FileNotFoundError("expressvpnctl.exe was not found on Windows.")

    def find_linux_cli(self) -> str:
        possible_paths = [
            "/usr/local/bin/expressvpnctl",
            "/opt/expressvpn/bin/expressvpnctl",
        ]
        for path in possible_paths:
            if os.path.isfile(path):
                return path

        cli = shutil.which("expressvpnctl")
        if cli:
            return cli

        raise FileNotFoundError("expressvpnctl was not found on Linux.")

    # ------------------------------------------------------------------ #
    # Friendly name -> CLI slug
    # ------------------------------------------------------------------ #
    @classmethod
    def to_cli_slug(cls, display_name: str) -> str:
        key = display_name.strip().lower()
        if key in cls._SLUG_ALIASES:
            return cls._SLUG_ALIASES[key]
        slug = re.sub(r"[^a-z0-9\s-]", "", key)
        slug = re.sub(r"\s+", "-", slug.strip())
        return slug

    # ------------------------------------------------------------------ #
    # Raw subprocess wrapper
    # ------------------------------------------------------------------ #
    def run(self, *args, quiet: bool = False) -> str:
        command = [self.cli, *[str(a) for a in args]]
        if not quiet:
            logger.info("Running: " + " ".join(command))

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=False,
            creationflags=_NO_WINDOW,
        )

        if result.stdout and not quiet:
            logger.debug(result.stdout.strip())
        if result.stderr and not quiet:
            logger.warning(result.stderr.strip())
        if result.returncode != 0:
            raise RuntimeError(
                f"ExpressVPN command failed ({result.returncode}): {command}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout or ""

    # ------------------------------------------------------------------ #
    # connect / disconnect / status
    # ------------------------------------------------------------------ #
    def connect(self, location_display: str, wait: int = 5) -> str:
        if IS_LINUX:
            # On Linux the daemon runs in the foreground by default; the
            # Windows service is always resident.
            self.run("background", "enable")

        slug = self.to_cli_slug(location_display)
        logger.info(
            f"[ExpressVPN] Connecting to '{location_display}' (slug={slug})"
        )

        try:
            self.run("connect", slug)
        except RuntimeError as exc:
            logger.warning(
                f"[ExpressVPN] slug '{slug}' rejected ({exc}), "
                f"retrying with display name"
            )
            self.run("connect", location_display)

        time.sleep(wait)
        status = self.status()

        if "Connected" not in status:
            raise RuntimeError(
                f"[ExpressVPN] connect() reported no active connection: {status!r}"
            )
        logger.info(f"[ExpressVPN] Connected via '{location_display}'")
        return status

    def disconnect(self) -> str:
        try:
            return self.run("disconnect", quiet=True)
        except RuntimeError as e:
            logger.warning(f"[ExpressVPN] disconnect failed: {e}")
            return ""

    def status(self) -> str:
        return self.run("status", quiet=True)

    def locations(self) -> str:
        return self.run("get", "regions", quiet=True)


if __name__ == "__main__":
    # Manual smoke test: connect to the first available local location.
    from src.automation.location_manager import LocationManager

    lm = LocationManager()
    vpn = ExpressVPN()
    if lm.has_next():
        loc = lm.next()
        try:
            vpn.connect(loc)
            print(vpn.status())
        finally:
            vpn.disconnect()
    else:
        print("No locations available.")