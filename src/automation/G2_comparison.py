import random
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from ..commons import wait_for_element
from ..logging import logger

# G2 review page used by the comparison flow.
# Override this value if your target review URL is different.

class G2Comparison:
    # g2_reviews_url = "https://www.g2.com/products/sauce-labs/reviews"

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    # ==================================================================
    # OPEN G2 COMPARE PAGE
    # ==================================================================
    def open_g2_compare_page(self):

        logger.info("Opening Sauce Labs reviews page...")

        # self.driver.get(self.g2_reviews_url)

        # wait_for_element(self.driver,(By.TAG_NAME, "body"),condition="presence",timeout=30,poll=0.5)

        # time.sleep(random.uniform(3, 5))

        # logger.info("Sauce Labs reviews page opened.")

        # =====================================================
        # HANDLE COOKIE CONSENT BANNER
        # =====================================================

        try:
            cookie_banner = self.driver.find_elements(
                By.XPATH,
                '//div[@role="dialog" and @aria-label="Cookie Consent Banner"]',
            )

            if cookie_banner:
                logger.info("Cookie Consent Banner found.")

                cookie_buttons = cookie_banner[0].find_elements(
                    By.XPATH, ".//button"
                )

                for button in cookie_buttons:
                    try:
                        if button.is_displayed():
                            logger.info(
                                f"Cookie button found: {button.text.strip()}"
                            )
                            button.click()
                            time.sleep(random.randint(1,3))
                            logger.info("Cookie Consent handled.")
                            break
                    except Exception:
                        continue

        except Exception as error:
            logger.warning(f"Cookie Consent handling skipped: {error}")

        # =====================================================
        # COMPARISON BLOCK
        # =====================================================

        compare_xpath = '(//div[@class="elv-flex elv-items-center"])[69]'

        logger.info("Searching for comparison block...")

        start_time = time.time()

        while time.time() - start_time < 30:
            try:
                compare_element = self.driver.find_element(
                    By.XPATH, compare_xpath
                )
                if compare_element.is_displayed():
                    logger.info("Comparison block found.")
                    break
            except Exception:
                pass

            # scroll_page(total_scroll=None, step_delay=None, direction=None)

            self.driver.execute_script(
                "window.scrollBy(0, arguments[0]);",
                random.randint(500, 800),
            )

            time.sleep(random.uniform(0.5, 1))

        else:
            raise Exception("Comparison block was not found.")

        # =====================================================
        # CLICK COMPARISON BUTTON
        # =====================================================

        compare_element = wait_for_element(
            self.driver,
            (By.XPATH, compare_xpath),
            condition="clickable",
            timeout=10,
            poll=0.5,
        )

        logger.info("Clicking comparison button...")

        try:
            compare_element.click()

        except Exception:
            logger.warning("Normal click intercepted.")

            try:
                cookie_banner = self.driver.find_elements(
                    By.XPATH,
                    '//div[@role="dialog" and @aria-label="Cookie Consent Banner"]',
                )
                if cookie_banner:
                    cookie_buttons = cookie_banner[0].find_elements(
                        By.XPATH, ".//button"
                    )
                    for button in cookie_buttons:
                        try:
                            if button.is_displayed():
                                button.click()
                                time.sleep(1)
                                break
                        except Exception:
                            continue
            except Exception:
                pass

            compare_element = wait_for_element(
                self.driver,
                (By.XPATH, compare_xpath),
                condition="clickable",
                timeout=10,
                poll=0.5,
            )

            compare_element.click()

        logger.info("Comparison button clicked.")

        time.sleep(random.uniform(3, 5))

    # ==================================================================
    # BROWSE COMPARISON PAGE
    # ==================================================================
    def browse_comparison_page(self, duration=60):

        logger.info(f"Browsing comparison page for {duration} seconds...")

        start_time = time.time()

        # =====================================================
        # TIME HELPERS
        # =====================================================

        def remaining_time():
            return max(0, duration - (time.time() - start_time))

        def time_available(seconds=1):
            return remaining_time() > seconds

        # =====================================================
        # CHECK CURRENT VIEWPORT
        # =====================================================

        def is_in_viewport(element):
            try:
                return self.driver.execute_script(
                    """
                    const rect = arguments[0].getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.bottom <= window.innerHeight &&
                        rect.left >= 0 &&
                        rect.right <= window.innerWidth
                    );
                    """,
                    element,
                )
            except Exception:
                return False

        # =====================================================
        # CLEAR TEXT SELECTION
        # =====================================================

        def clear_selection():
            try:
                self.driver.execute_script(
                    """
                    const selection = window.getSelection();
                    if (selection) {
                        selection.removeAllRanges();
                    }
                    """
                )
            except Exception:
                pass

        # =====================================================
        # SELECT RANDOM VISIBLE TEXT
        # =====================================================

        def select_random_visible_text():
            if not time_available(2):
                return False

            try:
                elements = self.driver.find_elements(
                    By.XPATH,
                    """
                    //p[string-length(normalize-space(.)) >= 20]
                    |
                    //li[string-length(normalize-space(.)) >= 20]
                    |
                    //td[string-length(normalize-space(.)) >= 20]
                    |
                    //span[string-length(normalize-space(.)) >= 20]
                    |
                    //div[string-length(normalize-space(.)) >= 20]
                    """,
                )

                visible_elements = []
                for element in elements:
                    try:
                        if not element.is_displayed():
                            continue
                        if not is_in_viewport(element):
                            continue
                        text = element.text.strip()
                        if len(text) < 20:
                            continue
                        visible_elements.append(element)
                    except Exception:
                        continue

                if not visible_elements:
                    return False

                element = random.choice(visible_elements)
                text = element.text.strip()
                words = text.split()

                if len(words) < 3:
                    return False

                # ---------------------------------------------
                # LARGER TEXT SELECTION
                # ---------------------------------------------
                if len(words) <= 8:
                    min_words = 3
                    max_words = len(words)
                elif len(words) <= 15:
                    min_words = 6
                    max_words = len(words)
                elif len(words) <= 25:
                    min_words = 10
                    max_words = len(words)
                else:
                    min_words = 12
                    max_words = min(35, len(words))

                min_words = min(min_words, len(words))
                max_words = min(max_words, len(words))

                if min_words > max_words:
                    min_words = 3
                    max_words = len(words)

                word_count = random.randint(min_words, max_words)
                max_start = max(0, len(words) - word_count)
                start_word = random.randint(0, max_start)

                selected_words = words[start_word:start_word + word_count]
                selected_text = " ".join(selected_words)

                if not is_in_viewport(element):
                    return False

                result = self.driver.execute_script(
                    """
                    const element = arguments[0];
                    const selectedText = arguments[1];

                    const walker = document.createTreeWalker(
                        element, NodeFilter.SHOW_TEXT
                    );

                    const nodes = [];
                    let node;
                    while (node = walker.nextNode()) {
                        nodes.push(node);
                    }

                    let fullText = "";
                    for (const n of nodes) {
                        fullText += n.textContent;
                    }

                    const startIndex = fullText.indexOf(selectedText);
                    if (startIndex === -1) {
                        return false;
                    }

                    const endIndex = startIndex + selectedText.length;

                    let position = 0;
                    let startNode = null;
                    let endNode = null;
                    let startOffset = 0;
                    let endOffset = 0;

                    for (const n of nodes) {
                        const nodeLength = n.textContent.length;
                        const nodeStart = position;
                        const nodeEnd = position + nodeLength;

                        if (
                            startNode === null &&
                            startIndex >= nodeStart &&
                            startIndex <= nodeEnd
                        ) {
                            startNode = n;
                            startOffset = startIndex - nodeStart;
                        }

                        if (endIndex >= nodeStart && endIndex <= nodeEnd) {
                            endNode = n;
                            endOffset = endIndex - nodeStart;
                            break;
                        }

                        position += nodeLength;
                    }

                    if (!startNode || !endNode) {
                        return false;
                    }

                    const range = document.createRange();
                    range.setStart(startNode, startOffset);
                    range.setEnd(endNode, endOffset);

                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);

                    return true;
                    """,
                    element,
                    selected_text,
                )

                if result:
                    logger.info(f'Selected visible text: "{selected_text}"')
                    time.sleep(
                        min(random.uniform(1.0, 2.0), remaining_time())
                    )
                    return True

                return False

            except Exception as error:
                logger.warning(f"Text selection skipped: {error}")
                return False

        # =====================================================
        # CLICK VISIBLE SHOW MORE
        # =====================================================

        def click_visible_show_more():
            if not time_available(3):
                return False

            show_more_xpath = (
                '//a[@class="a a--md a--subtle '
                'js-truncate white-space-no-wrap link"]'
            )

            try:
                links = self.driver.find_elements(By.XPATH, show_more_xpath)
                visible_show_more = []

                for link in links:
                    try:
                        if not link.is_displayed():
                            continue
                        if not is_in_viewport(link):
                            continue
                        text = link.text.strip().lower()
                        if "show more" in text:
                            visible_show_more.append(link)
                    except Exception:
                        continue

                if not visible_show_more:
                    return False

                link = random.choice(visible_show_more)
                logger.info(f'Clicking Show more: "{link.text.strip()}"')
                link.click()

                time.sleep(
                    min(random.uniform(1.0, 1.8), remaining_time())
                )
                return True

            except Exception as error:
                logger.warning(f"Show more skipped: {error}")
                return False

        # =====================================================
        # CLICK VISIBLE SHOW LESS
        # =====================================================

        def click_visible_show_less():
            if not time_available(2):
                return False

            show_less_xpath = (
                '//a[@class="a a--md a--subtle '
                'js-truncate white-space-no-wrap link"]'
            )

            try:
                links = self.driver.find_elements(By.XPATH, show_less_xpath)
                visible_show_less = []

                for link in links:
                    try:
                        if not link.is_displayed():
                            continue
                        if not is_in_viewport(link):
                            continue
                        text = link.text.strip().lower()
                        if "show less" in text:
                            visible_show_less.append(link)
                    except Exception:
                        continue

                if not visible_show_less:
                    return False

                link = random.choice(visible_show_less)
                logger.info(f'Clicking Show less: "{link.text.strip()}"')
                link.click()

                time.sleep(
                    min(random.uniform(0.8, 1.5), remaining_time())
                )
                return True

            except Exception as error:
                logger.warning(f"Show less skipped: {error}")
                return False

        # =====================================================
        # SCROLL DOWN
        # =====================================================

        def scroll_down():
            if not time_available(1):
                return False

            try:
                page_height = self.driver.execute_script(
                    "return document.body.scrollHeight;"
                )
                viewport_height = self.driver.execute_script(
                    "return window.innerHeight;"
                )
                current_position = self.driver.execute_script(
                    "return window.pageYOffset;"
                )

                max_scroll = max(0, page_height - viewport_height)

                if current_position >= (max_scroll - 10):
                    return False

                remaining_distance = max_scroll - current_position
                distance = random.randint(600, 1000)
                distance = min(distance, remaining_distance)

                steps = random.randint(5, 8)
                step_distance = distance / steps

                for _ in range(steps):
                    if not time_available(0.3):
                        break

                    self.driver.execute_script(
                        "window.scrollBy(0, arguments[0]);",
                        step_distance,
                    )
                    time.sleep(
                        min(random.uniform(0.05, 0.12), remaining_time())
                    )

                logger.info("Scrolled page.")

                if time_available(0.5):
                    time.sleep(
                        min(random.uniform(0.5, 1.0), remaining_time())
                    )

                return True

            except Exception as error:
                logger.warning(f"Scroll skipped: {error}")
                return False

        # =====================================================
        # INITIAL TEXT SELECTION
        # =====================================================

        if time_available(2):
            select_random_visible_text()

        # =====================================================
        # MAIN LOOP
        # =====================================================

        action_counter = 1

        while time_available(2):
            current_position = self.driver.execute_script(
                "return window.pageYOffset;"
            )
            page_height = self.driver.execute_script(
                "return document.body.scrollHeight;"
            )
            viewport_height = self.driver.execute_script(
                "return window.innerHeight;"
            )
            max_scroll = max(0, page_height - viewport_height)

            # =================================================
            # BOTTOM REACHED
            # =================================================

            if current_position >= (max_scroll - 15):
                logger.info("Reached bottom of comparison page.")
                if time_available(2):
                    select_random_visible_text()
                break

            # =================================================
            # TEXT SELECTION
            # =================================================

            if random.random() < 0.85:
                if select_random_visible_text():
                    action_counter += 1

            # =================================================
            # SHOW MORE
            # =================================================

            if time_available(4) and random.random() < 0.35:
                show_more_clicked = click_visible_show_more()
                if show_more_clicked:
                    action_counter += 1

                    if time_available(2):
                        if select_random_visible_text():
                            action_counter += 1

                    if time_available(2):
                        if scroll_down():
                            action_counter += 1

                    if time_available(2):
                        if click_visible_show_less():
                            action_counter += 1

                    continue

            # =================================================
            # NORMAL SCROLL
            # =================================================

            if time_available(1):
                if scroll_down():
                    action_counter += 1

        # =====================================================
        # FINAL BOTTOM CHECK
        # =====================================================

        if time_available(0.5):
            current_position = self.driver.execute_script(
                "return window.pageYOffset;"
            )
            page_height = self.driver.execute_script(
                "return document.body.scrollHeight;"
            )
            viewport_height = self.driver.execute_script(
                "return window.innerHeight;"
            )
            max_scroll = max(0, page_height - viewport_height)

            if current_position < max_scroll:
                self.driver.execute_script(
                    "window.scrollTo(0, arguments[0]);",
                    max_scroll,
                )

        # =====================================================
        # CLEAR SELECTION
        # =====================================================

        clear_selection()

        elapsed = time.time() - start_time
        logger.info(f"Browsing completed in {round(elapsed, 2)} seconds.")
        logger.info(f"Total actions performed: {action_counter}")

    # ==================================================================
    # COMPLETE SAUCE LABS FLOW
    # ==================================================================
    def process_sauce_labs_comparison(self):

        logger.info("=" * 60)
        logger.info("Starting Sauce Labs comparison flow")
        logger.info("=" * 60)

        # =====================================================
        # STEP 1 — Open reviews page and click comparison
        # =====================================================

        self.open_g2_compare_page()
        logger.info("Comparison page opened.")

        # =====================================================
        # STEP 2 — Browse comparison page for 60 seconds
        # =====================================================

        self.browse_comparison_page(duration=60)
        logger.info("Comparison page browsing completed.")

        # =====================================================
        # STEP 3 — CLICK FOOTER LINK
        # =====================================================

        logger.info("Searching for footer link...")

        footer_xpath = '//div[@id="footer-inner"]/div[2]/ul/li[1]/a'

        try:
            footer_link = wait_for_element(
                self.driver,
                (By.XPATH, footer_xpath),
                condition="presence",
                timeout=15,
                poll=0.5,
            )

            logger.info("Footer link found.")

            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
                """,
                footer_link,
            )

            time.sleep(random.uniform(1, 2))

            logger.info("Clicking footer link...")
            footer_link.click()
            logger.info("Footer link clicked successfully.")

        except Exception as error:
            logger.error(f"Footer link click failed: {error}")
            return

        # =====================================================
        # STEP 4 — WAIT FOR NEW PAGE
        # =====================================================

        time.sleep(random.uniform(3, 5))
        logger.info("New page opened.")

        # =====================================================
        # STEP 5 — BROWSE SECOND PAGE FOR 60 SECONDS
        # =====================================================

        self.browse_comparison_page(duration=60)
        logger.info("Second page browsing completed.")

        # =====================================================
        # COMPLETE
        # =====================================================

        logger.info("Complete Sauce Labs flow finished.")

    # ==================================================================
    # RUN
    # ==================================================================
    def run_g2_comparisons(self):

        try:
            self.process_sauce_labs_comparison()

        except Exception as error:
            logger.error(f"ERROR OCCURRED: {error}")

        finally:
            logger.info("Closing browser...")
            self.driver.quit()
            logger.info("Browser closed.")


if __name__ == "__main__":
    # Standalone execution: launch an undetected Chrome browser.
    # For integration with your existing BrowserManager, instantiate
    # G2Comparison(driver, human_simulator) from your application instead.
    options = uc.ChromeOptions()
    
    # options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, version_main=152)

    try:
        G2Comparison(driver, human_simulator=None).run_g2_comparisons()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass