import random
import os,time
from pathlib import Path
from urllib.parse import quote_plus
from httpcore import TimeoutException
from selenium.webdriver.common.by import By
from src.logging import logger
from src.commons import wait_for_element, save_html, get_random_word_or_sentence_faker
from src.automation.xpath_pools import GOOGLE_RESULTS_POOL
from twocaptcha import TwoCaptcha, ApiException
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
)
from dotenv import load_dotenv
load_dotenv()

class GoogleSearch:

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    # ---------------- captcha solving ---------------- #

    def solve_captcha(
    self,
    api_key: str | None = None,
    *,
    max_retries: int = 3,
    retry_delay: int = 3,
    reload_on_unsolvable: bool = True,
) -> str | None:
        """Solve the reCAPTCHA on the current page using 2Captcha."""

        if self.driver is None:
            raise RuntimeError("No active browser. Call Browser.launch() first.")

        api_key = api_key or os.environ.get('APIKEY_2CAPTCHA')
        if not api_key:
            raise ValueError(
                "2Captcha API key missing. Pass api_key= or set "
                "APIKEY_2CAPTCHA env var."
            )

        solver = TwoCaptcha(api_key)

        # --- helper: extract BOTH sitekey and data-s in one pass ---
        def _extract_tokens():
            try:
                return self.driver.execute_script("""
                    let sitekey = null, data_s = null;

                    // 1. direct element attrs
                    const skEl = document.querySelector('[data-sitekey]');
                    if (skEl) sitekey = skEl.getAttribute('data-sitekey');
                    const dsEl = document.querySelector('[data-s]');
                    if (dsEl) data_s = dsEl.getAttribute('data-s');

                    // 2. iframe src
                    const iframe = document.querySelector('iframe[src*="recaptcha"]');
                    if (iframe) {
                        if (!sitekey) {
                            const mk = iframe.src.match(/[?&]k=([^&]+)/);
                            if (mk) sitekey = decodeURIComponent(mk[1]);
                        }
                        if (!data_s) {
                            const ms = iframe.src.match(/[?&]s=([^&]+)/);
                            if (ms) data_s = ms[1];
                        }
                    }

                    // 3. script tags
                    if (!data_s) {
                        for (const s of document.querySelectorAll('script')) {
                            const m = s.textContent.match(
                                /data-s["']?\\s*[:=]\\s*["']([^"']+)["']/
                            );
                            if (m) { data_s = m[1]; break; }
                        }
                    }
                    return {sitekey, data_s};
                """)
            except Exception as exc:
                logger.error(f"[captcha] token extraction failed: {exc}")
                return {"sitekey": None, "data_s": None}

        tokens = _extract_tokens()
        sitekey, data_s = tokens["sitekey"], tokens["data_s"]

        if not sitekey:
            logger.warning("[captcha] No reCAPTCHA sitekey found on this page.")
            return None
        logger.info(f"[captcha] Found sitekey: {sitekey}")
        if data_s:
            logger.info(f"[captcha] Found data-s: {data_s[:20]}...")

        url = self.driver.current_url
        token = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[captcha] Attempt {attempt}/{max_retries}...")
                params = {"sitekey": sitekey, "url": url}
                if data_s:
                    params["datas"] = data_s

                result = solver.recaptcha(**params)
                token = result["code"]
                logger.info("[captcha] Solved successfully.")
                break

            except Exception as exc:
                # --- FIX: match on the message text, not on the exception class ---
                msg = str(exc)
                logger.warning(f"[captcha] Attempt {attempt} failed: {msg[:120]}")

                is_unsolvable = "ERROR_CAPTCHA_UNSOLVABLE" in msg
                is_transient  = (
                    "cannot recognize response" in msg
                    or "ERROR_NO_SLOT_AVAILABLE" in msg
                    or "ERROR_RECAPTCHA_TIMEOUT" in msg
                )

                if attempt >= max_retries:
                    logger.error(f"[captcha] Giving up after {max_retries} attempts.")
                    return None

                if is_unsolvable and reload_on_unsolvable:
                    # --- FIX: reload the page so Google issues a FRESH data-s ---
                    logger.info(
                        "[captcha] Unsolvable challenge; reloading page for "
                        "a fresh data-s..."
                    )
                    try:
                        self.driver.refresh()
                        time.sleep(random.uniform(1, 3))
                    except Exception as refresh_exc:
                        logger.warning(f"[captcha] Refresh failed: {refresh_exc}")

                    # re-extract tokens after reload
                    tokens = _extract_tokens()
                    sitekey, data_s = tokens["sitekey"], tokens["data_s"]
                    url = self.driver.current_url

                    if not sitekey:
                        logger.error("[captcha] sitekey gone after reload; aborting.")
                        return None
                    logger.info(f"[captcha] New data-s: "
                                f"{(data_s or 'None')[:20]}...")

                elif is_transient:
                    logger.info(f"[captcha] Transient error; sleeping {retry_delay}s.")
                    time.sleep(retry_delay)

                else:
                    logger.error(f"[captcha] Fatal error: {msg}")
                    return None

        if not token:
            logger.error("[captcha] Failed to obtain token after retries.")
            return None

        # ---------- inject token ----------
        try:
            self.driver.execute_script("""
                const el = document.getElementById('g-recaptcha-response');
                if (!el) return;
                el.value = arguments[0];
                el.innerHTML = arguments[0];
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            """, token)

            callback = self.driver.execute_script("""
                const el = document.querySelector('[data-callback]');
                return el ? el.getAttribute('data-callback') : null;
            """)
            if callback:
                try:
                    self.driver.execute_script(
                        f"window['{callback}'](arguments[0]);", token
                    )
                except Exception as exc:
                    logger.warning(f"[captcha] Callback '{callback}' failed: {exc}")
        except Exception as exc:
            logger.error(f"[captcha] Token injection failed: {exc}")
            return None

        return token
    # ---------------- bot detection ---------------- #

    def check_for_bot(self) -> bool:
        """
        Detects the Google 'unusual traffic' CAPTCHA page and attempts to
        solve it. Returns True if a CAPTCHA was found and handled,
        False otherwise.
        """
        # input("Catcha check: Press Enter to continue...")
        try:
            api_key = os.environ.get("APIKEY_2CAPTCHA")
        except Exception as exc:
            logger.error(f"[check_for_bot] Failed to read API key: {exc}")
            return False
        
        captcha_xpath = (
            '//*[contains(., "Sometimes you may be asked to solve the CAPTCHA") '
            'or contains(., "unusual traffic")]'
        )

        try:
            found = bool(wait_for_element(self.driver, locator = (By.XPATH, captcha_xpath),timeout=3, condition="visible", poll=0.5))
        except Exception as exc:
            logger.error(f"[check_for_bot] DOM query failed: {exc}")
            return False

        if not found:
            logger.info("[check_for_bot] No bot detection page found.")
            return False

        logger.warning("[check_for_bot] Bot detected — solving CAPTCHA...")

        token = self.solve_captcha(api_key=api_key)

        if not token:
            logger.error("[check_for_bot] CAPTCHA solve failed.")
            return False

        logger.info("[check_for_bot] CAPTCHA solved and submitted.")
        return True

    def check_for_pop_up(self,keyword):
        pop_up = self.driver.find_elements(By.XPATH, '//button[@aria-haspopup="true"]')

        if pop_up:
            self.human_simulator.mouse_click_after_hover(pop_up[0])
            logger.info(f"Pop up closed for {keyword}")
            time.sleep(random.uniform(0.2, 1))
            
            self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH,"//li[contains(text(),'English (United Kingdom)')]" ))
            refuse_xpath = "//button[contains(.,'Reject all')]"
            
            if self.driver.find_elements(By.XPATH,refuse_xpath):
                self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, refuse_xpath))
                logger.info(f"Reject All done")
        

    def search_work(self, keyword_combos):
        
        for keyword_combo in keyword_combos:
            keywords = keyword_combo[0]
            sug = keyword_combo[1]
            need_full = keyword_combo[2]
            for keyword in keywords:
                query = get_random_word_or_sentence_faker(keyword).lower()

                wait_for_element(
                    self.driver,
                    (By.XPATH, '//*[@aria-label="Google"]'),
                    condition="visible",
                    timeout=3
                )

                self.check_for_pop_up(keyword)
                
                try:
                    self.human_simulator.input_search_query(query,suggestion=sug,need_full=need_full)
                except Exception:
                    logger.info("Google page may not have opened correctly, retrying.")
                    self.get_google(query=keyword)
                
                self.check_for_bot()

                wait_for_element(
                    self.driver,
                    (By.XPATH, '//a[@aria-label="Go to Google Home"]'),
                    condition="visible",
                    timeout=3
                )

                self.check_for_pop_up(keyword)
                
                self.change_in_eng()
                
                clicked = False

                for attempt in range(7):
                    try:
                        elem_xpath = self.get_elem_xpaths()
                        logger.info(f"Attempt {attempt + 1}: Elem XPath found: {elem_xpath}")
                        try:
                            element = self.driver.find_element(By.XPATH, elem_xpath)
                            self.human_simulator.move_to_element_like_human(element)
                            self.human_simulator.mouse_click_after_hover(
                                self.driver.find_element(By.XPATH, elem_xpath)
                            )
                            clicked = True
                            break
                        except Exception as e:
                            logger.warning(f"{elem_xpath} not found")
                            self.human_simulator.scroll_page(
                                total_scroll=5, step_delay=0.3, direction="down"
                            )
                    except Exception as e:
                        logger.error(f"random_words failed for keyword '{keyword}' ")

                if not clicked:
                    logger.error(
                        f"Could not find/click any element after 7 attempts "
                        f"for query '{query}'"
                    )
                self.human_simulator.browse_page_randomly(
                    duration=5, pool=GOOGLE_RESULTS_POOL
                )

    def get_google(self, query=None, blocked=False):
        url = "https://www.google.com"
        if query:
            # FIX: URL-encode the query string.
            url += f"/search?q={quote_plus(str(query))}"

        # FIX: nested double quotes inside f-string broke on Python < 3.12.
        host = url.split("www.")[-1].split(".com")[0]
        logger.info(f"{'-' * 10}Hitting {host} Url {'-' * 10}")
        
        self.driver.get(url)

    def change_in_eng(self):
        trans_xpath = "//a[contains(text(),'Change to English')]"
        try:
            # wait_for_element(self.driver, (By.XPATH, trans_xpath), timeout=3, condition="clickable")

            if self.driver.find_elements(By.XPATH, trans_xpath):
                self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, trans_xpath))
                return trans_xpath
        except Exception as e:
            logger.info("No translation link found.")
            return None
        return None

    def get_elem_xpaths(self):
        ai_show_more = '//*[@aria-label="Show more AI Overview"]'
        people_ask_for = (
            '//*[text()="People also ask"]/../../following-sibling::div/'
            'div[not(@class)]//*[@data-hveid and @data-ved and count(@*)=2]'
        )
        img_show_more = "//*[contains(text(),'Show more images')]/ancestor::div[@data-ved][1]"
        read_more = '//*[@aria-label="Show more AI Overview"]'
        return random.choice([ai_show_more, people_ask_for, img_show_more, read_more])