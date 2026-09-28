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
"""

from __future__ import annotations

import os
import platform
import random
import shutil
import subprocess
import time
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

from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


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


class Browser:
    """
    Example:
        browser = Browser(headless=False, incognito=True)
        driver, name = browser.launch("Chrome")
        driver.get("https://example.com")
        browser.quit()
    """

    # FIX: Opera was missing though launch() supports it
    SUPPORTED = ["Chrome", "Brave", "Opera", "Edge","Firefox"]

    _WINDOW_SIZES = [
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1600, 900),
    ]

    def __init__(
        self,
        headless: bool = False,
        user_agent: str | None = None,
        window_size: tuple[int, int] | None = None,
        user_data_dir: str | None = None,
        use_undetected_firefox: bool = True,
        # incognito: bool = False,
    ):
        self.headless = headless
        self.user_agent = user_agent
        # FIX: honour caller window_size; otherwise random. Never set to False.
        self.window_size = window_size or random.choice(self._WINDOW_SIZES)
        self.use_undetected_firefox = use_undetected_firefox
        # self.incognito = incognito

        base = Path(user_data_dir or (Path.home() / ".browser_profiles"))
        base.mkdir(parents=True, exist_ok=True)

        self.profile_root = base
        self.driver = None
        self.browser_name = None
        self._opera_service = None

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
            if item and os.path.isfile(os.path.expandvars(item)):
                return os.path.expandvars(item)
        return None

    @staticmethod
    def _run_version(binary: str) -> str | None:
        try:
            result = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return (result.stdout or result.stderr).strip()
        except Exception:
            pass
        return None

    @classmethod
    def _major_version(cls, binary: str | None) -> int | None:
        if not binary:
            return None
        text = cls._run_version(binary)
        if not text:
            return None
        import re
        match = re.search(r"(\d+)(?:\.\d+){1,3}", text)
        return int(match.group(1)) if match else None

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

        # FIX: incognito now controlled by self.incognito (default False).
        # if self.incognito:
        if browser.lower() == "edge":
            options.add_argument("--inprivate")
        else:
            options.add_argument("--incognito")
        options.add_argument("--disable-session-crashed-bubble")
        options.add_argument("--disable-features=InfiniteSessionRestore")
        # else:
        #     # Persistent profile per browser to avoid lock conflicts.
        #     options.add_argument(f"--user-data-dir={self._profile(browser)}")

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
        time.sleep(random.uniform(0.4, 1.0))

    # ---------------- executables ---------------- #

    def _chrome_binary(self):
        system = platform.system()
        if system == "Windows":
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ])
        if system == "Darwin":
            return self._find_existing([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ])
        return self._which("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")

    def _brave_binary(self):
        system = platform.system()
        if system == "Windows":
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ])
        if system == "Darwin":
            return self._find_existing([
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            ])
        return self._which("brave-browser", "brave-browser-stable", "brave")

    def _opera_binary(self):
        system = platform.system()
        if system == "Windows":
            return self._find_existing([
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Opera\opera.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Opera\launcher.exe"),
            ])
        if system == "Darwin":
            return self._find_existing(["/Applications/Opera.app/Contents/MacOS/Opera"])
        return self._which("opera", "opera-stable")

    def _edge_binary(self):
        system = platform.system()
        if system == "Windows":
            return self._find_existing([
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ])
        if system == "Darwin":
            return self._find_existing([
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ])
        return self._which("microsoft-edge", "microsoft-edge-stable")

    # ---------------- public entry ---------------- #

    def launch(self, browser_name: str | None = None):
        mapping = {
            "firefox": self.get_firefox,
            "chrome": self.get_chrome,
            "brave": self.get_brave,
            "opera": self.get_opera,
            "edge": self.get_edge,
        }

        # IMPORTANT:
        # Default to Chrome instead of randomly selecting a browser.
        requested = browser_name or "Chrome"

        key = requested.strip().lower()

        if key not in mapping:
            raise ValueError(
                f"Unsupported browser '{browser_name}'. "
                f"Choose from {list(mapping.keys())}"
            )

        self.browser_name = key

        print(
            f"[Browser] Starting {requested}..."
        )

        try:
            self.driver = mapping[key]()

        except Exception as error:

            print(
                f"[Browser] Failed to start {requested}: {error}"
            )

            # Make sure a partially created driver doesn't remain.
            self.driver = None
            self.browser_name = None

            raise

        print(
            f"[Browser] {requested} started successfully."
        )

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
        # if not self.incognito:
        #     kwargs["user_data_dir"] = self._profile("chrome")
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
        # if not self.incognito:
        #     kwargs["user_data_dir"] = self._profile("brave")
        if version:
            kwargs["version_main"] = version

        driver = uc.Chrome(**kwargs)
        self._inject_cdp(driver)
        self._finalize(driver)
        return driver

    # ---------------- opera ---------------- #

    def _opera_driver_binary(self):
        candidates = [
            os.environ.get("OPERADRIVER"),
            self._which("operadriver"),
        ]
        wdm_root = Path.home() / ".wdm" / "drivers" / "operadriver"
        if wdm_root.exists():
            try:
                matches = sorted(
                    (p for p in wdm_root.rglob("operadriver") if p.is_file()),
                    key=lambda p: p.stat().st_mtime, reverse=True,
                )
                candidates.extend(str(p) for p in matches)
            except OSError:
                pass
        return self._find_existing(candidates)

    def get_opera(self):
        binary = self._opera_binary()
        if not binary:
            raise FileNotFoundError("Opera was not found.")
        driver_binary = self._opera_driver_binary()
        if not driver_binary:
            raise FileNotFoundError(
                "OperaDriver was not found. Set OPERADRIVER env var."
            )

        options = ChromeOptions()
        options.binary_location = binary
        self._apply_chromium_options(options, "opera")
        options.add_experimental_option("w3c", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=0")

        service = ChromeService(executable_path=driver_binary)
        service.start()
        driver = webdriver.Remote(command_executor=service.service_url, options=options)
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

        driver = None
        try:
            driver = webdriver.Edge(options=options)
        except Exception as first_error:
            try:
                service = EdgeService(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=options)
            except Exception as second_error:
                raise RuntimeError(
                    "Unable to start EdgeDriver.\n"
                    f"Selenium Manager error: {first_error}\n"
                    f"webdriver-manager error: {second_error}"
                ) from second_error

        self._inject_cdp(driver)
        self._finalize(driver)
        return driver

    # ---------------- firefox ---------------- #

    @staticmethod
    def _load_undetected_firefox():
        """
        Load undetected-geckodriver and make it recognize the
        manually installed Mozilla Firefox directory.

        undetected-geckodriver 1.0.7 searches for Firefox before
        applying options.binary_location, so we patch its runtime
        path lookup instead of modifying site-packages.
        """
        try:
            import undetected_geckodriver.driver as ug_driver
            from undetected_geckodriver import Firefox as UndetectedFirefox

            firefox_install_dir = "/home/suntec/firefox-mozilla"

            original_get_params = ug_driver.get_platform_dependent_params

            # Avoid patching the function more than once.
            if not getattr(
                ug_driver,
                "_e225_firefox_path_patched",
                False
            ):

                def patched_get_params():
                    params = original_get_params()

                    # Make a copy so we don't modify the package's
                    # original dictionary permanently.
                    params = dict(params)

                    firefox_paths = list(
                        params.get("firefox_paths", [])
                    )

                    if firefox_install_dir not in firefox_paths:
                        firefox_paths.insert(
                            0,
                            firefox_install_dir
                        )

                    params["firefox_paths"] = firefox_paths

                    return params

                ug_driver.get_platform_dependent_params = (
                    patched_get_params
                )

                ug_driver._e225_firefox_path_patched = True

            print(
                "[firefox] undetected-geckodriver loaded"
            )

            print(
                f"[firefox] Firefox installation: "
                f"{firefox_install_dir}"
            )

            return UndetectedFirefox

        except Exception as exc:
            print(
                f"[firefox] Could not load "
                f"undetected-geckodriver: {exc}"
            )
            return None
    def get_firefox(self):
        profile_path = self._profile("firefox")
        options = FirefoxOptions()

        # ============================================================
        # Firefox binary
        # ============================================================
        firefox_binary = "/home/suntec/firefox-mozilla/firefox"

        if os.path.isfile(firefox_binary):
            options.binary_location = firefox_binary
            print(f"[firefox] Using Firefox binary: {firefox_binary}")
        else:
            raise FileNotFoundError(
                f"Firefox binary not found: {firefox_binary}"
            )

        # ============================================================
        # Headless
        # ============================================================
        if self.headless:
            options.add_argument("-headless")

        # ============================================================
        # Window size
        # ============================================================
        if self.window_size:
            w, h = self.window_size
            options.add_argument(f"--width={w}")
            options.add_argument(f"--height={h}")

        # ============================================================
        # User agent
        # ============================================================
        if self.user_agent:
            options.set_preference(
                "general.useragent.override",
                self.user_agent
            )

        # ============================================================
        # Firefox preferences
        # ============================================================
        options.set_preference(
            "dom.webdriver.enabled",
            False
        )

        options.set_preference(
            "useAutomationExtension",
            False
        )

        options.set_preference(
            "media.navigator.enabled",
            True
        )

        options.set_preference(
            "network.http.sendRefererHeader",
            2
        )

        options.set_preference(
            "privacy.resistFingerprinting",
            False
        )

        # ============================================================
        # Private browsing
        # ============================================================
        # if self.incognito:
        options.add_argument("-private")

        # ============================================================
        # Start Firefox
        # ============================================================
        # if self.use_undetected_firefox:
        #     UndetectedFirefox = self._load_undetected_firefox()

        #     if UndetectedFirefox is not None:
        #         try:
        #             print("[firefox] Starting undetected Firefox...")

        #             driver = UndetectedFirefox(
        #                 options=options
        #             )

        #             self._finalize(driver)
        #             return driver

        #         except Exception as exc:
        #             print(
        #                 f"[firefox] undetected-geckodriver failed; "
        #                 f"fallback: {exc}"
        #             )

        if self.use_undetected_firefox:
            UndetectedFirefox = self._load_undetected_firefox()

            if UndetectedFirefox is not None:
                try:
                    print("[firefox] Starting undetected Firefox...")
                    print(
                        "[firefox] Binary:",
                        options.binary_location
                    )

                    # undetected-geckodriver 1.0.7 searches for the
                    # Firefox installation directory itself.
                    # Add the manually installed Mozilla Firefox location
                    # to its Linux search paths before creating the driver.
                    import undetected_geckodriver.constants as ug_constants

                    firefox_install_dir = "/home/suntec/firefox-mozilla"

                    if hasattr(ug_constants, "LINUX"):
                        linux_config = ug_constants.LINUX

                        if "firefox_paths" in linux_config:
                            paths = linux_config["firefox_paths"]

                            if firefox_install_dir not in paths:
                                paths.insert(0, firefox_install_dir)

                    driver = UndetectedFirefox(
                        options=options
                    )

                    self._finalize(driver)
                    return driver

                except Exception as exc:
                    print(
                        f"[firefox] undetected-geckodriver failed; "
                        f"fallback: {exc}"
                    )

        # ============================================================
        # Normal Selenium Firefox
        # ============================================================
        print("[firefox] Starting Selenium Firefox...")

        service = FirefoxService(
            GeckoDriverManager().install()
        )

        driver = webdriver.Firefox(
            service=service,
            options=options
        )

        # ============================================================
        # Hide webdriver property
        # ============================================================
        try:
            driver.execute_script(
                """
                Object.defineProperty(
                    Navigator.prototype,
                    'webdriver',
                    {
                        get: () => undefined
                    }
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
                "window.scrollBy({top: arguments[0], behavior: 'smooth'});", delta,
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
                    body, random.randint(10, max_x), random.randint(10, max_y),
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
            try:
                subprocess.run(["pkill", "-f", "brave"], check=False)
                print("Killed leftover brave processes.")
            except Exception as exc:
                print(f"pkill brave error: {exc}")


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