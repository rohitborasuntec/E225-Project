import random
import time

import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================================================
# URL
# =========================================================

G2_REVIEWS_URL = (
    "https://www.g2.com/products/sauce-labs/reviews"
)


# =========================================================
# CREATE UNDETECTED CHROME DRIVER
# =========================================================

def create_driver():

    options = uc.ChromeOptions()

    options.add_argument("--start-maximized")

    driver = uc.Chrome(
        options=options,
        version_main=152,
        use_subprocess=True
    )

    driver.maximize_window()

    return driver


# =========================================================
# OPEN SAUCE LABS REVIEWS PAGE
# =========================================================

def open_g2_compare_page(driver):

    print("\nOpening Sauce Labs reviews page...")

    driver.get(G2_REVIEWS_URL)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located(
            (By.TAG_NAME, "body")
        )
    )

    time.sleep(
        random.uniform(3, 5)
    )

    print(
        "Sauce Labs reviews page opened."
    )

    # =====================================================
    # HANDLE COOKIE CONSENT BANNER
    # =====================================================

    try:

        cookie_banner = driver.find_elements(
            By.XPATH,
            '//div[@role="dialog" and @aria-label="Cookie Consent Banner"]'
        )

        if cookie_banner:

            print(
                "Cookie Consent Banner found."
            )

            cookie_buttons = cookie_banner[0].find_elements(
                By.XPATH,
                ".//button"
            )

            for button in cookie_buttons:

                try:

                    if button.is_displayed():

                        print(
                            f"Cookie button found: "
                            f"{button.text.strip()}"
                        )

                        button.click()

                        time.sleep(1)

                        print(
                            "Cookie Consent handled."
                        )

                        break

                except Exception:
                    continue

    except Exception as error:

        print(
            f"Cookie Consent handling skipped: "
            f"{error}"
        )

    # =====================================================
    # COMPARISON BLOCK
    # =====================================================

    compare_xpath = (
        '(//div[@class="elv-flex elv-items-center"])[69]'
    )

    print(
        "\nSearching for comparison block..."
    )

    start_time = time.time()

    while time.time() - start_time < 30:

        try:

            compare_element = driver.find_element(
                By.XPATH,
                compare_xpath
            )

            if compare_element.is_displayed():

                print(
                    "Comparison block found."
                )

                break

        except Exception:
            pass

        driver.execute_script(
            """
            window.scrollBy(
                0,
                arguments[0]
            );
            """,
            random.randint(500, 800)
        )

        time.sleep(
            random.uniform(0.5, 1)
        )

    else:

        raise Exception(
            "Comparison block was not found."
        )

    # =====================================================
    # CLICK COMPARISON BUTTON
    # =====================================================

    compare_element = WebDriverWait(
        driver,
        10
    ).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                compare_xpath
            )
        )
    )

    print(
        "Clicking comparison button..."
    )

    try:

        compare_element.click()

    except Exception:

        print(
            "Normal click intercepted."
        )

        try:

            cookie_banner = driver.find_elements(
                By.XPATH,
                '//div[@role="dialog" and @aria-label="Cookie Consent Banner"]'
            )

            if cookie_banner:

                cookie_buttons = cookie_banner[0].find_elements(
                    By.XPATH,
                    ".//button"
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

        compare_element = WebDriverWait(
            driver,
            10
        ).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    compare_xpath
                )
            )
        )

        compare_element.click()

    print(
        "Comparison button clicked."
    )

    time.sleep(
        random.uniform(3, 5)
    )


# =========================================================
# BROWSE COMPARISON PAGE
# =========================================================

def browse_comparison_page(driver, duration=60):

    print(
        f"\nBrowsing comparison page for "
        f"{duration} seconds..."
    )

    start_time = time.time()

    # =====================================================
    # TIME HELPERS
    # =====================================================

    def remaining_time():

        return max(
            0,
            duration - (
                time.time() - start_time
            )
        )

    def time_available(seconds=1):

        return remaining_time() > seconds

    # =====================================================
    # CHECK CURRENT VIEWPORT
    # =====================================================

    def is_in_viewport(element):

        try:

            return driver.execute_script(
                """
                const rect =
                    arguments[0].getBoundingClientRect();

                return (
                    rect.top >= 0 &&
                    rect.bottom <= window.innerHeight &&
                    rect.left >= 0 &&
                    rect.right <= window.innerWidth
                );
                """,
                element
            )

        except Exception:

            return False

    # =====================================================
    # CLEAR TEXT SELECTION
    # =====================================================

    def clear_selection():

        try:

            driver.execute_script(
                """
                const selection =
                    window.getSelection();

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

            elements = driver.find_elements(
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
                """
            )

            visible_elements = []

            for element in elements:

                try:

                    if not element.is_displayed():
                        continue

                    # Text selection only from current viewport.
                    if not is_in_viewport(element):
                        continue

                    text = element.text.strip()

                    if len(text) < 20:
                        continue

                    visible_elements.append(
                        element
                    )

                except Exception:

                    continue

            if not visible_elements:

                return False

            element = random.choice(
                visible_elements
            )

            text = element.text.strip()

            words = text.split()

            if len(words) < 3:

                return False

            # =================================================
            # LARGER TEXT SELECTION
            # Approx. 2-3 lines / reading-like selection
            # =================================================

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
                max_words = min(
                    35,
                    len(words)
                )

            min_words = min(
                min_words,
                len(words)
            )

            max_words = min(
                max_words,
                len(words)
            )

            if min_words > max_words:

                min_words = 3
                max_words = len(words)

            word_count = random.randint(
                min_words,
                max_words
            )

            max_start = max(
                0,
                len(words) - word_count
            )

            start_word = random.randint(
                0,
                max_start
            )

            selected_words = words[
                start_word:
                start_word + word_count
            ]

            selected_text = " ".join(
                selected_words
            )

            # =================================================
            # VERIFY STILL VISIBLE
            # =================================================

            if not is_in_viewport(element):

                return False

            # =================================================
            # SELECT TEXT WITHOUT SCROLLING
            # =================================================

            result = driver.execute_script(
                """
                const element = arguments[0];
                const selectedText = arguments[1];

                const walker =
                    document.createTreeWalker(
                        element,
                        NodeFilter.SHOW_TEXT
                    );

                const nodes = [];

                let node;

                while (
                    node = walker.nextNode()
                ) {

                    nodes.push(node);
                }

                let fullText = "";

                for (const n of nodes) {

                    fullText += n.textContent;
                }

                const startIndex =
                    fullText.indexOf(
                        selectedText
                    );

                if (startIndex === -1) {

                    return false;
                }

                const endIndex =
                    startIndex +
                    selectedText.length;

                let position = 0;

                let startNode = null;
                let endNode = null;

                let startOffset = 0;
                let endOffset = 0;

                for (const n of nodes) {

                    const nodeLength =
                        n.textContent.length;

                    const nodeStart =
                        position;

                    const nodeEnd =
                        position +
                        nodeLength;

                    if (
                        startNode === null &&
                        startIndex >= nodeStart &&
                        startIndex <= nodeEnd
                    ) {

                        startNode = n;

                        startOffset =
                            startIndex -
                            nodeStart;
                    }

                    if (
                        endIndex >= nodeStart &&
                        endIndex <= nodeEnd
                    ) {

                        endNode = n;

                        endOffset =
                            endIndex -
                            nodeStart;

                        break;
                    }

                    position += nodeLength;
                }

                if (
                    !startNode ||
                    !endNode
                ) {

                    return false;
                }

                const range =
                    document.createRange();

                range.setStart(
                    startNode,
                    startOffset
                );

                range.setEnd(
                    endNode,
                    endOffset
                );

                const selection =
                    window.getSelection();

                selection.removeAllRanges();

                selection.addRange(range);

                return true;
                """,
                element,
                selected_text
            )

            if result:

                print(
                    f'Selected visible text: '
                    f'"{selected_text}"'
                )

                time.sleep(
                    min(
                        random.uniform(
                            1.0,
                            2.0
                        ),
                        remaining_time()
                    )
                )

                return True

            return False

        except Exception as error:

            print(
                f"Text selection skipped: "
                f"{error}"
            )

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

            links = driver.find_elements(
                By.XPATH,
                show_more_xpath
            )

            visible_show_more = []

            for link in links:

                try:

                    if not link.is_displayed():
                        continue

                    if not is_in_viewport(link):
                        continue

                    text = link.text.strip().lower()

                    if "show more" in text:

                        visible_show_more.append(
                            link
                        )

                except Exception:

                    continue

            if not visible_show_more:

                return False

            # Random visible Show more link
            link = random.choice(
                visible_show_more
            )

            print(
                f'Clicking Show more: '
                f'"{link.text.strip()}"'
            )

            link.click()

            time.sleep(
                min(
                    random.uniform(
                        1.0,
                        1.8
                    ),
                    remaining_time()
                )
            )

            return True

        except Exception as error:

            print(
                f"Show more skipped: "
                f"{error}"
            )

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

            links = driver.find_elements(
                By.XPATH,
                show_less_xpath
            )

            visible_show_less = []

            for link in links:

                try:

                    if not link.is_displayed():
                        continue

                    if not is_in_viewport(link):
                        continue

                    text = link.text.strip().lower()

                    if "show less" in text:

                        visible_show_less.append(
                            link
                        )

                except Exception:

                    continue

            if not visible_show_less:

                return False

            link = random.choice(
                visible_show_less
            )

            print(
                f'Clicking Show less: '
                f'"{link.text.strip()}"'
            )

            link.click()

            time.sleep(
                min(
                    random.uniform(
                        0.8,
                        1.5
                    ),
                    remaining_time()
                )
            )

            return True

        except Exception as error:

            print(
                f"Show less skipped: "
                f"{error}"
            )

            return False

    # =====================================================
    # SCROLL DOWN
    # =====================================================

    def scroll_down():

        if not time_available(1):

            return False

        try:

            page_height = driver.execute_script(
                "return document.body.scrollHeight;"
            )

            viewport_height = driver.execute_script(
                "return window.innerHeight;"
            )

            current_position = driver.execute_script(
                "return window.pageYOffset;"
            )

            max_scroll = max(
                0,
                page_height -
                viewport_height
            )

            if current_position >= (
                max_scroll - 10
            ):

                return False

            remaining_distance = (
                max_scroll -
                current_position
            )

            distance = random.randint(
                600,
                1000
            )

            distance = min(
                distance,
                remaining_distance
            )

            steps = random.randint(
                5,
                8
            )

            step_distance = (
                distance / steps
            )

            for _ in range(steps):

                if not time_available(0.3):

                    break

                driver.execute_script(
                    """
                    window.scrollBy(
                        0,
                        arguments[0]
                    );
                    """,
                    step_distance
                )

                time.sleep(
                    min(
                        random.uniform(
                            0.05,
                            0.12
                        ),
                        remaining_time()
                    )
                )

            print(
                "Scrolled page."
            )

            if time_available(0.5):

                time.sleep(
                    min(
                        random.uniform(
                            0.5,
                            1.0
                        ),
                        remaining_time()
                    )
                )

            return True

        except Exception as error:

            print(
                f"Scroll skipped: "
                f"{error}"
            )

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

        current_position = driver.execute_script(
            "return window.pageYOffset;"
        )

        page_height = driver.execute_script(
            "return document.body.scrollHeight;"
        )

        viewport_height = driver.execute_script(
            "return window.innerHeight;"
        )

        max_scroll = max(
            0,
            page_height -
            viewport_height
        )

        # =================================================
        # BOTTOM REACHED
        # =================================================

        if current_position >= (
            max_scroll - 15
        ):

            print(
                "Reached bottom of comparison page."
            )

            if time_available(2):

                select_random_visible_text()

            break

        # =================================================
        # TEXT SELECTION
        # =================================================

        # High probability of selecting text
        if random.random() < 0.85:

            if select_random_visible_text():

                action_counter += 1

        # =================================================
        # SHOW MORE
        # =================================================

        if (
            time_available(4)
            and
            random.random() < 0.35
        ):

            show_more_clicked = (
                click_visible_show_more()
            )

            if show_more_clicked:

                action_counter += 1

                # -------------------------------------------------
                # Select text after Show more expansion
                # -------------------------------------------------

                if time_available(2):

                    if select_random_visible_text():

                        action_counter += 1

                # -------------------------------------------------
                # Scroll expanded content
                # -------------------------------------------------

                if time_available(2):

                    if scroll_down():

                        action_counter += 1

                # -------------------------------------------------
                # Click Show less
                # -------------------------------------------------

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

        current_position = driver.execute_script(
            "return window.pageYOffset;"
        )

        page_height = driver.execute_script(
            "return document.body.scrollHeight;"
        )

        viewport_height = driver.execute_script(
            "return window.innerHeight;"
        )

        max_scroll = max(
            0,
            page_height -
            viewport_height
        )

        if current_position < max_scroll:

            driver.execute_script(
                """
                window.scrollTo(
                    0,
                    arguments[0]
                );
                """,
                max_scroll
            )

    # =====================================================
    # CLEAR SELECTION
    # =====================================================

    clear_selection()

    elapsed = (
        time.time() -
        start_time
    )

    print(
        f"\nBrowsing completed in "
        f"{round(elapsed, 2)} seconds."
    )

    print(
        f"Total actions performed: "
        f"{action_counter}"
    )


# =========================================================
# COMPLETE SAUCE LABS FLOW
# =========================================================

def process_sauce_labs_comparison(driver):

    print("\n")
    print("=" * 60)
    print("Starting Sauce Labs comparison flow")
    print("=" * 60)

    # =====================================================
    # STEP 1
    # Open reviews page and click comparison
    # =====================================================

    open_g2_compare_page(driver)

    print(
        "\nComparison page opened."
    )

    # =====================================================
    # STEP 2
    # Browse comparison page for 60 seconds
    # =====================================================

    browse_comparison_page(
        driver,
        duration=60
    )

    print(
        "\nComparison page browsing completed."
    )

    # =====================================================
    # STEP 3
    # CLICK FOOTER LINK
    # =====================================================

    print(
        "\nSearching for footer link..."
    )

    footer_xpath = (
        '//div[@id="footer-inner"]/div[2]/ul/li[1]/a'
    )

    try:

        footer_link = WebDriverWait(
            driver,
            15
        ).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    footer_xpath
                )
            )
        )

        print(
            "Footer link found."
        )

        # Scroll to footer link
        driver.execute_script(
            """
            arguments[0].scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
            """,
            footer_link
        )

        time.sleep(
            random.uniform(1, 2)
        )

        # -------------------------------------------------
        # Click footer link
        # -------------------------------------------------

        print(
            "Clicking footer link..."
        )

        footer_link.click()

        print(
            "Footer link clicked successfully."
        )

    except Exception as error:

        print(
            f"Footer link click failed: "
            f"{error}"
        )

        return

    # =====================================================
    # STEP 4
    # WAIT FOR NEW PAGE
    # =====================================================

    time.sleep(
        random.uniform(3, 5)
    )

    print(
        "\nNew page opened."
    )

    # =====================================================
    # STEP 5
    # BROWSE SECOND PAGE FOR 60 SECONDS
    # =====================================================

    browse_comparison_page(
        driver,
        duration=60
    )

    print(
        "\nSecond page browsing completed."
    )

    # =====================================================
    # COMPLETE
    # =====================================================

    print(
        "\nComplete Sauce Labs flow finished."
    )


# =========================================================
# RUN
# =========================================================

def run_g2_comparisons():

    driver = create_driver()

    try:

        process_sauce_labs_comparison(
            driver
        )

    except Exception as error:

        print(
            "\nERROR OCCURRED:"
        )

        print(
            f"Error details: {error}"
        )

    finally:

        print(
            "\nClosing browser..."
        )

        driver.quit()

        print(
            "Browser closed."
        )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    run_g2_comparisons()