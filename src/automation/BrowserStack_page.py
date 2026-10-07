"""Human-like exploration flow for the BrowserStack public website."""

import argparse
import random
import time

from selenium.common.exceptions import NoSuchWindowException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.automation.driver import Browser
from src.automation.human_simulator import HumanSimulator
from src.automation.xpath_pools import BROWSERSTACK_HOME_POOL
from src.commons import save_html
from src.excel import SponsoredResultTracker
from src.logging import logger


class BrowserStackPage:
    """Explore BrowserStack.com using shared HumanSimulator behavior."""

    url = "https://www.browserstack.com/"
    google_url = "https://www.google.com/"
    search_query = "browserstack"
    sponsored_container_xpath = '//*[@id="tadsb"]'
    sponsored_requested_xpath = '//*[@id="tadsb"]/div[5]'
    cookie_button_xpaths = (
        '//*[@id="onetrust-accept-btn-handler"]',
        '//button[contains(translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "accept all")]',
        '//button[contains(translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "accept cookies")]',
    )
    scroll_area_xpaths = (
        '//*[@id="product-tab-content0"]',
        '//*[@id="post-26"]/div/div[5]/div/div/div/div',
    )
    text_area_xpaths = (
        '//*[@id="post-26"]/div/div[7]/div/div/div/article/div/div',
        '//*[@id="post-26"]/div/div[8]/div/div/div/section',
    )

    def __init__(self, driver, human_simulator, sponsored_tracker=None):
        self.driver = driver
        self.human_simulator = human_simulator
        self.sponsored_tracker = sponsored_tracker or SponsoredResultTracker()

    def inspect_google_sponsored_results(self):
        """Record a BrowserStack sponsored result without clicking the ad."""
        logger.info("Opening Google to inspect sponsored results for: %s", self.search_query)
        self.driver.get(self.google_url)
        WebDriverWait(self.driver, 15, poll_frequency=0.25).until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        self.human_simulator.input_search_query(
            self.search_query,
            suggestion=False,
        )

        WebDriverWait(self.driver, 15, poll_frequency=0.25).until(
            lambda driver: (
                "/search" in driver.current_url
                or "/sorry" in driver.current_url
                or bool(driver.find_elements(By.ID, "tadsb"))
            )
        )
        if "/sorry" in self.driver.current_url:
            logger.warning(
                "Google CAPTCHA detected; sponsored inspection skipped and no bypass attempted"
            )
            return False

        candidates = self.driver.find_elements(By.XPATH, self.sponsored_requested_xpath)
        candidates.extend(
            self.driver.find_elements(
                By.XPATH,
                f'{self.sponsored_container_xpath}/*[not(self::script)]',
            )
        )
        logger.info("Google sponsored candidates found: %s", len(candidates))

        seen_ids = set()
        for candidate in candidates:
            try:
                candidate_id = candidate.id
                if candidate_id in seen_ids or not candidate.is_displayed():
                    continue
                seen_ids.add(candidate_id)
                content = " ".join((candidate.text or "").split())
                links = candidate.find_elements(By.CSS_SELECTOR, "a[href]")
                hrefs = " ".join(link.get_attribute("href") or "" for link in links)
                if "browserstack" not in f"{content} {hrefs}".casefold():
                    continue

                count = self.sponsored_tracker.record_seen("BrowserStack")
                logger.info(
                    "BrowserStack found in sponsored results; seen count is now %s. "
                    "Sponsored result was not clicked",
                    count,
                )
                return True
            except Exception as error:
                logger.warning("Could not inspect one sponsored candidate: %s", error)

        logger.info("BrowserStack was not found in the visible sponsored results")
        return False

    def wait_until_ready(self):
        WebDriverWait(self.driver, 30, poll_frequency=0.25).until(
            lambda driver: driver.execute_script("return document.readyState")
            in ("interactive", "complete")
        )
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logger.info(
            "BrowserStack homepage loaded: title=%r url=%s",
            self.driver.title,
            self.driver.current_url,
        )

    def close_cookie_banner_if_present(self):
        for xpath in self.cookie_button_xpaths:
            for button in self.driver.find_elements(By.XPATH, xpath):
                if not button.is_displayed() or not button.is_enabled():
                    continue
                try:
                    logger.info("Closing BrowserStack cookie banner with mouse")
                    self.human_simulator.mouse_click(button)
                    WebDriverWait(self.driver, 4, poll_frequency=0.2).until(
                        lambda _: not button.is_displayed()
                    )
                    logger.info("BrowserStack cookie banner closed")
                    return True
                except Exception as error:
                    logger.warning("Cookie banner close attempt failed: %s", error)
        logger.info("No visible BrowserStack cookie banner found")
        return False

    def _available_xpath_elements(self, xpaths):
        available = []
        for xpath in xpaths:
            for element in self.driver.find_elements(By.XPATH, xpath):
                if element.is_displayed():
                    available.append((xpath, element))
        return available

    def _reach_with_mouse(self, element):
        return self.human_simulator.scroll_to_element_human(
            element,
            align=random.choice(["start", "center", "center", "end"]),
        )

    def explore_random_scroll_area(self):
        areas = self._available_xpath_elements(self.scroll_area_xpaths)
        logger.info("Available BrowserStack scroll areas: %s", len(areas))
        if not areas:
            logger.warning("No supplied BrowserStack scroll area was available")
            return False

        xpath, area = random.choice(areas)
        logger.info(
            "Randomly selected 1 of %s BrowserStack scroll areas: %s",
            len(areas),
            xpath,
        )
        self._reach_with_mouse(area)
        logger.info("Reached selected BrowserStack scroll area")
        move_count = random.randint(2, 4)
        directions = [1] * random.randint(1, 2) + [-1]
        while len(directions) < move_count:
            directions.append(random.choice([-1, 1, 1]))

        for index, direction in enumerate(directions[:move_count], start=1):
            distance = random.randint(80, 180)
            logger.info(
                "BrowserStack area mouse scroll %s/%s: %s %spx",
                index,
                move_count,
                "down" if direction > 0 else "up",
                distance,
            )
            self.human_simulator.scroll_page(
                total_scroll=distance,
                direction="down" if direction > 0 else "up",
            )
            time.sleep(random.uniform(0.4, 1.0))

        self.human_simulator.hover_element_human(area)
        if random.random() < 0.4:
            self.human_simulator.random_glance_scroll()

        logger.info("Completed random BrowserStack scroll-area interaction")
        return True

    def interact_with_random_image(self):
        image_area_xpath = '//*[@id="post-26"]/div/div[5]/div/div/div/div'
        areas = self.driver.find_elements(By.XPATH, image_area_xpath)
        logger.info("BrowserStack image-area elements found: %s", len(areas))
        if not areas:
            logger.warning("BrowserStack image-selection area was unavailable")
            return False

        area = areas[0]
        self._reach_with_mouse(area)
        images = [
            image for image in area.find_elements(By.CSS_SELECTOR, "img, [role='img']")
            if image.is_displayed()
            and image.size.get("width", 0) >= 30
            and image.size.get("height", 0) >= 30
        ]
        logger.info("Visible BrowserStack image candidates: %s", len(images))
        if not images:
            logger.warning("No visible image was available in BrowserStack image area")
            return False

        image = random.choice(images)
        image_name = (
            image.get_attribute("alt")
            or image.get_attribute("aria-label")
            or image.get_attribute("src")
            or "unnamed image"
        )
        logger.info(
            "Randomly selected 1 of %s BrowserStack images: %s",
            len(images),
            image_name,
        )
        self._reach_with_mouse(image)
        logger.info("Moving mouse over selected BrowserStack image")
        self.human_simulator.hover_element_human(image)

        safe_controls = image.find_elements(
            By.XPATH,
            './ancestor::button[not(@disabled)][1] | '
            './ancestor::*[@role="button" and not(@aria-disabled="true")][1]',
        )
        if safe_controls and random.random() < 0.6:
            control = safe_controls[0]
            logger.info("Clicking selected BrowserStack image control with mouse")
            self.human_simulator.safe_click(control)
            view_time = random.uniform(1.0, 3.0)
            logger.info("Viewing selected image state for %.1fs", view_time)
            time.sleep(view_time)
        else:
            logger.info("Selected image was viewed without navigation click")
        return True

    def select_text_from_random_area(self):
        areas = self._available_xpath_elements(self.text_area_xpaths)
        logger.info("Available BrowserStack text-selection areas: %s", len(areas))
        if not areas:
            logger.warning("No supplied BrowserStack text-selection area was available")
            return None

        xpath, area = random.choice(areas)
        logger.info(
            "Randomly selected 1 of %s BrowserStack text areas: %s",
            len(areas),
            xpath,
        )
        self._reach_with_mouse(area)
        logger.info("Reached selected BrowserStack text-selection area")
        logger.info("Hovering over BrowserStack text area")
        self.human_simulator.hover_element_human(area)
        if self.human_simulator.use_native_cursor:
            min_words = random.randint(1, 3)
            max_words = random.randint(6, 12)
            logger.info(
                "Selecting a random BrowserStack phrase in the %s-%s word range",
                min_words,
                max_words,
            )
            phrase = self.human_simulator.select_visible_phrase(
                area,
                min_words=min_words,
                max_words=max_words,
            )
            logger.info("Mouse-selected BrowserStack website text: %r", phrase)
            return phrase

        selected = self.human_simulator.select_text_in_element(area)
        logger.info("Selected BrowserStack website text with fallback: %s", selected)
        return selected

    def run(self, min_seconds=20, max_seconds=40, inspect_sponsored=True):
        if min_seconds > max_seconds:
            min_seconds, max_seconds = max_seconds, min_seconds

        logger.info("BrowserStack website automation started")
        if inspect_sponsored:
            try:
                self.inspect_google_sponsored_results()
            except Exception as error:
                logger.warning(
                    "Sponsored-result inspection could not complete; continuing safely: %s",
                    error,
                )
        logger.info("Opening BrowserStack directly to avoid search CAPTCHA: %s", self.url)
        self.driver.get(self.url)
        self.wait_until_ready()
        save_html(self.driver.page_source, "BrowserStack_Home")
        self.close_cookie_banner_if_present()

        initial_moves = random.randint(1, 3)
        logger.info("Moving mouse around homepage %s time(s)", initial_moves)
        self.human_simulator.move_mouse_around(moves=initial_moves)

        interactions = (
            ("BrowserStack Scroll Area", self.explore_random_scroll_area),
            ("BrowserStack Random Image", self.interact_with_random_image),
            ("BrowserStack Text Selection", self.select_text_from_random_area),
        )
        interaction_summary = self.human_simulator.run_random_actions(
            interactions,
            min_actions=2,
            max_actions=len(interactions),
        )
        logger.info(
            "BrowserStack selected interaction summary: %s",
            interaction_summary,
        )

        duration = random.uniform(min_seconds, max_seconds)
        logger.info("Random BrowserStack browsing duration: %.1f seconds", duration)
        summary = self.human_simulator.browse_page_randomly(
            duration=duration,
            pool=BROWSERSTACK_HOME_POOL,
        )
        logger.info("BrowserStack website interaction summary: %s", summary)
        logger.info("BrowserStack website automation completed successfully")
        return summary


def run(
    min_seconds=20,
    max_seconds=40,
    browser_name="Chrome",
    inspect_sponsored=True,
):
    max_browser_attempts = 3
    for attempt in range(1, max_browser_attempts + 1):
        # Avoid a second SET_WINDOW_RECT command immediately after Chrome
        # starts. On some macOS/UC launches that command races the first tab
        # and produces "web view not found" before launch() can return.
        manager = Browser(headless=False, window_size=None)
        try:
            logger.info(
                "Starting BrowserStack browser launch attempt %s/%s",
                attempt,
                max_browser_attempts,
            )
            driver, selected_browser = manager.launch(browser_name)
            handles = driver.window_handles
            logger.info("Browser window handles detected: %s", len(handles))
            if not handles:
                raise NoSuchWindowException(
                    "Chrome launched without an available browser window"
                )
            driver.switch_to.window(handles[0])
            logger.info(
                "Browser launched for BrowserStack flow: %s (attempt %s/%s)",
                selected_browser,
                attempt,
                max_browser_attempts,
            )
            human_simulator = HumanSimulator(driver, use_native_cursor=True)
            if not human_simulator.use_native_cursor:
                logger.warning(
                    "Native mouse is unavailable; Selenium pointer fallback will be used"
                )
            return BrowserStackPage(driver, human_simulator).run(
                min_seconds=min_seconds,
                max_seconds=max_seconds,
                inspect_sponsored=inspect_sponsored,
            )
        except NoSuchWindowException as error:
            if attempt >= max_browser_attempts:
                logger.exception(
                    "BrowserStack browser window closed on final attempt: %s",
                    error,
                )
                raise
            logger.warning(
                "Chrome window closed before automation started; "
                "launching a fresh browser session"
            )
            time.sleep(1)
        except Exception as error:
            logger.exception("BrowserStack website automation failed: %s", error)
            raise
        finally:
            try:
                # manager.quit()
                pass
            except Exception as close_error:
                logger.warning("Browser cleanup skipped: %s", close_error)
            logger.info("BrowserStack website browser session closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run human-like BrowserStack website exploration"
    )
    parser.add_argument("--min-seconds", type=float, default=20)
    parser.add_argument("--max-seconds", type=float, default=40)
    parser.add_argument("--browser", default="Chrome")
    parser.add_argument(
        "--skip-sponsored-check",
        action="store_true",
        help="Open BrowserStack directly without inspecting Google sponsored results",
    )
    args = parser.parse_args()
    run(
        min_seconds=args.min_seconds,
        max_seconds=args.max_seconds,
        browser_name=args.browser,
        inspect_sponsored=not args.skip_sponsored_check,
    )
