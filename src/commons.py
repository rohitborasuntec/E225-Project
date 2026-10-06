import re
import time
from faker import Faker
from datetime import datetime, date
from random import randint
import random,re
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

# FIX: import the configured logger INSTANCE, not the module.
from src.logging import logger

start_time = time.time()
duration = 60


def check_for_block(driver):
    acc_den_xpath = '//*[contains(.,"Access is temporarily restricted")]'
    if driver.find_elements(By.XPATH, acc_den_xpath):
        # breakpoint()
        return True
    return False



# def check_for_block(driver):
#     """
#     Return True if the current page looks like a G2 / Cloudflare block page.

#     Adjust the selectors / title checks to your own environment if needed.
#     """
#     try:
#         title = (driver.title or "").lower()
#         source = (driver.page_source or "").lower()
#     except Exception:
#         return False

#     block_markers = (
#         "access denied",
#         "are you a human",
#         "attention required",
#         "just a moment",
#         "checking your browser",
#         "cloudflare",
#         "captcha",
#         "verify you are human",
#     )
#     if any(marker in title for marker in block_markers):
#         return True
#     if "access denied" in source and "g2.com" in source:
#         return True
#     return False

def wait_for_element(driver, locator, timeout=10, condition="visible", poll=0.5):
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
    if option == 'name':
        return fake.name()
    if option == 'country':
        return f"current gdp of {fake.country()}?"
    if option == 'movie':
        return f"movies released in {year}"
    if option == 'music':
        return f"top songs of {year}"
    if option == 'sports':
        sports = ["cricket", "football", ""]
        return f"{random.choice(sports)} live score"
    if option == 'technology':
        return f"top techonlogies build in {year}"
    if option == 'News':
        return f"current news of {fake.city()}"
    return option


def save_html(html_text, file_name="Test"):
    folder_path = Path("HTML")
    folder_path.mkdir(parents=True, exist_ok=True)

    stem = Path(file_name).stem
    # Sanitize: replace Windows-illegal chars, strip trailing dots/spaces
    stem = re.sub(r'[<>:"/\\|?*]', '_', stem).rstrip('. ')
    if not stem:
        stem = "output"
    # Optional: cap length to stay under Windows MAX_PATH
    stem = stem[:150]

    today = date.today().strftime("%Y-%m-%d")
    final_name = f"{stem}_{today}.html"
    file_path = folder_path / final_name
    file_path.write_text(html_text, encoding="utf-8")
    logger.info(f"--------HTML SAVED for {file_path}----------")

# ---------------- time helpers ---------------- #

def remaining_time():
    return max(0, duration - (time.time() - start_time))


def time_available(seconds=1):
    return remaining_time() > seconds


# ---------------- visible text helpers ---------------- #

def is_in_viewport(driver, element):
    try:
        return driver.execute_script(
            """
            const rect = arguments[0].getBoundingClientRect();
            return (rect.top >= 0 && rect.bottom <= window.innerHeight
                 && rect.left >= 0 && rect.right <= window.innerWidth);
            """,
            element,
        )
    except Exception:
        return False


def select_random_visible_text(driver, duration_sec, start_ts):
    """Selects a random portion of visible text from the current viewport."""
    def _remaining():
        return max(0, duration_sec - (time.time() - start_ts))

    def _time_available(seconds=1):
        return _remaining() > seconds

    if not _time_available(2):
        return False

    try:
        elements = driver.find_elements(
            By.XPATH,
            """
            //p[string-length(normalize-space(.)) >= 20]
            | //li[string-length(normalize-space(.)) >= 20]
            | //td[string-length(normalize-space(.)) >= 20]
            | //span[string-length(normalize-space(.)) >= 20]
            | //div[string-length(normalize-space(.)) >= 20]
            """,
        )
        visible_elements = []
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                if not is_in_viewport(driver, element):
                    continue
                if len(element.text.strip()) < 20:
                    continue
                visible_elements.append(element)
            except Exception:
                continue

        if not visible_elements:
            return False

        element = random.choice(visible_elements)
        words = element.text.strip().split()
        if len(words) < 3:
            return False

        if len(words) <= 8:
            min_words, max_words = 3, len(words)
        elif len(words) <= 15:
            min_words, max_words = 6, len(words)
        elif len(words) <= 25:
            min_words, max_words = 10, len(words)
        else:
            min_words, max_words = 12, min(35, len(words))

        min_words = min(min_words, len(words))
        max_words = min(max_words, len(words))
        if min_words > max_words:
            min_words, max_words = 3, len(words)

        word_count = random.randint(min_words, max_words)
        start_word = random.randint(0, max(0, len(words) - word_count))
        selected_text = " ".join(words[start_word:start_word + word_count])

        if not is_in_viewport(driver, element):
            return False

        result = driver.execute_script(
            """
            const element = arguments[0];
            const selectedText = arguments[1];
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const nodes = [];
            let node;
            while (node = walker.nextNode()) nodes.push(node);
            let fullText = "";
            for (const n of nodes) fullText += n.textContent;
            const startIndex = fullText.indexOf(selectedText);
            if (startIndex === -1) return false;
            const endIndex = startIndex + selectedText.length;
            let position = 0, startNode = null, endNode = null;
            let startOffset = 0, endOffset = 0;
            for (const n of nodes) {
                const nodeLength = n.textContent.length;
                const nodeStart = position, nodeEnd = position + nodeLength;
                if (startNode === null && startIndex >= nodeStart && startIndex <= nodeEnd) {
                    startNode = n; startOffset = startIndex - nodeStart;
                }
                if (endIndex >= nodeStart && endIndex <= nodeEnd) {
                    endNode = n; endOffset = endIndex - nodeStart; break;
                }
                position += nodeLength;
            }
            if (!startNode || !endNode) return false;
            const range = document.createRange();
            range.setStart(startNode, startOffset);
            range.setEnd(endNode, endOffset);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            return true;
            """,
            element, selected_text,
        )
        if result:
            logger.info(f'Selected visible text: "{selected_text}"')
            time.sleep(min(random.uniform(1.0, 2.0), _remaining()))
            return True
        return False
    except Exception as error:
        logger.warning(f"Text selection skipped: {error}")
        return False