import random
from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
from src.automation.g2_saucelabs import G2
from src.commons import get_random_word_or_sentence_faker,wait_for_element
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
)
import traceback
from src.logging import logger
from src.automation.google_work import GoogleSearch
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def random_words(driver, gs, human_simulator):
    CATEGORIES = ['word', 'name', 'country', 'movie', 'music',
                  'sports', 'technology', 'News']

    logger.info(f"{'-'*10} Searching for 2 Random Searches {'-'*10}")
    keywords = random.choices(CATEGORIES, k=2)

    for keyword in keywords:
        query = get_random_word_or_sentence_faker(keyword).lower()

        wait_for_element(driver, (By.XPATH, '//*[@aria-label="Google"]'), condition="visible")
        human_simulator.input_search_query(query)
        wait_for_element(driver, (By.XPATH, '//a[@aria-label="Go to Google Home"]'), condition="visible")

        clicked = False

        for attempt in range(10):
            try:
                elem_xpath = gs.get_elem_xpaths()
                logger.info(f"{'-'*10} Attempt {attempt+1}: Elem Xpath found: {elem_xpath} {'-'*10}")
                try:
                    element = driver.find_element(By.XPATH, elem_xpath)
                    human_simulator.move_to_element_like_human(element)
                    human_simulator.mouse_click_after_hover(driver.find_element(By.XPATH,elem_xpath))
                    clicked = True
                    break
                except (NoSuchElementException, ElementClickInterceptedException) as e:
                    logger.warning(f"{elem_xpath} not found: {e}")
                    human_simulator.scroll_page(total_scroll=5, step_delay=0.1, direction="down")
            except Exception as e:
                logger.error(f"random_words failed for keyword '{keyword}': {e}")

        if not clicked:
            raise RuntimeError(f"Could not find/click any element after 10 attempts for query '{query}'")


def test_keywords_search():
    # try:
    test_keywords = ["browser tests", "software testing", "automation tests", "ai in test cases", "app android", "android on browser"]

    keywords = random.choices(test_keywords,k=2)
    for keyword in keywords:
        human_simulator.input_search_query(keyword)
        locator = (By.XPATH , '//a[@aria-label="Go to Google Home"]')
        wait_for_element(driver,locator,condition="visible")

        clicked = False
        for i in range(10):
            elem_xpath = gs.get_elem_xpaths()
            logger.info(f"{'-'*10} Elem Xpath found: {elem_xpath} {'-'*10}")
            try:
                # human_simulator.move_to_element_like_human(
                #     driver.find_element(By.XPATH, elem_xpath)
                # )
                # human_simulator.mouse_click(elem_xpath)
                element = driver.find_element(By.XPATH, elem_xpath)
                human_simulator.move_to_element_like_human(element)
                human_simulator.mouse_click_after_hover(driver.find_element(By.XPATH,elem_xpath))
                clicked = True
                break
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                logger.warning(f"{elem_xpath} not found: {e}")
                human_simulator.scroll_page(total_scroll=5, step_delay=0.1, direction="down")

        if not clicked:
            raise RuntimeError("Could not find/click any element after 5 attempts")
    # except:
    #     breakpoint()


if __name__ == "__main__":

    logger.info("Script Has Been Started..............")
    manager = Browser(headless=False)
    driver = manager.launch("chrome")

    gs = GoogleSearch(driver)
    human_simulator = HumanSimulator(driver)
    gs.get_google()
    # g2 = G2(driver,human_simulator)

    random_words(driver, gs, human_simulator)
    test_keywords_search()

    logger.info(f"{"-"*10} Process Completed {"-"*10}")
    
    driver.quit()