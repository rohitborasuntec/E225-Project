"""
browser_manager.py
------------------
Unified Selenium browser manager with working incognito/private mode.

Browser strategy
----------------
Chrome / Brave : undetected-chromedriver (UC)
Opera          : OperaDriver via webdriver.Remote() (UC rejects "chrome" browserName)
Edge           : Microsoft EdgeDriver / Selenium Manager
Firefox        : Optional undetected-geckodriver-lw; otherwise normal GeckoDriver

Incognito mode
--------------
Pass incognito=True to Browser(). When enabled we deliberately do NOT set
--user-data-dir (a persistent profile silently overrides --incognito) and
we do NOT pass user_data_dir to UC.
Firefox uses -private (not --incognito).

Windows / Linux / macOS are all supported.

Performance notes (v2)
----------------------
- Uses Selenium Manager (built into Selenium 4.6+) instead of webdriver-manager
  for Edge and Firefox. Selenium Manager caches drivers under ~/.cache/selenium
  and skips the GitHub round-trip on warm runs.
- Browser major-version detection is cached per-binary, so we spawn
  `chrome --version` at most once per process.
- OperaDriver lookup is cached at module level (no more rglob on every launch).
- Opera uses ChromeService directly via webdriver.Remote (no manual .start()).
- _finalize() sleep reduced and made skippable.
"""

from __future__ import annotations

import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"


STEALTH_JS = r"""
(() => {
    try {
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: () => undefined, configurable: true
        });
    } catch (_) {}
    try {
        Object.defineProperty(Navigator.prototype, 'languages', {
            get: () => ['en-US', 'en'], configurable: true
        });
    } catch (_) {}
    try {
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {};
    } catch (_) {}
    try {
        const originalQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (parameters) => {
            if (parameters && parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return originalQuery(parameters);
        };
    } catch (_) {}
    try {
        const patchWebGL = (proto) => {
            if (!proto || !proto.getParameter) return;
            const original = proto.getParameter;
            proto.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return original.call(this, parameter);
            };
        };
        patchWebGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
        patchWebGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);
    } catch (_) {}
    try {
        Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {
            get: () => 8, configurable: true
        });
    } catch (_) {}
    try {
        Object.defineProperty(Navigator.prototype, 'deviceMemory', {
            get: () => 8, configurable: true
        });
    } catch (_) {}
    try {
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    } catch (_) {}
})();
"""


# ---------------------------------------------------------------------------
# Module-level caches (survive across Browser() instances in the same process)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _cached_major_version(binary: str) -> int | None:
    """Run `<binary> --version` once per binary path per process."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        if result.returncode == 0:
            text = (result.stdout or result.stderr).strip()
            match = re.search(r"(\d+)(?:\.\d+){1,3}", text)
            return int(match.group(1)) if match else None
    except Exception:
        pass
    return None


@lru_cache(maxsize=1)
def _cached_operadriver() -> str | None:
    """
    Find OperaDriver once per process. Avoids the rglob over ~/.wdm on
    every launch.
    """
    candidates: list[str] = []
    if os.environ.get("OPERADRIVER"):
        candidates.append(os.environ["OPERADRIVER"])
    which = shutil.which("operadriver") or shutil.which("operadriver.exe")
    if which:
        candidates.append(which)

    # webdriver-manager cache: ~/.wdm/drivers/operadriver/<os>/<ver>/...
    wdm_root = Path.home() / ".wdm" / "drivers" / "operadriver"
    if wdm_root.exists():
        try:
            exe_name = "operadriver.exe" if IS_WINDOWS else "operadriver"
            matches = sorted(
                (p for p in wdm_root.rglob(exe_name) if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            candidates.extend(str(p) for p in matches)
        except OSError:
            pass

    for item in candidates:
        if not item:
            continue
        expanded = os.path.expandvars(item)
        if os.path.isfile(expanded):
            return expanded
    return None


class Browser:
    """
    Example:
        browser = Browser(headless=False, incognito=True)
        driver, name = browser.launch("Chrome")
        driver.get("https://example.com")
        browser.quit()
    """

    SUPPORTED = ["Chrome", "Brave", "Opera", "Edge", "Firefox"]

    _WINDOW_SIZES = [
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1600, 900),
    ]

    # Optional override for the Firefox install directory, used by
    # undetected-geckodriver. If None, auto-detected per-OS.
    FIREFOX_INSTALL_DIR: str | None = None

    def __init__(
        self,
        headless: bool = False,
        user_agent: str | None = None,
        window_size: tuple[int, int] | None = None,
        user_data_dir: str | None = None,
        use_undetected_firefox: bool = True,
        firefox_install_dir: str | None = None,
        post_launch_delay: tuple[float, float] = (0.1, 0.3),
        done_browser: list[str] | None = None,
    ):
        if done_browser is None:
            done_browser = []

        self.SUPPORTED = [
            browser for browser in self.SUPPORTED
            if browser not in done_browser
        ]
        self.headless = headless
        self.user_agent = user_agent
        self.window_size = window_size or random.choice(self._WINDOW_SIZES)
        self.use_undetected_firefox = use_undetected_firefox
        self.post_launch_delay = post_launch_delay

        base = Path(user_data_dir or (Path.home() / ".browser_profiles"))
        base.mkdir(parents=True, exist_ok=True)

        self.profile_root = base
        self.driver = None
        self.browser_name = None
        self._opera_service = None

        if firefox_install_dir:
            type(self).FIREFOX_INSTALL_DIR = firefox_install_dir

    # ---------------- helpers ---------------- #

    @staticmethod
    def _which(*names: str) -> str | None:
        for name in names:
            path = shutil.which(name)
            if path:
                return path
        return None

    @staticmethod
    def _find_existing(paths: list[str]) -> str | None:
        for item in paths:
            if not item:
                continue
            expanded = os.path.expandvars(item)
            if os.path.isfile(expanded):
                return expanded
        return None

    @classmethod
    def _major_version(cls, binary: str | None) -> int | None:
        if not binary:
            return None
        return _cached_major_version(binary)

    def _profile(self, browser: str) -> str:
        path = self.profile_root / browser.lower()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _add_window_options(self, options) -> None:
        if self.window_size:
            w, h = self.window_size
            options.add_argument(f"--window-size={w},{h}")
        if self.headless:
            options.add_argument("--headless=new")

    def _apply_chromium_options(self, options, browser: str) -> None:
        self._add_window_options(options)

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-first-run")
        options.add_argument("--lang=en-US,en")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-background-timer-throttling")

        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")

        if browser.lower() == "edge":
            options.add_argument("--inprivate")
        else:
            options.add_argument("--incognito")
        options.add_argument("--disable-session-crashed-bubble")
        options.add_argument("--disable-features=InfiniteSessionRestore")

    @staticmethod
    def _inject_cdp(driver) -> None:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS},
            )
        except Exception as exc:
            print(f"[stealth] CDP pre-navigation injection unavailable: {exc}")

    def _finalize(self, driver) -> None:
        if self.window_size and hasattr(driver, "set_window_size"):
            try:
                driver.set_window_size(*self.window_size)
            except Exception:
                pass
        lo, hi = self.post_launch_delay
        if hi > 0:
            time.sleep(random.uniform(lo, hi))

    @staticmethod
    def _kill_by_name(image_name: str) -> None:
        """Cross-platform 'kill everything named <image_name>' helper."""
        try:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/F", "/IM", image_name],
                    check=False,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                # -x matches the exact process name, avoiding false positives
                # like a python script whose path contains "brave".
                proc_name = image_name
                subprocess.run(
                    ["pkill", "-x", proc_name],
                    check=False,
                    capture_output=True,
                )
            print(f"Killed leftover {image_name} processes.")
        except Exception as exc:
            print(f"kill {image_name} error: {exc}")

    # ---------------- executables ---------------- #

    def _chrome_binary(self):
        if IS_WINDOWS:
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ])
        if IS_MAC:
            return self._find_existing([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ])
        return self._which("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")

    def _brave_binary(self):
        if IS_WINDOWS:
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ])
        if IS_MAC:
            return self._find_existing([
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            ])
        return self._which("brave-browser", "brave-browser-stable", "brave")

    def _opera_binary(self):
        if IS_WINDOWS:
            return self._find_existing([
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Opera\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Opera\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Opera\launcher.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
            ])
        if IS_MAC:
            return self._find_existing(["/Applications/Opera.app/Contents/MacOS/Opera"])
        return self._which("opera", "opera-stable")

    def _edge_binary(self):
        if IS_WINDOWS:
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ])
        if IS_MAC:
            return self._find_existing([
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ])
        return self._which("microsoft-edge", "microsoft-edge-stable")

    def _firefox_install_dir(self) -> str | None:
        """
        Return the *directory* that contains the Firefox binary.
        undetected-geckodriver wants the install dir, not the exe.
        """
        if self.FIREFOX_INSTALL_DIR and os.path.isdir(self.FIREFOX_INSTALL_DIR):
            return self.FIREFOX_INSTALL_DIR

        candidates: list[str] = []
        if IS_WINDOWS:
            candidates += [
                os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Mozilla Firefox"),
                os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox"),
            ]
        elif IS_MAC:
            candidates += ["/Applications/Firefox.app/Contents/MacOS"]
        else:
            candidates += [
                "/home/suntec/firefox-mozilla",
                "/opt/firefox",
                "/usr/lib/firefox",
                "/usr/lib64/firefox",
            ]

        for c in candidates:
            exe = os.path.join(c, "firefox.exe" if IS_WINDOWS else "firefox")
            if os.path.isfile(exe):
                return c
        return None

    def _firefox_binary(self) -> str | None:
        install_dir = self._firefox_install_dir()
        if not install_dir:
            return self._which("firefox")
        exe = "firefox.exe" if IS_WINDOWS else "firefox"
        full = os.path.join(install_dir, exe)
        return full if os.path.isfile(full) else None

    # ---------------- public entry ---------------- #

    def launch(self, browser_name: str | None = None):
        mapping = {
            "firefox": self.get_firefox,
            "chrome": self.get_chrome,
            "brave": self.get_brave,
            "opera": self.get_opera,
            "edge": self.get_edge,
        }

        requested = browser_name or random.choice(self.SUPPORTED)
        key = requested.strip().lower()

        if key not in mapping:
            raise ValueError(
                f"Unsupported browser '{browser_name}'. "
                f"Choose from {list(mapping.keys())}"
            )

        self.browser_name = key
        print(f"[Browser] Starting {requested}...")

        t0 = time.perf_counter()
        try:
            self.driver = mapping[key]()
        except Exception as error:
            print(f"[Browser] Failed to start {requested}: {error}")
            self.driver = None
            self.browser_name = None
            raise

        elapsed = time.perf_counter() - t0
        print(f"[Browser] {requested} started successfully in {elapsed:.2f}s.")
        return self.driver, requested

    # ---------------- chrome / brave ---------------- #

    def get_chrome(self):
        options = uc.ChromeOptions()
        binary = self._chrome_binary()
        if binary:
            options.binary_location = binary
        self._apply_chromium_options(options, "chrome")
        version = self._major_version(binary)

        kwargs = {"options": options, "headless": self.headless, "use_subprocess": True}
        if version:
            kwargs["version_main"] = version
        if binary:
            kwargs["browser_executable_path"] = binary

        driver = uc.Chrome(**kwargs)
        self._inject_cdp(driver)
        self._finalize(driver)
        return driver

    def get_brave(self):
        binary = self._brave_binary()
        if not binary:
            raise FileNotFoundError("Brave was not found.")

        options = uc.ChromeOptions()
        options.binary_location = binary
        self._apply_chromium_options(options, "brave")
        version = self._major_version(binary)

        kwargs = {
            "options": options,
            "browser_executable_path": binary,
            "headless": self.headless,
            "use_subprocess": True,
        }
        if version:
            kwargs["version_main"] = version

        driver = uc.Chrome(**kwargs)
        self._inject_cdp(driver)
        self._finalize(driver)
        return driver

    # ---------------- opera ---------------- #

    def _opera_driver_binary(self):
        return _cached_operadriver()

    def get_opera(self):
        binary = self._opera_binary()
        if not binary:
            raise FileNotFoundError("Opera was not found.")
        driver_binary = self._opera_driver_binary()
        if not driver_binary:
            raise FileNotFoundError("OperaDriver was not found. Set OPERADRIVER env var.")

        options = ChromeOptions()
        options.binary_location = binary
        self._apply_chromium_options(options, "opera")
        options.add_experimental_option("w3c", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        service = ChromeService(executable_path=driver_binary)
        service.start()                      # <-- the missing step
        try:
            driver = webdriver.Remote(
                command_executor=service.service_url,
                options=options,
            )
        except Exception:
            service.stop()                   # don't leak a stray operadriver process
            raise

        self._opera_service = service
        self._inject_cdp(driver)
        self._finalize(driver)
        return driver
    # ---------------- edge ---------------- #

    def get_edge(self):
        binary = self._edge_binary()
        options = EdgeOptions()
        options.use_chromium = True
        if binary:
            options.binary_location = binary
        self._apply_chromium_options(options, "edge")
        try:
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
        except AttributeError:
            options.set_capability("excludeSwitches", ["enable-automation"])

        # Selenium Manager (built into Selenium 4.6+) handles driver resolution
        # and caches it under ~/.cache/selenium. No webdriver-manager call.
        try:
            driver = webdriver.Edge(options=options)
        except Exception as first_error:
            # Only fall back to a manual EdgeService if we can find a driver
            # without another network hit.
            service = self._edge_service_from_cache()
            if service is None:
                raise RuntimeError(
                    f"Unable to start EdgeDriver via Selenium Manager: {first_error}"
                ) from first_error
            driver = webdriver.Edge(service=service, options=options)

        self._inject_cdp(driver)
        self._finalize(driver)
        return driver

    @staticmethod
    def _edge_service_from_cache():
        """Look for msedgedriver in common cache locations (no network)."""
        exe_name = "msedgedriver.exe" if IS_WINDOWS else "msedgedriver"
        candidates: list[Path] = []

        # Selenium Manager cache
        for root in [
            Path.home() / ".cache" / "selenium",
            Path.home() / "AppData" / "Local" / "selenium",
        ]:
            if root.exists():
                candidates.extend(root.rglob(exe_name))

        # webdriver-manager cache (if it was used before)
        wdm = Path.home() / ".wdm" / "drivers" / "edgedriver"
        if wdm.exists():
            candidates.extend(wdm.rglob(exe_name))

        matches = [p for p in candidates if p.is_file()]
        if not matches:
            return None
        newest = max(matches, key=lambda p: p.stat().st_mtime)
        return EdgeService(executable_path=str(newest))

    # ---------------- firefox ---------------- #

    @staticmethod
    def _load_undetected_firefox(firefox_install_dir: str | None):
        """
        Load undetected-geckodriver and make it recognize the
        manually installed Mozilla Firefox directory.
        """
        try:
            import undetected_geckodriver.constants as ug_constants
            from undetected_geckodriver import Firefox as UndetectedFirefox
        except Exception as exc:
            print(f"[firefox] Could not import undetected-geckodriver: {exc}")
            return None

        try:
            if firefox_install_dir:
                table = ug_constants.WINDOWS if IS_WINDOWS else ug_constants.LINUX
                if isinstance(table, dict) and "firefox_paths" in table:
                    paths = list(table["firefox_paths"])
                    if firefox_install_dir not in paths:
                        paths.insert(0, firefox_install_dir)
                    table["firefox_paths"] = paths
                elif hasattr(table, "firefox_paths"):
                    paths = list(table.firefox_paths)
                    if firefox_install_dir not in paths:
                        paths.insert(0, firefox_install_dir)
                    table.firefox_paths = paths

                print(
                    f"[firefox] undetected-geckodriver loaded "
                    f"(install dir: {firefox_install_dir})"
                )
            else:
                print("[firefox] undetected-geckodriver loaded (no path patch)")
        except Exception as exc:
            print(f"[firefox] Could not patch undetected-geckodriver paths: {exc}")

        return UndetectedFirefox

    def get_firefox(self):
        options = FirefoxOptions()

        # ---------- Firefox binary ----------
        firefox_binary = self._firefox_binary()
        if not firefox_binary:
            raise FileNotFoundError(
                "Firefox was not found. Install Firefox or pass "
                "firefox_install_dir= to Browser()."
            )
        options.binary_location = firefox_binary
        print(f"[firefox] Using Firefox binary: {firefox_binary}")

        # ---------- Headless ----------
        if self.headless:
            options.add_argument("-headless")

        # ---------- Window size ----------
        if self.window_size:
            w, h = self.window_size
            options.add_argument(f"--width={w}")
            options.add_argument(f"--height={h}")

        # ---------- User agent ----------
        if self.user_agent:
            options.set_preference("general.useragent.override", self.user_agent)

        # ---------- Preferences ----------
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference("media.navigator.enabled", True)
        options.set_preference("network.http.sendRefererHeader", 2)
        options.set_preference("privacy.resistFingerprinting", False)

        # ---------- Private browsing ----------
        options.add_argument("-private")

        # ---------- Try undetected-geckodriver first ----------
        if self.use_undetected_firefox:
            install_dir = os.path.dirname(firefox_binary)
            UndetectedFirefox = self._load_undetected_firefox(install_dir)

            if UndetectedFirefox is not None:
                try:
                    print("[firefox] Starting undetected Firefox...")
                    driver = UndetectedFirefox(options=options)
                    self._finalize(driver)
                    return driver
                except Exception as exc:
                    print(
                        f"[firefox] undetected-geckodriver failed; "
                        f"fallback: {exc}"
                    )

        # ---------- Normal Selenium Firefox ----------
        # Selenium Manager resolves geckodriver (cached under ~/.cache/selenium).
        print("[firefox] Starting Selenium Firefox...")
        driver = webdriver.Firefox(options=options)

        try:
            driver.execute_script(
                """
                Object.defineProperty(
                    Navigator.prototype,
                    'webdriver',
                    { get: () => undefined }
                );
                """
            )
        except Exception:
            pass

        self._finalize(driver)
        return driver

    # ---------------- human helpers ---------------- #

    @staticmethod
    def human_type(driver, css_selector: str, text: str, wpm: int = 220):
        element = driver.find_element(By.CSS_SELECTOR, css_selector)
        element.click()
        time.sleep(random.uniform(0.2, 0.6))
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.03, 0.10))
        time.sleep(random.uniform(0.1, 0.4))

    @staticmethod
    def human_scroll(driver, steps: int = 5):
        for _ in range(steps):
            delta = random.randint(200, 700)
            driver.execute_script(
                "window.scrollBy({top: arguments[0], behavior: 'smooth'});",
                delta,
            )
            time.sleep(random.uniform(0.3, 1.0))

    @staticmethod
    def human_mouse_wander(driver, moves: int = 4):
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            size = driver.get_window_size()
            max_x = max(20, size["width"] - 30)
            max_y = max(20, size["height"] - 30)
            for _ in range(moves):
                ActionChains(driver).move_to_element_with_offset(
                    body,
                    random.randint(10, max_x),
                    random.randint(10, max_y),
                ).pause(random.uniform(0.2, 0.7)).perform()
        except Exception:
            pass

    # ---------------- cleanup ---------------- #

    def quit(self, browser_name: str | None = None):
        name = (browser_name or self.browser_name or "").lower()

        if self.driver:
            try:
                self.driver.quit()
                print("WebDriver quit successfully.")
            except Exception as exc:
                print(f"driver.quit() error: {exc}")
            finally:
                self.driver = None

        if name == "opera" and self._opera_service is not None:
            try:
                self._opera_service.stop()
            except Exception as exc:
                print(f"operadriver service.stop() error: {exc}")
            finally:
                self._opera_service = None

        if name == "brave":
            # On Windows the image is brave.exe; on *nix it is brave.
            self._kill_by_name("brave.exe" if IS_WINDOWS else "brave")


if __name__ == "__main__":
    manager = Browser(headless=False)
    driver, launched = manager.launch("Firefox")
    try:
        driver.get("https://www.google.com")
        time.sleep(random.uniform(1.5, 3.0))
        manager.human_mouse_wander(driver, moves=3)
        selector = "textarea[name=q], input[name=q]"
        try:
            manager.human_type(driver, selector, "python tutorial")
            driver.find_element(By.CSS_SELECTOR, selector).send_keys(Keys.ENTER)
        except Exception as exc:
            print(f"[demo] Search interaction failed: {exc}")
        time.sleep(random.uniform(2.0, 4.0))
        print(f"Browser: {launched}\nTitle: {driver.title}")
    finally:
        manager.quit(launched)