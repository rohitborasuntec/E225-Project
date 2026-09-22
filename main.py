import random,time
from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
# from src.automation.G2_saucelabs import G2
from src.commons import *
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
)
from src.vpn.vpn_automation import ExpressVPN
from src.logging import logger
from src.automation.google_work import GoogleSearch
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from src.automation.G2_comparison import G2Comparison
from src.automation.G2_page import G2Page

class G2Automation:

    def __init__(self,driver,human_simulator,gs):
        self.driver = driver
        self.human_simulator = human_simulator
        self.gs = gs

    def random_words(self):
        CATEGORIES = ['word', 'name', 'country', 'movie', 'music',
                    'sports', 'technology', 'News']

        logger.info("Searching for 2 Random Searches")
        keywords = random.choices(CATEGORIES, k=2)

        for keyword in keywords:
            query = get_random_word_or_sentence_faker(keyword).lower()

            wait_for_element(driver, (By.XPATH, '//*[@aria-label="Google"]'), condition="visible")
            self.human_simulator.input_search_query(query)
            wait_for_element(driver, (By.XPATH, '//a[@aria-label="Go to Google Home"]'), condition="visible")
            save_html(html_text=self.driver.page_source,file_name=query)
            clicked = False

            for attempt in range(10):
                try:
                    elem_xpath = gs.get_elem_xpaths()
                    logger.info(f"Attempt {attempt+1}: Elem Xpath found: {elem_xpath}")
                    try:
                        element = driver.find_element(By.XPATH, elem_xpath)
                        self.human_simulator.move_to_element_like_human(element)
                        self.human_simulator.mouse_click_after_hover(driver.find_element(By.XPATH,elem_xpath))
                        clicked = True
                        break
                    except (NoSuchElementException, ElementClickInterceptedException) as e:
                        logger.warning(f"{elem_xpath} not found: {e}")
                        self.human_simulator.scroll_page(total_scroll=5, step_delay=0.1, direction="down")
                except Exception as e:
                    logger.error(f"random_words failed for keyword '{keyword}': {e}")

            if not clicked:
                raise RuntimeError(f"Could not find/click any element after 10 attempts for query '{query}'")


    def test_keywords_search(self):
        
        test_keywords = ["browser tests", "software testing", "automation tests", "ai in test cases", "app android", "android on browser"]

        keywords = random.choices(test_keywords,k=2)
        for keyword in keywords:
            self.human_simulator.input_search_query(keyword)
            locator = (By.XPATH , '//a[@aria-label="Go to Google Home"]')
            wait_for_element(driver,locator,condition="visible")

            clicked = False
            for i in range(10):
                elem_xpath = gs.get_elem_xpaths()
                logger.info(f"Elem Xpath found: {elem_xpath}")
                try:
                    element = driver.find_element(By.XPATH, elem_xpath)
                    self.human_simulator.move_to_element_like_human(element)
                    self.human_simulator.mouse_click_after_hover(driver.find_element(By.XPATH,elem_xpath))
                    clicked = True
                    break
                except (NoSuchElementException, ElementClickInterceptedException) as e:
                    logger.warning(f"{elem_xpath} not found: {e}")
                    self.human_simulator.scroll_page(total_scroll=5, step_delay=0.1, direction="down")

            if not clicked:
                raise RuntimeError("Could not find/click any element after 10 attempts")

    def run_g2(self,product,comparing_product):
        self.random_words()
        self.test_keywords_search()
        
        G2Page(self.driver,self.human_simulator,product,comparing_product).run_g2_saucelabs()
    
        G2Comparison(self.driver,self.human_simulator,comparing_product).run_g2_comparisons()

if __name__ == "__main__":

    logger.info("Script Has Been Started..............")

    products = {"SauceLabs":["Ranorex" ,"Testcomplete"] , "BrowserStack":["Testrail" , "Perfecto"]}

    # vpn = ExpressVPN()
    # locations = vpn.get_vpn_locations()

    for product,comparing_products in products.items():
        # vpn.connect(random.choice(locations))
        manager = Browser(headless=False)
        driver = manager.launch("chrome")

        human_simulator = HumanSimulator(driver)
    
        gs = GoogleSearch(driver)
        gs.get_google()

        for comparing_product in comparing_products:
            g2_project = G2Automation(driver,human_simulator,gs)
            g2_project.run_g2(product,comparing_product)

        logger.info(f"Comparison Process Completed for {product} and {comparing_product}")   
        driver.quit()
        # vpn.disconnect(random.choice(locations))
        # time.sleep(5)

    
    