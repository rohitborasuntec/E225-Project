import random
import time
import traceback

from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
from src.commons import *
from src.automation.vpn.vpn_automation import ExpressVPN
from src.automation.location_manager import LocationManager
from src.logging import logger
from src.automation.google_work import GoogleSearch
from src.automation.G2_comparison import G2Comparison
from src.automation.G2_page import G2Page
from src.automation.errors import AccessDeniedError,RetryableFailure
from src.excel import Excel


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
# Must match EXACTLY the names Browser.launch() returns / Excel.browser_list()
# stores (case included), otherwise the exclusion silently does nothing.
ALL_BROWSERS = ["chrome", "brave", "opera", "edge", "firefox"]

MAX_RETRY_ATTEMPTS   = 3    # total attempts per pair when blocked
MAX_VPN_ATTEMPTS     = 20   # VPN locations to try per attempt
VPN_SETTLE_WAIT      = 5    # after connect, before opening browser
POST_DISCONNECT_WAIT = 3    # after disconnect, before next connect/browser


# --------------------------------------------------------------------------
# G2 automation
# --------------------------------------------------------------------------
class G2Automation:

    def __init__(self, driver, human_simulator, gs):
        self.driver = driver
        self.human_simulator = human_simulator
        self.gs = gs
        self.items = {}
        self.excel = Excel()

    def set_data(self, product, comparing_product, browser, location, status, link=""):
        self.items["Link"] = link
        self.items["First product"] = product
        self.items["Second product"] = comparing_product
        self.items["Browser Name"] = browser
        self.items["Country Name"] = location
        self.items["Version Number"] = ""
        self.items["Status"] = status

    def run_g2(self, product, comparing_product, browser, location, is_last_attempt=True):
        status = "Unknown"
        link = ""
        retry = False  # True => main will retry; only save a row on the last attempt
        try:
            categories = ['word', 'name', 'country', 'movie', 'music', 'sports', 'technology', 'News']
            test_keywords = [
                "browser tests", "software testing", "automation tests",
                "ai in test cases", "app android", "android on browser",
            ]
            keywords_combos = [
                (random.choices(categories, k=2), True),
                (random.choices(test_keywords, k=2), False),
            ]

            try:
                self.gs.search_work(keywords_combos)
            except AccessDeniedError:
                status = "Blocked at Google Search"
                raise
            except Exception as e:
                status = f"Failed at Google Search: {str(e).splitlines()[0]}"
                logger.exception(status)
                raise RetryableFailure(status) from e

            try:
                G2Page(self.driver, self.human_simulator, product, comparing_product).run_g2_product()
                link = self.driver.current_url
            except AccessDeniedError:
                status = "Blocked at G2 Page"
                raise
            except Exception as e:
                status = f"Failed at G2 Page: {str(e).splitlines()[0]}"
                logger.exception(status)
                raise RetryableFailure(status) from e

            try:
                G2Comparison(self.driver, self.human_simulator, comparing_product).run_g2_comparisons()
                status = "Done"
            except AccessDeniedError:
                status = "Blocked at G2 Comparison"
                raise
            except Exception as e:
                status = "Failed at G2 Comparison"   # not retried (original behaviour)
                logger.exception(f"G2 comparison failed: {e}")

        except (AccessDeniedError, RetryableFailure):
            retry = True
            raise
        except Exception:
            if status == "Unknown":
                status = "Failed (unknown)"
            logger.error(traceback.format_exc())
        finally:
            if not retry or is_last_attempt:
                self.set_data(product, comparing_product, browser, location, status, link)
                self.excel.save_excel(row=self.items)

        return status
# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def safe_disconnect(vpn):
    if vpn is None:
        return
    try:
        vpn.disconnect()
    except Exception:
        pass


def connect_vpn(vpn, location_manager):
    """Return a connected location, or None if none could be connected."""
    for n in range(1, MAX_VPN_ATTEMPTS + 1):
        if not location_manager.has_next():
            logger.error("No VPN locations left.")
            return None

        candidate = location_manager.next()
        try:
            vpn.connect(candidate)
            logger.info(f"[VPN] Connected to '{candidate}' (try {n}/{MAX_VPN_ATTEMPTS})")
            return candidate
        except Exception as e:
            logger.warning(f"[VPN] '{candidate}' rejected ({e}); blacklisting.")
            location_manager.mark_failed(candidate)
            safe_disconnect(vpn)
            time.sleep(POST_DISCONNECT_WAIT)
    return None


def browsers_to_exclude(excel_done, tried):
    """
    Exclude browsers already used for finished rows plus the ones that were
    blocked during this pair's retries. Once every browser is excluded,
    rotate back: forget the blocked list and reuse them.
    """
    excluded = set(excel_done) | set(tried)
    if set(ALL_BROWSERS) <= excluded:
        logger.info("All browsers tried for this pair - rotating back to the start.")
        tried.clear()
        excluded = set(excel_done)
        if set(ALL_BROWSERS) <= excluded:  # even Excel-done covers everything
            excluded = set()
    return list(excluded)


def run_pair(product, comparing_product, vpn, location_manager):
    """Run one (product, comparing_product) pair. Returns True on success."""
    tried_browsers = []  # browsers that got blocked for THIS pair

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        location = connect_vpn(vpn, location_manager)
        if location is None:
            logger.error(f"No usable VPN for {product}/{comparing_product} - giving up.")
            return False

        manager, browser = None, None

        try:
            time.sleep(VPN_SETTLE_WAIT)

            excluded = browsers_to_exclude(Excel().browser_list(), tried_browsers)
            logger.info(
                f"[Attempt {attempt}/{MAX_RETRY_ATTEMPTS}] excluding browsers: {excluded}"
            )

            manager = Browser(headless=False, done_browser=excluded)
            driver, browser = manager.launch()

            human_simulator = HumanSimulator(driver)
            gs = GoogleSearch(driver, human_simulator)
            gs.get_google()

            status = G2Automation(driver, human_simulator, gs).run_g2(
                product, comparing_product, browser, location,
                is_last_attempt=(attempt == MAX_RETRY_ATTEMPTS),
            )
            if status == "Done":
                logger.info(f"Completed {product}/{comparing_product} via '{location}' on {browser}")
                location_manager.mark_success(location)
                return True
            logger.warning(f"{product}/{comparing_product} finished with status '{status}' - not retrying.")
            return False

        except (AccessDeniedError, RetryableFailure) as err:
            kind = "BLOCKED" if isinstance(err, AccessDeniedError) else "FAILED"
            logger.warning(
                f"[{kind} {attempt}/{MAX_RETRY_ATTEMPTS}] {product}/{comparing_product} "
                f"on '{location}' with {browser}: {str(err).splitlines()[0]}"
            )
            if isinstance(err, AccessDeniedError):
                location_manager.mark_failed(location)  # only a real block blames the VPN
            if browser:
                tried_browsers.append(browser)
            # loop continues: new VPN + a different browser

        except Exception:
            logger.exception(f"{product}/{comparing_product} crashed (not retryable).")
            return False

        #     G2Automation(driver, human_simulator, gs).run_g2(
        #         product, comparing_product, browser, location
        #     )
        #     logger.info(
        #         f"Completed {product}/{comparing_product} via '{location}' on {browser}"
        #     )
        #     location_manager.mark_success(location)
        #     return True

        # except AccessDeniedError as blocked:
        #     logger.warning(
        #         f"[BLOCKED {attempt}/{MAX_RETRY_ATTEMPTS}] {product}/{comparing_product} "
        #         f"on '{location}' with {browser}: {blocked}"
        #     )
        #     location_manager.mark_failed(location)
        #     if browser:
        #         tried_browsers.append(browser)
            # loop continues: new VPN + a different browser

        # except Exception:
        #     # Code/data error: a new VPN or browser won't fix it, so don't retry.
        #     logger.exception(
        #         f"{product}/{comparing_product} failed (not a block) - not retrying."
        #     )
        #     return False

        finally:
            if manager is not None:
                try:
                    manager.quit(browser_name=browser)
                except Exception:
                    pass
            safe_disconnect(vpn)
            time.sleep(POST_DISCONNECT_WAIT)

    logger.error(
        f"Giving up on {product}/{comparing_product} "
        f"after {MAX_RETRY_ATTEMPTS} blocked attempts."
    )
    return False


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Script Has Been Started..............")

    products = {
        "SauceLabs":    ["Ranorex", "TestComplete"],
        "BrowserStack": ["Qase", "accessiBe"],
    }

    location_manager = LocationManager()
    vpn = None
    try:
        vpn = ExpressVPN()

        for product, comparing_products in products.items():
            for comparing_product in comparing_products:

                if Excel().check_if_completed(product, comparing_product):
                    logger.info(f"Already Done {product} and {comparing_product}")
                    continue

                logger.info(f"Starting comparison for {product} and {comparing_product}")

                run_pair(product, comparing_product, vpn, location_manager)

    except Exception:
        logger.error(traceback.format_exc())
    finally:
        safe_disconnect(vpn)