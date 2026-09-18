from faker import Faker
from datetime import datetime
from random import randint
import src.logging.logger as logger
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
