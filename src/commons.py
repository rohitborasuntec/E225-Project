import time

from faker import Faker
from datetime import datetime
from random import randint
import src.logging.logger as logger
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
import random

def wait_for_element(driver, locator, timeout=10, condition="visible", poll=0.5):
    """
    Wait for an element and return it.

    locator:   tuple, e.g. (By.XPATH, "//a[contains(@href,'example')]")
    timeout:   seconds to wait
    condition: "presence" | "visible" | "clickable"
    poll:      polling frequency in seconds

    Returns the WebElement, or None if it times out.
    """
    conditions = {
        "presence":  EC.presence_of_element_located,
        "visible":   EC.visibility_of_element_located,
        "clickable": EC.element_to_be_clickable,
    }
    if condition not in conditions:
        raise ValueError(f"Unknown condition: {condition}")

    wait = WebDriverWait(driver, timeout, poll_frequency=poll)
    try:
        return wait.until(conditions[condition](locator))
    except TimeoutException:
        return None

def get_random_word_or_sentence_faker(option):
    fake = Faker()
    curr_yr = datetime.now().year
    year = randint(1950, curr_yr)
    if option == 'word':
        return f"{fake.word()} meaning"
    elif option == 'name':
        return fake.name() 
    elif option == 'country':
        return f"current gdp of {fake.country()}?"
    elif option == 'movie':
        return f"movies released in {year}"
    elif option == 'music':
        return f"top songs of {year}"
    elif option == 'sports':
        sports = ["cricket","football",""]
        return f"{random.choice(sports)} live score"
    elif option == 'technology':
        return f"top techonlogies build in {year}"
    elif option == 'News':
        return f"current news of {fake.city()}"
    else:
        return "Invalid option. Use 'word' or 'sentence'"

def save_html(html_text,file_path):

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    logger.info(f"--------HTML SAVED for {file_path}----------")


# =====================================================
# TIME HELPER FUNCTIONS
# =====================================================
start_time = time.time()
duration=60
def remaining_time():
    return max(0, duration - (time.time() - start_time))

def time_available(seconds=1):
    return remaining_time() > seconds



# =====================================================
# Visible text FUNCTIONS
# =====================================================

def is_in_viewport(driver, element):
    try:
        return driver.execute_script(
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


def select_random_visible_text(driver, duration, start_time):
    """
    Selects a random portion of visible text from the current viewport.

    - Finds text elements containing at least 20 characters.
    - Only considers visible/in-viewport elements.
    - Randomly selects 3-35 words depending on text length.
    - Uses JavaScript Range API to highlight the selected text.
    """

    def remaining_time():
        return max(0, duration - (time.time() - start_time))

    def time_available(seconds=1):
        return remaining_time() > seconds

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
            """,
        )

        visible_elements = []

        for element in elements:
            try:
                if not element.is_displayed():
                    continue

                if not is_in_viewport(driver, element):
                    continue

                text = element.text.strip()

                if len(text) < 20:
                    continue

                visible_elements.append(element)

            except Exception:
                continue

        if not visible_elements:
            return False

        # Random visible text element
        element = random.choice(visible_elements)

        text = element.text.strip()
        words = text.split()

        if len(words) < 3:
            return False

        # =====================================================
        # LARGER TEXT SELECTION
        # =====================================================

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
            start_word:start_word + word_count
        ]

        selected_text = " ".join(selected_words)

        # Make sure element is still visible
        if not is_in_viewport(driver, element):
            return False

        # =====================================================
        # SELECT TEXT USING JAVASCRIPT RANGE
        # =====================================================

        result = driver.execute_script(
            """
            const element = arguments[0];
            const selectedText = arguments[1];

            const walker = document.createTreeWalker(
                element,
                NodeFilter.SHOW_TEXT
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

            const endIndex =
                startIndex + selectedText.length;

            let position = 0;

            let startNode = null;
            let endNode = null;

            let startOffset = 0;
            let endOffset = 0;

            for (const n of nodes) {

                const nodeLength =
                    n.textContent.length;

                const nodeStart = position;
                const nodeEnd =
                    position + nodeLength;

                if (
                    startNode === null &&
                    startIndex >= nodeStart &&
                    startIndex <= nodeEnd
                ) {
                    startNode = n;

                    startOffset =
                        startIndex - nodeStart;
                }

                if (
                    endIndex >= nodeStart &&
                    endIndex <= nodeEnd
                ) {
                    endNode = n;

                    endOffset =
                        endIndex - nodeStart;

                    break;
                }

                position += nodeLength;
            }

            if (!startNode || !endNode) {
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
            selected_text,
        )

        if result:

            logger.info(
                f'Selected visible text: "{selected_text}"'
            )

            # Human-like pause after selection
            time.sleep(
                min(
                    random.uniform(1.0, 2.0),
                    remaining_time()
                )
            )

            return True

        return False

    except Exception as error:

        logger.warning(
            f"Text selection skipped: {error}"
        )

        return False