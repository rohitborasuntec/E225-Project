# src/vpn/vpn_automation.py
"""
ExpressVPN CLI wrapper with friendly-name -> CLI-slug translation and a
verified connect() that raises when the tunnel is not actually up.

The tiered LocationManager (location_manager.py) is the source of truth for
which location to try.  This class only knows how to talk to expressvpnctl.
"""

import platform
import re
import shutil
import subprocess
import time

from src.logging import logger


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
        if self.system == "Windows":
            self.cli = self.find_windows_cli()
        elif self.system == "Linux":
            self.cli = self.find_linux_cli()
        else:
            raise RuntimeError(f"Unsupported operating system: {self.system}")
        logger.info(f"ExpressVPN CLI: {self.cli}")

    # ------------------------------------------------------------------ #
    # CLI discovery
    # ------------------------------------------------------------------ #
    def find_windows_cli(self):
        possible_paths = [
            r"C:\Program Files (x86)\ExpressVPN\services\expressvpnctl.exe",
            r"C:\Program Files\ExpressVPN\expressvpnctl.exe",
            r"C:\Program Files\ExpressVPN\services\expressvpnctl.exe",
        ]
        for path in possible_paths:
            if shutil.os.path.exists(path):
                return path
        cli = shutil.which("expressvpnctl")
        if cli:
            return cli
        raise FileNotFoundError("expressvpnctl.exe was not found on Windows.")

    def find_linux_cli(self):
        possible_paths = [
            "/usr/local/bin/expressvpnctl",
            "/opt/expressvpn/bin/expressvpnctl",
        ]
        for path in possible_paths:
            if shutil.os.path.exists(path):
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
    def run(self, *args):
        command = [self.cli, *args]
        logger.info("Running: " + " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stdout:
            logger.debug(result.stdout.strip())
        if result.stderr:
            logger.warning(result.stderr.strip())
        if result.returncode != 0:
            raise RuntimeError(f"ExpressVPN command failed: {command}")
        return result.stdout

    # ------------------------------------------------------------------ #
    # connect / disconnect / status
    # ------------------------------------------------------------------ #
    def connect(self, location_display: str, wait: int = 5):
        if self.system == "Linux":
            self.run("background", "enable")

        slug = self.to_cli_slug(location_display)
        logger.info(
            f"[ExpressVPN] Connecting to '{location_display}' (slug={slug})"
        )

        try:
            self.run("connect", slug)
        except RuntimeError:
            logger.warning(
                f"[ExpressVPN] slug '{slug}' rejected, retrying with display name"
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

    def disconnect(self):
        try:
            return self.run("disconnect")
        except RuntimeError as e:
            logger.warning(f"[ExpressVPN] disconnect failed: {e}")
            return ""

    def status(self):
        return self.run("status")

    def locations(self):
        return self.run("get", "regions")


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