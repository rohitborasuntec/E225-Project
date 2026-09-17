"""
browser_manager.py
-------------------
A class-based browser driver manager supporting:
    Firefox, Chrome, Brave, Opera Mini (-> desktop Opera), Edge

Design:
- Chrome / Brave / Opera all sit on top of `undetected_chromedriver` (uc),
  which patches the chromedriver binary to avoid the common
  `navigator.webdriver` / CDP detection signatures. Brave and Opera are
  Chromium forks, so we point `uc.Chrome` at their binaries instead of
  standard Chrome.
- Edge is Chromium-based too, but `undetected_chromedriver` only patches
  *chromedriver*, not *msedgedriver*, so it can't drive Edge. Instead we
  use Selenium's native Edge driver and apply the same stealth flags +
  a CDP call to erase the `navigator.webdriver` flag after load.
- Firefox has no CDP layer and no mainstream "undetected" driver package.
  We approximate the same effect with Firefox preferences
  (`dom.webdriver.enabled`, UA override, disabling the automation
  extension) plus a post-load JS patch.
- "Opera Mini" is a proxy-rendered *mobile* browser with no desktop binary
  and no WebDriver support at all -- it cannot be automated with Selenium
  under any driver. It's mapped to desktop Opera (Chromium-based) here;
  see the docstring on `get_opera()`.

Requirements:
    pip install selenium undetected-chromedriver webdriver-manager
"""

import os,subprocess
import platform

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


class Browser:
    """
    Usage:
        b = Browser(headless=False, user_agent=None, proxy=None)
        driver = b.launch("Chrome")   # or "Firefox" / "Brave" / "Edge" / "Opera Mini"
        driver.get("https://example.com")
        b.quit()
    """

    SUPPORTED = ["Firefox", "Chrome", "Brave", "Opera Mini", "Edge"]

    def __init__(self, headless: bool = False, user_agent: str | None = None, window_size: tuple[int, int] = (1920, 1080)):
        self.headless = headless
        self.user_agent = user_agent
        self.window_size = window_size
        self.driver = None

    # ---------------------------------------------------------------- #
    # Public entrypoint
    # ---------------------------------------------------------------- #
    def launch(self, browser_name: str):
        """Launch the requested browser and return the live driver instance."""
        print("LOOOOL")
        key = browser_name.strip().lower()
        mapping = {
            "firefox": self.get_firefox,
            "chrome": self.get_chrome,
            "brave": self.get_brave,
            "opera mini": self.get_opera,
            "opera": self.get_opera,
            "edge": self.get_edge,
        }
        if key not in mapping:
            raise ValueError(f"Unsupported browser '{browser_name}'. Choose from {self.SUPPORTED}")
        self.driver = mapping[key]()
        return self.driver

    # ---------------------------------------------------------------- #
    # Chrome  (undetected-chromedriver)
    # ---------------------------------------------------------------- #
    def get_chrome(self):
        
        def _get_chrome_version():
            """Get installed Chrome major version"""
            try:
                if platform.system() == "Windows":
                    import winreg
                    try:
                        # Try current user first
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        version = winreg.QueryValueEx(key, "version")[0]
                        return int(version.split('.')[0])
                    except:
                        # Try local machine
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon")
                        version = winreg.QueryValueEx(key, "version")[0]
                        return int(version.split('.')[0])
                        
                elif platform.system() == "Linux":
                    # Try common Chrome executables
                    for cmd in ['google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium']:
                        try:
                            result = subprocess.run([cmd, '--version'], capture_output=True, text=True)
                            if result.returncode == 0:
                                version = result.stdout.strip().split()[-1]
                                return int(version.split('.')[0])
                        except:
                            continue
                            
                elif platform.system() == "Darwin":  # macOS
                    try:
                        result = subprocess.run(
                            ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            version = result.stdout.strip().split()[-1]
                            return int(version.split('.')[0])
                    except:
                        pass
                        
            except Exception as e:
                # logger.debug(f"Could not detect Chrome version: {e}")
                pass
            
            return None


        options = uc.ChromeOptions()
        self._apply_common_chromium_options(options)
        version = _get_chrome_version()
        driver = uc.Chrome(options=options, headless=self.headless, version_main=version)
        self._finalize(driver)
        return driver

    # ---------------------------------------------------------------- #
    # Brave  (Chromium fork -> undetected-chromedriver + custom binary)
    # ---------------------------------------------------------------- #
    def get_brave(self):
        options = uc.ChromeOptions()
        self._apply_common_chromium_options(options)
        brave_path = self._find_binary({
            "Windows": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            "Darwin": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "Linux": "/usr/bin/brave-browser",
        })
        driver = uc.Chrome(
            options=options,
            browser_executable_path=brave_path,
            headless=self.headless,
            use_subprocess=True,
        )
        self._finalize(driver)
        return driver

    # ---------------------------------------------------------------- #
    # Opera / "Opera Mini"
    # ---------------------------------------------------------------- #
    def get_opera(self):
        """
        Opera Mini itself (the real mobile app) proxies pages through
        Opera's own servers for compression and has no desktop build or
        WebDriver support -- Selenium simply cannot drive it. This method
        launches desktop Opera instead (Chromium-based), which is the
        closest automatable equivalent.
        """
        options = uc.ChromeOptions()
        self._apply_common_chromium_options(options)
        opera_path = self._find_binary({
            "Windows": os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            "Darwin": "/Applications/Opera.app/Contents/MacOS/Opera",
            "Linux": "/usr/bin/opera",
        })
        driver = uc.Chrome(
            options=options,
            browser_executable_path=opera_path,
            headless=self.headless,
            use_subprocess=True,
        )
        self._finalize(driver)
        return driver

    # ---------------------------------------------------------------- #
    # Edge  (Chromium-based, but needs msedgedriver -> not uc)
    # ---------------------------------------------------------------- #
    def get_edge(self):
        options = EdgeOptions()
        options.use_chromium = True
        self._apply_common_chromium_options(options)
        if self.headless:
            options.add_argument("--headless=new")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)

        # Same trick undetected-chromedriver uses internally: erase the
        # navigator.webdriver flag before any page script runs.
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self._finalize(driver)
        return driver

    # ---------------------------------------------------------------- #
    # Firefox  (preference-based stealth; no CDP layer available)
    # ---------------------------------------------------------------- #
    def get_firefox(self):
        options = FirefoxOptions()
        if self.headless:
            options.add_argument("--headless")

        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference("general.platform.override", "Win32")
        options.set_preference("privacy.trackingprotection.enabled", True)
        if self.user_agent:
            options.set_preference("general.useragent.override", self.user_agent)
        # if self.proxy:
        #     self._set_firefox_proxy(options)

        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._finalize(driver)
        return driver

    # ---------------------------------------------------------------- #
    # Shared helpers
    # ---------------------------------------------------------------- #
    def _apply_common_chromium_options(self, options):
        if self.window_size:
            w, h = self.window_size
            options.add_argument(f"--window-size={w},{h}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--incognito")

        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")
        # if self.proxy:
        #     options.add_argument(f"--proxy-server={self.proxy}")

    def _finalize(self, driver):
        if self.window_size and hasattr(driver, "set_window_size"):
            driver.set_window_size(*self.window_size)

    # def _set_firefox_proxy(self, options):
    #     host, port = self.proxy.split(":")
    #     options.set_preference("network.proxy.type", 1)
    #     options.set_preference("network.proxy.http", host)
    #     options.set_preference("network.proxy.http_port", int(port))
    #     options.set_preference("network.proxy.ssl", host)
    #     options.set_preference("network.proxy.ssl_port", int(port))

    @staticmethod
    def _find_binary(candidates: dict) -> str | None:
        path = candidates.get(platform.system())
        return path if path and os.path.exists(path) else None

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

if __name__ == "__main__":
    browsers = ["Firefox", "Chrome", "Brave", "Opera Mini", "Edge"]

    manager = Browser(headless=False)
    driver = manager.launch("Chrome")
    driver.get("https://example.com")
    print(driver.title)
    manager.quit()