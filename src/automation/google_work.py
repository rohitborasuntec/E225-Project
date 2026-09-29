import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from urllib.parse import quote_plus

from selenium.webdriver.common.by import By

from src.logging import logger
from src.commons import wait_for_element, save_html, get_random_word_or_sentence_faker
from src.automation.xpath_pools import GOOGLE_RESULTS_POOL


class GoogleSearch:

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    def check_for_bot(self):
        captcha = '//*[contains(.,"Sometimes you may be asked to solve the CAPTCHA")]'
        if self.driver.find_elements(By.XPATH, captcha):
            logger.warning("Google CAPTCHA detected — waiting for manual solve.")
            input("Robot: after solving the CAPTCHA press ENTER to continue...")

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
                
                try:
                    self.human_simulator.input_search_query(query,suggestion=sug)
                except Exception:
                    logger.info("Google page may not have opened correctly, retrying.")
                    self.get_google(query=keyword)

                wait_for_element(
                    self.driver,
                    (By.XPATH, '//a[@aria-label="Go to Google Home"]'),
                    condition="visible",
                )
                self.check_for_bot()

                xpath_trans = self.change_in_eng()
                if xpath_trans:
                    self.human_simulator.mouse_click_after_hover(
                        self.driver.find_element(By.XPATH, xpath_trans)
                    )
                    logger.info(f"Translation done for {keyword}")

                refuse_xpath = "//*[contains(text(),'Reject all')]"
                
                if self.driver.find_elements(By.XPATH,refuse_xpath):
                    self.human_simulator.mouse_click_after_hover(self.driver.find_element(By.XPATH, xpath_trans))
                    logger.info(f"Reject All done")

                
                save_html(html_text=self.driver.page_source, file_name=query)

                clicked = False
                for attempt in range(10):
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
                            logger.warning(f"{elem_xpath} not found: {e}")
                            self.human_simulator.scroll_page(
                                total_scroll=5, step_delay=0.1, direction="down"
                            )
                    except Exception as e:
                        logger.error(f"random_words failed for keyword '{keyword}': {e}")

                if not clicked:
                    logger.error(
                        f"Could not find/click any element after 10 attempts "
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
        if self.driver.find_elements(By.XPATH, trans_xpath):
            return trans_xpath
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