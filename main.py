import random
import os
import traceback
import sys
import argparse
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchWindowException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# if __package__ in (None, ""):
#     sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
from src.commons import *
from src.automation.vpn.vpn_automation import ExpressVPN
from src.automation.location_manager import LocationManager
from src.logging import logger
from src.excel import Excel, SponsoredResultTracker
from src.automation.xpath_pools import MU_GOOGLE_POOL


class TestMuAutomation:
    """Run the TestMu sponsored-result flow from main.py."""

    TESTMU_DOMAIN = "testmuai.com"
    # Default to the same randomized Google search flow used by G2.
    # Set MU_LOCAL_DIRECT_SEARCH=1 only for local browserstack testing.
    LOCAL_DIRECT_SEARCH = os.getenv("MU_LOCAL_DIRECT_SEARCH", "0") == "1"
    SPONSORED_LINK_XPATH = (
        '//*[@id="tads"]//a[@href] | //*[@id="tadsb"]//a[@href] | '
        '//div[@data-text-ad]//a[@href] | '
        '//div[contains(@class,"uEierd")]//a[@href] | '
        '//a[contains(@href,"/aclk?")] | '
        "//*[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
        "'sponsored')]/ancestor::*[self::div or self::li][.//a[@href]][1]"
        "//a[@href]"
    )
    SPONSORED_WORD_XPATH = (
        "//*[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
        "'sponsored')]"
    )

    def __init__(self, driver, human_simulator, google_search=None):
        self.driver = driver
        self.human_simulator = human_simulator
        self.google_search = google_search
        self.tracker = SponsoredResultTracker()

    def _step(self, name, status="ok", details=""):
        self.tracker.log_event(name, status, details)
        logger.info(f"MU step={name} status={status} {details}".rstrip())

    def _bring_into_view_if_needed(self, element):
        in_view = self.driver.execute_script(
            "const r=arguments[0].getBoundingClientRect(); "
            "return r.top >= 80 && r.bottom <= window.innerHeight - 40;",
            element,
        )
        # Do not repeatedly scroll to every supplied XPath. Only interact
        # with the target when it is already visible.
        return bool(in_view)

    @staticmethod
    def _g2_search_combinations():
        """Use the same randomized Google search inputs as G2Automation."""
        categories = [
            "word", "name", "country", "movie", "music", "sports",
            "technology", "News",
        ]
        test_keywords = [
            "browser tests", "software testing", "automation tests",
            "ai in test cases", "app android", "android on browser",
        ]
        return [
            (random.choices(categories, k=2), True),
            (random.choices(test_keywords, k=2), False),
        ]

    @staticmethod
    def _advertiser_website(href):
        """Return the advertiser domain from a direct or Google redirect URL."""
        if not href:
            return None

        current = href
        for _ in range(2):
            parsed = urlparse(current)
            query = parse_qs(parsed.query)
            redirected = next(
                (
                    values[0]
                    for key in ("adurl", "url", "q")
                    if (values := query.get(key))
                ),
                None,
            )
            if not redirected:
                break
            current = unquote(redirected)

        hostname = (urlparse(current).hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        google_tracking_domains = (
            "google.com",
            "googleadservices.com",
            "doubleclick.net",
            "gstatic.com",
        )
        if not hostname or hostname.endswith(google_tracking_domains):
            return None
        return hostname

    def inspect_sponsored_results(self):
        self._step("google_open", details="G2-style sponsored-result inspection")
        if self.google_search is not None:
            self.google_search.get_google()
            if self.LOCAL_DIRECT_SEARCH:
                self.google_search.last_query = "browserstack"
                self.google_search.get_google(query="browserstack")
                self._step(
                    "google_direct_search",
                    details="browserstack (local mode)",
                )
                WebDriverWait(self.driver, 15, poll_frequency=0.25).until(
                    lambda driver: "/search" in driver.current_url
                )
                save_html(self.driver.page_source, "MU_browserstack")
                self._step("google_html_saved", details="MU_browserstack")
            else:
                self._step("google_search_work_started")
                self.google_search.search_work(
                    self._g2_search_combinations(),
                    step_callback=lambda step, details: self._step(
                        step, details=details
                    ),
                    browse_duration=0,
                    max_element_attempts=1,
                    scroll_on_missing=False,
                )
                self._step("google_search_work_completed")

        else:
            self.driver.get("https://www.google.com/")
            WebDriverWait(self.driver, 15, poll_frequency=0.25).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            self.human_simulator.input_search_query(
                "browserstack",
                suggestion=False,
            )
            WebDriverWait(self.driver, 15, poll_frequency=0.25).until(
                lambda driver: (
                    "/search" in driver.current_url
                    or "/sorry" in driver.current_url
                )
            )

        save_html(self.driver.page_source, "MU_sponsored_results")
        self._step("sponsored_html_saved", details="MU_sponsored_results")
        sponsored_labels = [
            label for label in self.driver.find_elements(
                By.XPATH, self.SPONSORED_WORD_XPATH
            ) if label.is_displayed()
        ]
        self._step(
            "sponsored_word_check",
            "found" if sponsored_labels else "not_found",
            f"labels={len(sponsored_labels)}",
        )

        if "/sorry" in self.driver.current_url:
            logger.warning(
                "Google CAPTCHA detected; waiting up to 120 seconds for manual completion"
            )
            try:
                WebDriverWait(self.driver, 120, poll_frequency=0.5).until(
                    lambda driver: (
                        "/sorry" not in driver.current_url
                        and (
                            "/search" in driver.current_url
                            or bool(driver.find_elements(By.ID, "search"))
                        )
                    )
                )
                logger.info(
                    "Manual CAPTCHA completion detected; resuming sponsored inspection"
                )
            except TimeoutException:
                logger.warning(
                    "CAPTCHA was not completed within 120 seconds; "
                    "sponsored inspection stopped"
                )
                return False

        results = {}
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            for link in self.driver.find_elements(By.XPATH, self.SPONSORED_LINK_XPATH):
                try:
                    if not link.is_displayed():
                        continue
                    href = link.get_attribute("href") or ""
                    website = self._advertiser_website(href)
                    if website:
                        key = (href, link.text.strip())
                        results.setdefault(key, {
                            "element": link,
                            "href": href,
                            "title": link.text.strip(),
                            "website": website,
                            "result_text": link.find_element(
                                By.XPATH, "./ancestor::div[@data-text-ad][1]"
                            ).text.strip() if link.find_elements(
                                By.XPATH, "./ancestor::div[@data-text-ad][1]"
                            ) else link.text.strip(),
                        })
                except Exception as error:
                    logger.warning(f"Sponsored result inspection failed: {error}")
            time.sleep(0.25)

        if not results:
            self._step("sponsored_scan", "empty", "no sponsored websites found")
            logger.info("No advertiser websites found in either sponsored section")
            return False

        self._step("sponsored_candidates_collected", details=f"count={len(results)}")

        search_query = (
            getattr(self.google_search, "last_query", None)
            or "G2-style randomized Google search"
        )
        for result in results.values():
            website = result["website"].casefold()
            is_testmu = website == self.TESTMU_DOMAIN or website.endswith(
                f".{self.TESTMU_DOMAIN}"
            )
            self.tracker.record_result({
                "Search Query": search_query,
                "Title": result["title"],
                "Website Name": result["website"],
                "Link": result["href"],
                "Result Text": result["result_text"],
                "TestMu Result": "Yes" if is_testmu else "No",
            })
            logger.info(
                f"Sponsored website detected: {result['website']} "
                f"({result['title']})"
            )
            self._step(
                "sponsored_result_saved",
                details=f"website={result['website']} query={search_query}",
            )
        logger.info(
            f"query={search_query}; workbook={self.tracker.file_name}"
        )
        self._step("sponsored_scan_completed", details=f"count={len(results)}")
        return list(results.values())

    def _browse_sponsored_website(self, website, max_seconds=30):
        """Perform a short, bounded HumanSimulator interaction on one ad site."""
        started = time.monotonic()
        deadline = started + max_seconds
        self._step(
            "sponsored_site_browse_started",
            details=f"website={website} max_seconds={max_seconds}",
        )

        # Keep this deliberately small: one selection, one short scroll, and
        # one hover are enough to create a human-like visit without repeatedly
        # walking the whole page.
        try:
            if time.monotonic() < deadline:
                selected = self.human_simulator.select_text_once()
                logger.info(f"HumanSimulator text selection on {website}: {bool(selected)}")
                self._step("sponsored_site_text_select", details=f"website={website}")
        except Exception as error:
            logger.warning(f"Text selection skipped on {website}: {error}")

        try:
            if time.monotonic() < deadline:
                self.human_simulator.scroll_page(
                    total_scroll=random.randint(1, 2),
                    step_delay=random.uniform(0.12, 0.25),
                    direction="down",
                )
                logger.info(f"HumanSimulator short scroll on {website}")
                self._step("sponsored_site_scroll", details=f"website={website}")
        except Exception as error:
            logger.warning(f"Short scroll skipped on {website}: {error}")

        try:
            if time.monotonic() < deadline:
                elements = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "main h1, main h2, main h3, main p, main img, "
                    "article h2, article h3, section h2, section h3",
                )
                visible = [element for element in elements if element.is_displayed()]
                if visible:
                    element = random.choice(visible)
                    self.human_simulator.mouse_hover(element, hover_time=0.8)
                    logger.info(f"HumanSimulator hover on {website}")
                    self._step("sponsored_site_hover", details=f"website={website}")
        except Exception as error:
            logger.warning(f"Hover skipped on {website}: {error}")

        elapsed = round(time.monotonic() - started, 2)
        logger.info(f"Sponsored website visit completed: {website}; elapsed={elapsed}s")
        self._step("sponsored_site_browse_completed", details=f"website={website} elapsed={elapsed}s")

    def _visit_all_sponsored_websites(self, results):
        """Open every sponsored result entry and return to Google each time."""
        if not results:
            self._step("sponsored_site_visits", "empty")
            return False

        google_handle = self.driver.current_window_handle
        google_url = self.driver.current_url
        total_results = len(results)
        self._step(
            "sponsored_site_visit_queue",
            details=f"total_entries={total_results}",
        )

        for result_number, result in enumerate(results, start=1):
            website = result["website"]
            self._step(
                "sponsored_site_visit_started",
                details=(
                    f"entry={result_number}/{total_results} website={website} "
                    f"href={result['href']}"
                ),
            )

            try:
                candidates = self.driver.find_elements(By.XPATH, self.SPONSORED_LINK_XPATH)
                link = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.is_displayed()
                        and (
                            candidate.get_attribute("href") == result["href"]
                            or website_key in (candidate.get_attribute("href") or "").casefold()
                        )
                    ),
                    None,
                )
                if link is None:
                    self._step(
                        "sponsored_site_skipped",
                        details=(
                            f"entry={result_number}/{total_results} website={website} "
                            "link_not_found_on_current_google_page"
                        ),
                    )
                    continue

                old_url = self.driver.current_url
                old_handles = set(self.driver.window_handles)
                self._step(
                    "sponsored_site_click_started",
                    details=f"entry={result_number}/{total_results} website={website}",
                )
                self.human_simulator.mouse_hover(link, hover_time=0.5)
                self.human_simulator.mouse_click_after_hover(link)

                def destination_opened(_):
                    new_handles = set(self.driver.window_handles) - old_handles
                    if new_handles:
                        self.driver.switch_to.window(next(iter(new_handles)))
                        return self.driver.current_url != "about:blank"
                    return self.driver.current_url != old_url

                try:
                    WebDriverWait(self.driver, 10, poll_frequency=0.25).until(destination_opened)
                except TimeoutException:
                    logger.warning(f"Sponsored click did not navigate on first attempt: {website}")
                    try:
                        link.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", link)
                    WebDriverWait(self.driver, 10, poll_frequency=0.25).until(destination_opened)

                new_handles = set(self.driver.window_handles) - old_handles
                if new_handles:
                    self.driver.switch_to.window(next(iter(new_handles)))
                WebDriverWait(self.driver, 10, poll_frequency=0.25).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                logger.info(f"Sponsored website opened: {website}; url={self.driver.current_url}")
                self._step(
                    "sponsored_site_opened",
                    details=(
                        f"entry={result_number}/{total_results} website={website} "
                        f"url={self.driver.current_url}"
                    ),
                )
                self._browse_sponsored_website(website, max_seconds=30)
            except Exception as error:
                logger.warning(f"Sponsored website visit failed for {website}: {error}")
                self._step(
                    "sponsored_site_failed",
                    details=(
                        f"entry={result_number}/{total_results} website={website} "
                        f"error={error}"
                    ),
                )
            finally:
                try:
                    if self.driver.current_window_handle != google_handle:
                        self.driver.close()
                        self.driver.switch_to.window(google_handle)
                    elif self.driver.current_url != google_url:
                        self.driver.back()
                    WebDriverWait(self.driver, 8, poll_frequency=0.25).until(
                        lambda driver: "/search" in driver.current_url or bool(driver.find_elements(By.ID, "search"))
                    )
                except Exception as error:
                    logger.warning(f"Could not restore Google results after {website}: {error}")
                    try:
                        self.driver.get(google_url)
                    except Exception:
                        pass
                self._step(
                    "sponsored_site_returned_to_google",
                    details=f"entry={result_number}/{total_results} website={website}",
                )

        self._step(
            "sponsored_site_visits_completed",
            details=f"processed_entries={total_results}",
        )
        return True

    def _click_google_page_two_and_scan(self):
        """Open Google page 2 and collect its currently rendered sponsored ads."""
        page_two_xpaths = MU_GOOGLE_POOL["xpaths"]["page_2"]
        self._step("google_page_two_started", details=f"xpath_count={len(page_two_xpaths)}")
        page_two_link = None
        selected_page_two_xpath = None
        for xpath in page_two_xpaths:
            try:
                candidates = self.driver.find_elements(By.XPATH, xpath)
                page_two_link = next(
                    (candidate for candidate in candidates if candidate.is_displayed()),
                    None,
                )
                self._step(
                    "google_page_two_xpath_checked",
                    "found" if page_two_link else "not_found",
                    details=xpath,
                )
                if page_two_link:
                    selected_page_two_xpath = xpath
                    break
            except Exception as error:
                logger.warning(f"Google page-2 XPath failed: {xpath}; error={error}")
                self._step("google_page_two_xpath_error", "failed", f"xpath={xpath} error={error}")

        if page_two_link is None:
            self._step("google_page_two", "not_found", "page 2 link unavailable")
            return []

        old_url = self.driver.current_url
        self._step(
            "google_page_two_click_started",
            details=selected_page_two_xpath or "unknown_xpath",
        )
        try:
            self.human_simulator.mouse_hover(page_two_link, hover_time=0.4)
            self.human_simulator.mouse_click_after_hover(page_two_link)
            WebDriverWait(self.driver, 12, poll_frequency=0.25).until(
                lambda driver: driver.current_url != old_url
            )
            WebDriverWait(self.driver, 12, poll_frequency=0.25).until(
                EC.presence_of_element_located((By.ID, "search"))
            )
            self._step("google_page_two_opened", details=self.driver.current_url)
        except Exception as error:
            logger.warning(f"Google page 2 could not be opened: {error}")
            self._step("google_page_two", "failed", details=str(error))
            return []

        save_html(self.driver.page_source, "MU_sponsored_results_page_2")
        self._step("sponsored_html_saved", details="MU_sponsored_results_page_2")
        results = {}
        scan_deadline = time.monotonic() + 8
        while time.monotonic() < scan_deadline:
            try:
                links = self.driver.find_elements(By.XPATH, self.SPONSORED_LINK_XPATH)
                self._step("page_two_sponsored_scan_pass", details=f"links={len(links)}")
                for link in links:
                    try:
                        if not link.is_displayed():
                            continue
                        href = link.get_attribute("href") or ""
                        website = self._advertiser_website(href)
                        if website:
                            key = (href, link.text.strip())
                            results.setdefault(key, {
                                "element": link,
                                "href": href,
                                "title": link.text.strip(),
                                "website": website,
                                "result_text": link.text.strip(),
                            })
                    except Exception as error:
                        logger.warning(f"Page-2 sponsored result inspection failed: {error}")
                        self._step("page_two_sponsored_result_error", "failed", str(error))
            except Exception as error:
                logger.warning(f"Page-2 sponsored scan pass failed: {error}")
                self._step("page_two_sponsored_scan_pass", "failed", str(error))
            time.sleep(0.25)

        self._step("page_two_sponsored_candidates_collected", details=f"count={len(results)}")
        search_query = getattr(self.google_search, "last_query", None) or "Google page 2"
        saved_count = 0
        for result in results.values():
            website = result["website"].casefold()
            is_testmu = website == self.TESTMU_DOMAIN or website.endswith(f".{self.TESTMU_DOMAIN}")
            try:
                self.tracker.record_result({
                    "Search Query": search_query,
                    "Title": result["title"],
                    "Website Name": result["website"],
                    "Link": result["href"],
                    "Result Text": result["result_text"],
                    "TestMu Result": "Yes" if is_testmu else "No",
                })
                saved_count += 1
                self._step("page_two_sponsored_result_saved", details=f"website={result['website']}")
            except Exception as error:
                logger.warning(f"Page-2 tracker save failed for {result['website']}: {error}")
                self._step("page_two_sponsored_result_save", "failed", str(error))
        self._step("google_page_two_completed", details=f"saved_count={saved_count}")
        return list(results.values())

    def run(self):
        results = self.inspect_sponsored_results()
        testmu_results = [
            result
            for result in results
            if (
                result["website"].casefold() == self.TESTMU_DOMAIN
                or result["website"].casefold().endswith(
                    f".{self.TESTMU_DOMAIN}"
                )
            )
        ] if results else []
        if not testmu_results:
            self._step("testmu_target", "not_found")
            logger.info(
                "TestMu was not found; sponsored websites were saved but not opened"
            )
            return False

        self._step(
            "testmu_target",
            "found",
            details=f"website={testmu_results[0]['website']}; opening all sponsored websites",
        )
        # Visit every sponsored result on page 1 first. A failed site is
        # isolated inside _visit_all_sponsored_websites and cannot stop the loop.
        page_one_completed = self._visit_all_sponsored_websites(results)
        self._step("google_page_one_completed", details=f"completed={page_one_completed}")

        # Page 2 is only opened after TestMu was confirmed on page 1.
        page_two_results = self._click_google_page_two_and_scan()
        if page_two_results:
            page_two_completed = self._visit_all_sponsored_websites(page_two_results)
            self._step("google_page_two_site_visits_completed", details=f"completed={page_two_completed}")
        else:
            self._step("google_page_two_site_visits", "empty", "no page-2 sponsored sites")
        return True

        # Legacy single-TestMu interaction flow retained below for reference.
        target = None
        if not target:
            self._step("testmu_target", "not_found")
            logger.info("TestMu was not found; no sponsored result will be clicked")
            return False

        self._step("testmu_click_started", details=target["href"])
        logger.info(
            "TestMu sponsored result found; clicking Google result "
            f"link={target['href']}"
        )
        old_url = self.driver.current_url
        old_handles = set(self.driver.window_handles)
        self.human_simulator.mouse_hover(target["element"], hover_time=1.0)
        self.human_simulator.mouse_click_after_hover(target["element"])

        def destination_opened(_):
            new_handles = set(self.driver.window_handles) - old_handles
            if new_handles:
                self.driver.switch_to.window(next(iter(new_handles)))
                return self.driver.current_url != "about:blank"
            return self.driver.current_url != old_url

        try:
            WebDriverWait(self.driver, 8, poll_frequency=0.25).until(
                destination_opened
            )
        except TimeoutException:
            # Native cursor clicks can miss Google's dynamic ad hit area. Keep
            # the click on the sponsored anchor and use the same fallbacks as
            # the existing G2 interactions before treating it as a failure.
            logger.warning("Sponsored anchor click did not navigate; retrying")
            self._step("testmu_click_fallback", "retry")
            try:
                target["element"].click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", target["element"])
            WebDriverWait(self.driver, 22, poll_frequency=0.25).until(
                destination_opened
            )
        new_handles = set(self.driver.window_handles) - old_handles
        if new_handles:
            self.driver.switch_to.window(next(iter(new_handles)))
        WebDriverWait(self.driver, 30, poll_frequency=0.25).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logger.info(f"TestMu destination opened: {self.driver.current_url}")
        self._step("testmu_destination_opened", details=self.driver.current_url)
        from src.automation.xpath_pools import TESTMU_PAGE_POOL

        self._step(
            "testmu_browse_started",
            details="targeted visible-element interaction; random scrolling disabled",
        )

        expandable_controls = [
            element
            for element in self.driver.find_elements(
                By.XPATH,
                "//button[@aria-expanded='false'] | "
                "//*[@role='button' and @aria-expanded='false']",
            )
            if element.is_displayed()
        ]
        if expandable_controls:
            try:
                control = random.choice(expandable_controls)
                self.human_simulator.mouse_hover(control, hover_time=0.8)
                self.human_simulator.mouse_click_after_hover(control)
                logger.info("TestMu expandable control clicked")
                self._step("testmu_expandable_click")
            except Exception as error:
                logger.warning(f"TestMu expandable click skipped: {error}")
        else:
            logger.info("TestMu expandable control click: none available")

        # Exercise the exact TestMu regions supplied for this flow.
        for xpath in TESTMU_PAGE_POOL["xpaths"]["specified_image"]:
            for element in self.driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed():
                        continue
                    if not self._bring_into_view_if_needed(element):
                        logger.info(f"TestMu specified image skipped off-screen: {xpath}")
                        continue
                    self.human_simulator.mouse_hover(element, hover_time=1.2)
                    logger.info(f"TestMu specified image hovered: {xpath}")
                    self._step("testmu_specified_image_hover", details=xpath)
                except Exception as error:
                    logger.warning(f"TestMu specified image skipped: {error}")

        for xpath in TESTMU_PAGE_POOL["xpaths"]["specified_text"]:
            for element in self.driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed():
                        continue
                    if not self._bring_into_view_if_needed(element):
                        logger.info(f"TestMu specified text skipped off-screen: {xpath}")
                        continue
                    selected = self.human_simulator.select_text_in_element(element)
                    logger.info(
                        f"TestMu specified text selection: xpath={xpath} "
                        f"selected={selected}"
                    )
                    self._step("testmu_specified_text_select", details=xpath)
                except Exception as error:
                    logger.warning(
                        f"TestMu specified text selection skipped: {error}"
                    )

        for xpath in TESTMU_PAGE_POOL["xpaths"]["specified_hover"]:
            for element in self.driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed():
                        continue
                    if not self._bring_into_view_if_needed(element):
                        logger.info(f"TestMu specified hover skipped off-screen: {xpath}")
                        continue
                    self.human_simulator.mouse_hover(element, hover_time=2.0)
                    logger.info(f"TestMu specified region hovered: {xpath}")
                    self._step("testmu_specified_hover", details=xpath)
                except Exception as error:
                    logger.warning(f"TestMu specified hover skipped: {error}")

        # Dismiss common consent or announcement controls when TestMu shows
        # them. These labels are intentionally limited to non-navigation UI.
        dismiss_controls = self.driver.find_elements(
            By.XPATH,
            "//button[contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            "'accept') or contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            "'allow') or contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            "'close') or contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            "'got it')]",
        )
        visible_dismiss_controls = [
            element for element in dismiss_controls if element.is_displayed()
        ]
        if visible_dismiss_controls:
            try:
                control = visible_dismiss_controls[0]
                self.human_simulator.mouse_hover(control, hover_time=0.5)
                self.human_simulator.mouse_click_after_hover(control)
                logger.info("TestMu consent/announcement control clicked")
            except Exception as error:
                logger.warning(f"TestMu consent control skipped: {error}")

        for selection_number in range(random.randint(1, 3)):
            try:
                words = self.human_simulator.select_random_words(
                    random.randint(2, 4)
                )
                logger.info(
                    f"TestMu word selection {selection_number + 1}: {words}"
                )
            except Exception as error:
                logger.warning(f"TestMu word selection skipped: {error}")

        # Hover over a few content elements to create natural reading pauses.
        content_elements = self.driver.find_elements(
            By.CSS_SELECTOR,
            "main h1, main h2, main h3, main p, main img, "
            "article h2, article h3, section h2, section h3",
        )
        visible_content = [
            element for element in content_elements if element.is_displayed()
        ]
        for element in random.sample(
            visible_content, min(len(visible_content), random.randint(2, 5))
        ):
            try:
                self.human_simulator.mouse_hover(
                    element, hover_time=random.uniform(0.8, 2.0)
                )
            except Exception as error:
                logger.warning(f"TestMu content hover skipped: {error}")

        # Finish with a full page pass so both upper and lower sections are
        # visited even when the random pool has few matching elements.
        for direction in ():
            try:
                self.human_simulator.scroll_page(
                    total_scroll=random.randint(1, 2),
                    step_delay=random.uniform(0.12, 0.3),
                    direction=direction,
                )
                logger.info(f"TestMu full-page scroll completed: direction={direction}")
                self._step("testmu_full_scroll", details=f"direction={direction}")
            except Exception as error:
                logger.warning(
                    f"TestMu full-page scroll skipped ({direction}): {error}"
                )

        # Add explicit reading and scrolling actions so the destination is
        # explored even when the page pool finds few interactive elements.
        for action_number in range(1):
            try:
                selected = self.human_simulator.select_text_once()
                logger.info(
                    f"TestMu text selection {action_number + 1}: "
                    f"{bool(selected)}"
                )
            except Exception as error:
                logger.warning(f"TestMu text selection skipped: {error}")

            try:
                self.human_simulator.scroll_page(
                    total_scroll=random.randint(1, 2),
                    step_delay=random.uniform(0.15, 0.35),
                    direction="down",
                )
                logger.info("TestMu single scroll completed")
                self._step("testmu_scroll", details="single short downward scroll")
            except Exception as error:
                logger.warning(f"TestMu scroll skipped: {error}")

        logger.info(
            "TestMu sponsored-result flow completed with human-simulator browsing"
        )
        return True


def run_mu_flow(browser_name="Chrome"):
    """Run the standalone TestMu sponsored-result inspection from main.py."""
    # Keep Google navigation on the same helper used by the G2 workflow.
    from src.automation.google_work import GoogleSearch

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        manager = Browser(headless=False, window_size=None)
        try:
            logger.info(
                f"Starting TestMu browser attempt {attempt}/{max_attempts}"
            )
            driver, browser = manager.launch(browser_name)
            if not driver.window_handles:
                raise NoSuchWindowException(
                    "Chrome started without an available browser window"
                )
            driver.switch_to.window(driver.window_handles[0])
            logger.info(f"Browser launched for TestMu flow: {browser}")
            human_simulator = HumanSimulator(driver, use_native_cursor=True)
            google_search = GoogleSearch(driver, human_simulator)
            return TestMuAutomation(
                driver, human_simulator, google_search=google_search
            ).run()
        except NoSuchWindowException as error:
            if attempt >= max_attempts:
                logger.exception(
                    f"Chrome window closed on final attempt: {error}"
                )
                raise
            logger.warning(
                "Chrome window closed before navigation; retrying with a fresh session"
            )
            time.sleep(1)
        finally:
            try:
                manager.quit()
            except Exception as error:
                logger.warning(f"Browser cleanup skipped: {error}")
            logger.info(
                f"TestMu browser attempt {attempt}/{max_attempts} closed"
            )


def get_execution_option():
    parser = argparse.ArgumentParser(description="Run E225 automation")
    parser.add_argument(
        "--opt",
        choices=("g2", "mu"),
        default="g2",
        help="g2 runs the existing G2 process; mu checks the TestMu sponsored result",
    )
    return parser.parse_args().opt


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

    def run_g2(self, product, comparing_product, browser, location):
        # FIX: status starts as "Unknown", is upgraded step by step.
        status = "Unknown"
        link = ""
        try:
            categories = [
                'word', 'name', 'country', 'movie',
                'music', 'sports', 'technology', 'News',
            ]
            test_keywords = [
                "browser tests", "software testing", "automation tests",
                "ai in test cases", "app android", "android on browser",
            ]
            keywords_combos = [ (random.choices(categories, k=2), True), (random.choices(test_keywords, k=2), False), ]

            try:
                self.gs.search_work(keywords_combos)
            except Exception as e:
                status = f"Failed at Google Search: {e}"
                logger.exception(status)
                raise  # stop this product row; don't pretend G2 succeeded

            # --- G2 product page ---
            try:
                G2Page(
                    self.driver, self.human_simulator, product, comparing_product
                ).run_g2_product()
                link = self.driver.current_url
            except Exception as e:
                status = f"Failed at G2 Page: {e}"
                logger.exception(status)
                raise

            # --- G2 comparison page ---
            try:
                G2Comparison(
                    self.driver, self.human_simulator, comparing_product
                ).run_g2_comparisons()
                status = "Done"
            except Exception as e:
                # Comparison failure should NOT override the main success.
                status = "Failed at G2 Comparison"
                logger.exception(f"G2 comparison failed: {e}")
            # else:
            
        except Exception:
            # status already set above; ensure we never leave it as "Unknown"
            if status == "Unknown":
                status = "Failed (unknown)"
            logger.error(traceback.format_exc())

        finally:
            self.set_data(
                product, comparing_product, browser, location, status, link,
            )
            self.excel.save_excel(row=self.items)


# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Testrail", "Perfecto"],
#     }
#     location_manager = LocationManager()
#     manager = None  # FIX: initialise before try so finally can reference it.
#     vpn = None
#     try:
#         vpn = ExpressVPN()
#         locations = vpn.get_vpn_locations()

#         for product, comparing_products in products.items():
#             location = random.choice(locations)
#             # vpn.connect(location)

#             manager = Browser(headless=False)
#             driver, browser = manager.launch()
#             human_simulator = HumanSimulator(driver)
#             gs = GoogleSearch(driver, human_simulator)
#             gs.get_google()

#             for comparing_product in comparing_products:
#                 g2_project = G2Automation(driver, human_simulator, gs)
#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )

#             logger.info(f"Comparison Process Completed for {product}")
#             manager.quit(browser_name=browser)
#             manager = None  # avoid double-quit
#             # vpn.disconnect()

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         # vpn.disconnect()

# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Testrail", "Perfecto"],
#     }
#     location_manager = LocationManager()
#     manager = None
#     vpn = None
#     try:
#         vpn = ExpressVPN()

#         for product, comparing_products in products.items():
#             # ----- CHANGED: retry until a real ExpressVPN region connects -----
#             MAX_VPN_ATTEMPTS = 20
#             location = None
#             for attempt in range(1, MAX_VPN_ATTEMPTS + 1):
#                 if not location_manager.has_next():
#                     logger.error(
#                         "No VPN locations left — aborting remaining products."
#                     )
#                     break

#                 candidate = location_manager.next()
#                 try:
#                     vpn.connect(candidate)
#                     location = candidate
#                     logger.info(
#                         f"[VPN] Connected to '{candidate}' "
#                         f"on attempt {attempt}/{MAX_VPN_ATTEMPTS}"
#                     )
#                     break  # got a good one — stop retrying
#                 except Exception as e:
#                     logger.warning(
#                         f"[VPN] '{candidate}' rejected ({e}); "
#                         f"blacklisting and picking another."
#                     )
#                     location_manager.mark_failed(candidate)
#                     vpn.disconnect()
#                     continue

#             if location is None:
#                 logger.error(
#                     f"Exhausted {MAX_VPN_ATTEMPTS} attempts for '{product}' — skipping."
#                 )
#                 continue
#             # ------------------------------------------------------------------

#             for comparing_product in comparing_products:
                
#                 if Excel.check_if_present(product,comparing_product):
#                     logger.info(f"Already Done {product} and {comparing_product}")
#                     continue

#                 manager = Browser(headless=False)
#                 driver, browser = manager.launch()
#                 human_simulator = HumanSimulator(driver)
#                 gs = GoogleSearch(driver, human_simulator)
#                 gs.get_google()
#                 g2_project = G2Automation(driver, human_simulator, gs)
#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )

#                 logger.info(f"Comparison Process Completed for {product}")
#                 manager.quit(browser_name=browser)
#                 manager = None

#                 location_manager.mark_success(location)
#                 vpn.disconnect()

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         if vpn is not None:
#             try:
#                 vpn.disconnect()
#             except Exception:
#                 pass

# if __name__ == "__main__":
    # logger.info("Script Has Been Started..............")

    # products = {
    #     "SauceLabs":    ["Ranorex", "Testcomplete"],
    #     "BrowserStack": ["Testrail", "Perfecto"],
    # }
    # location_manager = LocationManager()
    # manager = None  # FIX: initialise before try so finally can reference it.
    # vpn = None
    # try:
    #     vpn = ExpressVPN()

    #     for product, comparing_products in products.items():
    #         # ----- CHANGED: use LocationManager instead of vpn.get_vpn_locations() -----
    #         if not location_manager.has_next():
    #             logger.error(
    #                 "No VPN locations left — aborting remaining products."
    #             )
    #             break
    #         location = location_manager.next()  # tiered, unused, non-blacklisted
    #         # ---------------------------------------------------------------------------

    #         try:
    #             # ----- CHANGED: actually connect the VPN for this location -----
    #             vpn.connect(location)
    #             # ---------------------------------------------------------------
    #         except Exception as e:
    #             logger.error(f"VPN connect failed for '{location}': {e}")
    #             location_manager.mark_failed(location)  # blacklist this endpoint
    #             vpn.disconnect()                        # ensure clean state
    #             continue                                # try next product's location

    #         manager = Browser(headless=False)
    #         driver, browser = manager.launch()
    #         human_simulator = HumanSimulator(driver)
    #         gs = GoogleSearch(driver, human_simulator)
    #         gs.get_google()

    #         for comparing_product in comparing_products:
    #             g2_project = G2Automation(driver, human_simulator, gs)
    #             try:
    #                 g2_project.run_g2(product, comparing_product, browser, location)
    #             except Exception as e:
    #                 logger.error(
    #                     f"run_g2 failed for {product}/{comparing_product}: {e}"
    #                 )

    #         logger.info(f"Comparison Process Completed for {product}")
    #         manager.quit(browser_name=browser)
    #         manager = None  # avoid double-quit

    #         # ----- CHANGED: report success + disconnect the VPN -----
    #         location_manager.mark_success(location)
    #         vpn.disconnect()
    #         # --------------------------------------------------------

    # except Exception:
    #     logger.error(traceback.format_exc())
    # finally:
    #     if manager is not None:
    #         try:
    #             manager.quit()
    #         except Exception:
    #             pass
    #     # ----- CHANGED: actually disconnect the VPN in finally -----
    #     if vpn is not None:
    #         try:
    #             vpn.disconnect()
    #         except Exception:
    #             pass
    #     # -----------------------------------------------------------

# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Qase", "accessiBe"],
#     }
#     location_manager = LocationManager()
#     manager = None
#     vpn = None

#     # ----- CHANGED: configurable waits -----
#     VPN_SETTLE_WAIT      = 5   # after connect, before opening browser
#     POST_DISCONNECT_WAIT = 3   # after disconnect, before next connect/browser
#     MAX_VPN_ATTEMPTS     = 20
#     # --------------------------------------

#     try:
#         vpn = ExpressVPN()
        

#         for product, comparing_products in products.items():

#             for comparing_product in comparing_products:

#                 # if Excel().check_if_present(product, comparing_product):
#                 #     logger.info(f"Already Done {product} and {comparing_product}")
#                 #     continue
#                 # # ---------------------------------------------------------------------

#                 # ----- CHANGED: VPN retry loop moved INSIDE comparing_products -----
#                 location = None
#                 for attempt in range(1, MAX_VPN_ATTEMPTS + 1):
#                     if not location_manager.has_next():
#                         logger.error(
#                             "No VPN locations left — aborting remaining work."
#                         )
#                         break

#                     candidate = location_manager.next()
#                     try:
#                         vpn.connect(candidate)
#                         location = candidate
#                         logger.info(
#                             f"[VPN] Connected to '{candidate}' "
#                             f"on attempt {attempt}/{MAX_VPN_ATTEMPTS}"
#                         )
#                         break  # got a good one
#                     except Exception as e:
#                         logger.warning(
#                             f"[VPN] '{candidate}' rejected ({e}); "
#                             f"blacklisting and picking another."
#                         )
#                         location_manager.mark_failed(candidate)
#                         vpn.disconnect()
#                         time.sleep(POST_DISCONNECT_WAIT)  # cool down before retry
#                         continue

#                 if location is None:
#                     logger.error(
#                         f"Exhausted {MAX_VPN_ATTEMPTS} attempts for "
#                         f"'{product}/{comparing_product}' — skipping."
#                     )
#                     continue

#                 # ----- CHANGED: wait for the tunnel to actually stabilize -----
#                 time.sleep(VPN_SETTLE_WAIT)
#                 # ---------------------------------------------------------------

#                 # ----- CHANGED: fresh browser per comparing_product -----
#                 manager = Browser(headless=False)
#                 driver, browser = manager.launch()
#                 human_simulator = HumanSimulator(driver)
#                 gs = GoogleSearch(driver, human_simulator)
#                 gs.get_google()
#                 g2_project = G2Automation(driver, human_simulator, gs)

#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                     logger.info(
#                         f"Comparison Process Completed for "
#                         f"{product}/{comparing_product} via '{location}'"
#                     )
#                     location_manager.mark_success(location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )
#                     location_manager.mark_failed(location)  # endpoint may be bad
#                 finally:
#                     # ----- CHANGED: always close browser, then disconnect VPN -----
#                     if manager is not None:
#                         try:
#                             manager.quit(browser_name=browser)
#                         except Exception:
#                             pass
#                         manager = None

#                     try:
#                         vpn.disconnect()
#                     except Exception:
#                         pass

#                     # ----- CHANGED: wait AFTER disconnect, BEFORE next browser -----
#                     time.sleep(POST_DISCONNECT_WAIT)
#                     # -----------------------------------------------------------------
#                 # ------------------------------------------------------------------------

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         if vpn is not None:
#             try:
#                 vpn.disconnect()
#             except Exception:
#                 pass

if __name__ == "__main__":
    logger.info("Script Has Been Started..............")

    execution_option = get_execution_option()
    logger.info(f"Selected execution option: {execution_option}")
    if execution_option == "mu":
        try:
            run_mu_flow()
        except Exception as error:
            logger.exception(f"TestMu flow failed: {error}")
            raise
        sys.exit(0)
    else:
        # Load G2-only dependencies only for the original G2 workflow.
        from src.automation.google_work import GoogleSearch
        from src.automation.G2_comparison import G2Comparison
        from src.automation.G2_page import G2Page
        from src.automation.errors import AccessDeniedError

    products = {
        "SauceLabs":    ["Ranorex", "TestComplete"],
        "BrowserStack": ["Qase", "accessiBe"],
    }
    USE_VPN = False  # Local development: set True when VPN testing is needed.
    location_manager = LocationManager() if USE_VPN else None
    manager = None
    vpn = None

    # ----- configurable waits / attempts -----
    VPN_SETTLE_WAIT      = 5    # after connect, before opening browser
    POST_DISCONNECT_WAIT = 3    # after disconnect, before next connect/browser
    MAX_VPN_ATTEMPTS     = 20   # per (product, comparing_product)
    # -----------------------------------------

    try:
        if USE_VPN:
            vpn = ExpressVPN()
        else:
            logger.info("VPN disabled for local development")
        done_browser = []
        for product, comparing_products in products.items():
            for comparing_product in comparing_products:

                # if Excel().check_if_present(product, comparing_product):
                #     logger.info(f"Already Done {product} and {comparing_product}")
                #     continue

                # =========================================================
                # RESTART LOOP:
                # Each iteration of this loop is one complete attempt for
                # this (product, comparing_product) pair on a fresh VPN.
                # If G2 raises AccessDeniedError anywhere in the flow, we
                # tear down browser + VPN, blacklist the location, and
                # come back here to try again with a new VPN.
                # =========================================================
                if Excel().check_if_completed(product, comparing_product):
                    logger.info(f"Already Done {product} and {comparing_product}")
                    continue 
                
                logger.info(f"Starting comparison for {product} and {comparing_product}")
                pair_done = False

                pair_attempts = MAX_VPN_ATTEMPTS if USE_VPN else 1
                for pair_attempt in range(1, pair_attempts + 1):

                    # ---- pick + connect a fresh VPN -----------------
                    location = "Local"
                    if USE_VPN:
                        location = None
                        for vpn_attempt in range(1, MAX_VPN_ATTEMPTS + 1):
                            if not location_manager.has_next():
                                logger.error(
                                    "No VPN locations left — aborting remaining work."
                                )
                                break

                            candidate = location_manager.next()
                            try:
                                vpn.connect(candidate)
                                location = candidate
                                logger.info(
                                    f"[VPN] Connected to '{candidate}' "
                                    f"(pair attempt {pair_attempt}/"
                                    f"{MAX_VPN_ATTEMPTS}, "
                                    f"connect try {vpn_attempt}/"
                                    f"{MAX_VPN_ATTEMPTS})"
                                )
                                break
                            except Exception as e:
                                logger.warning(
                                    f"[VPN] '{candidate}' rejected ({e}); "
                                    f"blacklisting and picking another."
                                )
                                location_manager.mark_failed(candidate)
                                vpn.disconnect()
                                time.sleep(POST_DISCONNECT_WAIT)
                                continue

                    if location is None:
                        logger.error(
                            f"Exhausted VPN connect attempts for "
                            f"'{product}/{comparing_product}' — skipping."
                        )
                        break   # out of pair_attempt loop, move to next pair

                    # ---- let the tunnel stabilise -------------------
                    if USE_VPN:
                        time.sleep(VPN_SETTLE_WAIT)

                    # ---- fresh browser per attempt ------------------
                    manager = Browser(headless=False,done_browser=done_browser)
                    driver, browser = manager.launch()
                    done_browser.append(browser)
                    human_simulator = HumanSimulator(driver)
                    gs = GoogleSearch(driver, human_simulator)
                    gs.get_google()
                    
                    g2_project = G2Automation(driver, human_simulator, gs)

                    retry_needed = False

                    try:
                        g2_project.run_g2(
                            product, comparing_product, browser, location
                        )
                        logger.info(
                            f"Comparison Process Completed for "
                            f"{product}/{comparing_product} via '{location}'"
                        )
                        if USE_VPN:
                            location_manager.mark_success(location)
                        pair_done = True

                    except AccessDeniedError as blocked:
                        # ---- CHANGED: restart the WHOLE pair on a new VPN ----
                        logger.warning(
                            f"[RETRY] Access denied for "
                            f"{product}/{comparing_product} on '{location}': "
                            f"{blocked}. Restarting flow with a new VPN."
                        )
                        if USE_VPN:
                            location_manager.mark_failed(location)
                            retry_needed = True
                        else:
                            logger.warning(
                                "VPN retry is disabled in local development mode"
                            )
                            pair_done = True

                    except Exception as e:
                        logger.error(
                            f"run_g2 failed for {product}/{comparing_product}: {e}"
                        )
                        if USE_VPN:
                            location_manager.mark_failed(location)
                        # Non-AccessDenied failures: do NOT restart the whole
                        # pair with a new VPN — it's most likely a code / data
                        # problem, not a network block.
                        pair_done = True   # give up on this pair this run

                    finally:
                        # Always close the browser, then disconnect the VPN,
                        # then wait before the next attempt/connect.
                        if manager is not None:
                            try:
                                manager.quit(browser_name=browser)
                            except Exception:
                                pass
                            manager = None

                        if USE_VPN and vpn is not None:
                            try:
                                vpn.disconnect()
                            except Exception:
                                pass
                            time.sleep(POST_DISCONNECT_WAIT)

                    if pair_done:
                        break   # done with this pair for this run
                    if retry_needed:
                        continue   # loop back, pick a new VPN, restart pair

                # ---- end of pair_attempt loop -----------------------

    except Exception:
        logger.error(traceback.format_exc())
    finally:
        if manager is not None:
            try:
                manager.quit()
            except Exception:
                pass
        if vpn is not None:
            try:
                vpn.disconnect()
            except Exception:
                pass
