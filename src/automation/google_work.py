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
class GoogleSearch:

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    # ---------------- captcha solving ---------------- #

    # def solve_captcha(
    #     self,
    #     api_key: str | None = None,
    #     *,
    #     max_retries: int = 3,
    #     retry_delay: int = 5,
    #     submit: bool = True,
    # ) -> str | None:

    #     import os
    #     import time
    #     from twocaptcha import TwoCaptcha, ApiException
    #     from selenium.webdriver.common.by import By


    #     if self.driver is None:
    #         raise RuntimeError(
    #             "No active browser. Call Browser.launch() first."
    #         )

    #     api_key = api_key or os.environ.get("APIKEY_2CAPTCHA")
    #     if not api_key:
    #         raise ValueError(
    #             "2Captcha API key missing. Pass api_key= or set "
    #             "APIKEY_2CAPTCHA env var."
    #         )

    #     solver = TwoCaptcha(api_key)
    #     driver = self.driver
    #     url = driver.current_url

    #     # ---------- extract sitekey ----------
    #     try:
    #         sitekey = driver.execute_script("""
    #             const el = document.querySelector('[data-sitekey]');
    #             if (el) return el.getAttribute('data-sitekey');
    #             const iframe = document.querySelector(
    #                 'iframe[src*="recaptcha"]'
    #             );
    #             if (iframe) {
    #                 const m = iframe.src.match(/[?&]k=([^&]+)/);
    #                 if (m) return decodeURIComponent(m[1]);
    #             }
    #             return null;
    #         """)
    #     except Exception as exc:
    #         print(f"[captcha] sitekey extraction failed: {exc}")
    #         sitekey = None

    #     if not sitekey:
    #         print("[captcha] No reCAPTCHA sitekey found on this page.")
    #         return None
    #     print(f"[captcha] Found sitekey: {sitekey}")

    #     # ---------- extract data-s (Google Search) ----------
    #     try:
    #         data_s = driver.execute_script("""
    #             const el = document.querySelector('[data-s]');
    #             if (el) return el.getAttribute('data-s');
    #             const iframe = document.querySelector(
    #                 'iframe[src*="recaptcha"]'
    #             );
    #             if (iframe) {
    #                 const m = iframe.src.match(/[?&]s=([^&]+)/);
    #                 if (m) return m[1];
    #             }
    #             const scripts = document.querySelectorAll('script');
    #             for (const s of scripts) {
    #                 const m = s.textContent.match(
    #                     /data-s["']?\\s*[:=]\\s*["']([^"']+)["']/
    #                 );
    #                 if (m) return m[1];
    #             }
    #             return null;
    #         """)
    #     except Exception:
    #         data_s = None

    #     if data_s:
    #         print(f"[captcha] Found data-s: {data_s[:20]}...")


    #     # ---------- solve with retries ----------
    #     token = None
    #     for attempt in range(1, max_retries + 1):
    #         try:
    #             print(f"[captcha] Attempt {attempt}/{max_retries}...")
    #             params = {"sitekey": sitekey, "url": url}
    #             if data_s:
    #                 params["datas"] = data_s

    #             result = solver.recaptcha(**params)
    #             token = result["code"]
    #             print("[captcha] Solved successfully.")
    #             break

    #         except ApiException as exc:
    #             msg = str(exc)
    #             if (
    #                 "cannot recognize response" in msg
    #                 or "ERROR_CAPTCHA_UNSOLVABLE" in msg
    #                 or "ERROR_NO_SLOT_AVAILABLE" in msg
    #             ):
    #                 print(
    #                     f"[captcha] Transient error, retrying in "
    #                     f"{retry_delay}s: {msg[:80]}"
    #                 )
    #                 time.sleep(retry_delay)
    #                 if data_s:
    #                     try:
    #                         data_s = self.driver.execute_script("""
    #                             const el = document.querySelector('[data-s]');
    #                             return el ? el.getAttribute('data-s') : null;
    #                         """)
    #                     except Exception:
    #                         pass
    #             else:
    #                 print(f"[captcha] Fatal API error: {msg}")
    #                 return None

    #         except Exception as exc:
    #             print(f"[captcha] Unexpected error: {exc}")
    #             return None

    #     if not token:
    #         print("[captcha] Failed to obtain token after retries.")
    #         return None

    #     # ---------- inject token ----------
    #     try:
    #         driver.execute_script("""
    #             const el = document.getElementById('g-recaptcha-response');
    #             if (!el) return;
    #             el.value = arguments[0];
    #             el.innerHTML = arguments[0];
    #             el.dispatchEvent(new Event('input',  { bubbles: true }));
    #             el.dispatchEvent(new Event('change', { bubbles: true }));
    #         """, token)

    #         # Fire the callback declared on the widget, if any
    #         callback = driver.execute_script("""
    #             const el = document.querySelector('[data-callback]');
    #             return el ? el.getAttribute('data-callback') : null;
    #         """)
    #         if callback:
    #             try:
    #                 driver.execute_script(
    #                     f"window['{callback}'](arguments[0]);", token
    #                 )
    #             except Exception as exc:
    #                 print(f"[captcha] Callback '{callback}' failed: {exc}")
    #     except Exception as exc:
    #         print(f"[captcha] Token injection failed: {exc}")
    #         return None

    #     # ---------- submit ----------
    #     if submit:
    #         try:
    #             btn = driver.find_element(
    #                 By.CSS_SELECTOR,
    #                 "button[type='submit'], input[type='submit'], #recaptcha-verify-button",
    #             )
    #             btn.click()
    #             print("[captcha] Submitted form.")
    #         except Exception:
    #             # Many Google CAPTCHAs auto-submit after the callback fires.
    #             print("[captcha] No submit button found; relying on callback.")

    #     return token

    # def check_for_bot(self):
    #     captcha = '//*[contains(.,"Sometimes you may be asked to solve the CAPTCHA")]'
    #     if self.driver.find_elements(By.XPATH, captcha):
    #         logger.warning("Bot detected!")
    #         token = self.solve_captcha(api_key="abc")

    #         self.driver.execute_script("""
    #         const el = document.getElementById('g-recaptcha-response');
    #         if (el) {
    #             el.value = arguments[0];
    #             el.dispatchEvent(new Event('input', { bubbles: true }));
    #             el.dispatchEvent(new Event('change', { bubbles: true }));
    #         }
    #     """, token)

    #     try:
    #         submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
    #         submit_btn.click()
    #     except:

    #         pass

    # ---------------- captcha solving ---------------- #

    def solve_captcha(
        self,
        api_key: str | None = None,
        *,
        max_retries: int = 3,
        retry_delay: int = 5,
    ) -> str | None:
        """Solve the reCAPTCHA on the current page using 2Captcha."""

        if self.driver is None:
            raise RuntimeError("No active browser. Call Browser.launch() first.")

        api_key = api_key or os.environ.get("APIKEY_2CAPTCHA")
        if not api_key:
            raise ValueError(
                "2Captcha API key missing. Pass api_key= or set "
                "APIKEY_2CAPTCHA env var."
            )

        solver = TwoCaptcha(api_key)
        
        url = self.driver.current_url

        # ---------- extract sitekey ----------
        try:
            sitekey = self.driver.execute_script("""
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');
                const iframe = document.querySelector('iframe[src*="recaptcha"]');
                if (iframe) {
                    const m = iframe.src.match(/[?&]k=([^&]+)/);
                    if (m) return decodeURIComponent(m[1]);
                }
                return null;
            """)
        except Exception as exc:
            logger.error(f"[captcha] sitekey extraction failed: {exc}")
            sitekey = None

        if not sitekey:
            logger.warning("[captcha] No reCAPTCHA sitekey found on this page.")
            return None
        logger.info(f"[captcha] Found sitekey: {sitekey}")

        # ---------- extract data-s (Google Search) ----------
        try:
            data_s = self.driver.execute_script("""
                const el = document.querySelector('[data-s]');
                if (el) return el.getAttribute('data-s');
                const iframe = document.querySelector('iframe[src*="recaptcha"]');
                if (iframe) {
                    const m = iframe.src.match(/[?&]s=([^&]+)/);
                    if (m) return m[1];
                }
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const m = s.textContent.match(
                        /data-s["']?\\s*[:=]\\s*["']([^"']+)["']/
                    );
                    if (m) return m[1];
                }
                return null;
            """)
        except Exception:
            data_s = None

        if data_s:
            logger.info(f"[captcha] Found data-s: {data_s[:20]}...")

        # ---------- solve with retries ----------
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

            except ApiException as exc:
                msg = str(exc)
                if (
                    "cannot recognize response" in msg
                    or "ERROR_CAPTCHA_UNSOLVABLE" in msg
                    or "ERROR_NO_SLOT_AVAILABLE" in msg
                ):
                    logger.warning(
                        f"[captcha] Transient error, retrying in "
                        f"{retry_delay}s: {msg[:80]}"
                    )
                    time.sleep(retry_delay)
                    # data-s is single-use: refresh before retry
                    if data_s:
                        try:
                            data_s = self.driver.execute_script("""
                                const el = document.querySelector('[data-s]');
                                return el ? el.getAttribute('data-s') : null;
                            """)
                        except Exception:
                            pass
                else:
                    logger.error(f"[captcha] Fatal API error: {msg}")
                    return None

            except Exception as exc:
                logger.error(f"[captcha] Unexpected error: {exc}")
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

        # # ---------- submit ----------
        # if submit:
        #     try:
        #         btn = self.driver.find_element(
        #             By.CSS_SELECTOR,
        #             "button[type='submit'], input[type='submit'], #recaptcha-verify-button",
        #         )
        #         btn.click()
        #         logger.info("[captcha] Submitted form.")
        #     except Exception:
        #         logger.info("[captcha] No submit button; relying on callback.")

        return token

    # ---------------- bot detection ---------------- #

    def check_for_bot(self) -> bool:
        """
        Detects the Google 'unusual traffic' CAPTCHA page and attempts to
        solve it. Returns True if a CAPTCHA was found and handled,
        False otherwise.
        """

        # api_key = os.environ.get("APIKEY_2CAPTCHA")
        api_key = "8ed5397bd9db6500a766bf0c13905453"
        captcha_xpath = (
            '//*[contains(., "Sometimes you may be asked to solve the CAPTCHA") '
            'or contains(., "unusual traffic")]'
        )

        try:
            found = bool(self.driver.find_elements(By.XPATH, captcha_xpath))
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


    def search_work(self, keyword_combos):
        
        for keyword_combo in keyword_combos:
            keywords = keyword_combo[0]
            sug = keyword_combo[1]

            for keyword in keywords:
                query = get_random_word_or_sentence_faker(keyword).lower()

                wait_for_element(
                    self.driver,
                    (By.XPATH, '//*[@aria-label="Google"]'),
                    condition="visible",
                )

                pop_up = self.driver.find_elements(By.XPATH, '//button[@aria-haspopup="true"]')

                if pop_up:
                    self.human_simulator.mouse_click_after_hover(pop_up[0])
                    logger.info(f"Pop up closed for {keyword}")
                    time.sleep(random.uniform(0.5, 1))
                    
                    self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH,"//li[contains(text(),'English (United Kingdom)')]" ))
                    refuse_xpath = "//*[contains(text(),'Reject all')]"
                    
                    if self.driver.find_elements(By.XPATH,refuse_xpath):
                        self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, refuse_xpath))
                        logger.info(f"Reject All done")
                
                try:
                    self.human_simulator.input_search_query(query,suggestion=sug)
                except Exception:
                    logger.info("Google page may not have opened correctly, retrying.")
                    self.get_google(query=keyword)
                
                self.check_for_bot()

                wait_for_element(
                    self.driver,
                    (By.XPATH, '//a[@aria-label="Go to Google Home"]'),
                    condition="visible",
                )

                xpath_trans = self.change_in_eng()

                if xpath_trans:
                    try:
                        self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, xpath_trans))
                    except (StaleElementReferenceException, NoSuchElementException):
                        # Page changed under us. Retry once, or just carry on without it.
                        xpath_trans = self.change_in_eng(timeout=1)
                        if xpath_trans:
                            self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, xpath_trans))

                # if xpath_trans:
                #     self.human_simulator.mouse_click_after_hover(
                #         self.driver.find_element(By.XPATH, xpath_trans)
                #     )
                #     logger.info(f"Translation done for {keyword}")

                refuse_xpath = "//*[contains(text(),'Reject all')]"
                
                if self.driver.find_elements(By.XPATH,refuse_xpath):
                    self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, refuse_xpath))
                    logger.info(f"Reject All done")
                
                save_html(html_text=self.driver.page_source, file_name=query)

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
                    duration=10, pool=GOOGLE_RESULTS_POOL
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
            wait_for_element(self.driver, (By.XPATH, trans_xpath), timeout=3, condition="clickable")

            if self.driver.find_elements(By.XPATH, trans_xpath):
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