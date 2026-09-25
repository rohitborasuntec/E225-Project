import random
import traceback
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
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
from selenium.common.exceptions import TimeoutException
from src.automation.G2_comparison import G2Comparison
from src.automation.G2_page import G2Page
from src.excel import Excel

class G2Automation:

    def __init__(self, driver, human_simulator, gs):
        self.driver = driver
        self.human_simulator = human_simulator
        self.gs = gs
        self.items = {}
        self.excel = Excel()


    def set_data(self, product, comparing_product,browser,location,status):
        self.items["Link"] = ""
        self.items["First product"] = product
        self.items["Second product"] = comparing_product
        self.items["Browser Name"] = browser
        self.items["Country Name"] = location
        self.items["Version Number"] = ""
        self.items["Status"] = status


    def run_g2(self, product, comparing_product,browser,location):
        
        try:
            # self.random_words()

            categories = ['word', 'name', 'country', 'movie', 'music','sports', 'technology', 'News']

            test_keywords = [
                        "browser tests", "software testing", "automation tests",
                        "ai in test cases", "app android", "android on browser",
                    ]

            categories_queries = random.choices(categories, k=2)

            test_queries = random.choices(test_keywords, k=2)
            keywords = categories_queries + test_queries

            gs.search_work(keywords)

            try:
                G2Page(
                    self.driver, self.human_simulator, product, comparing_product
                ).run_g2_product()

                try:
                    G2Comparison(
                        self.driver, self.human_simulator, comparing_product
                    ).run_g2_comparisons()
                except :
                    status = "Failed at G2 Comparison"
                    logger.error(status)

                status = "Done"

            except:
                status = "Failed at G2 Page"
                logger.error(status)

        except:
            status = "Failed at Google Search"
            logger.error(status)

        self.set_data(product, comparing_product,browser,location,status)

        self.excel.save_excel(row=self.items)
        



if __name__ == "__main__":
    logger.info("Script Has Been Started..............")

    products = {
        "SauceLabs": ["Ranorex", "Testcomplete"],
        # "BrowserStack": ["Testrail", "Perfecto"],
    }
    try:

        vpn = ExpressVPN()
        locations = vpn.get_vpn_locations()

        for product, comparing_products in products.items():

            location = random.choice(locations)
            # vpn.connect(location)
            
            manager = Browser(headless=False)
            driver , browser = manager.launch("chrome")

            human_simulator = HumanSimulator(driver)

            gs = GoogleSearch(driver,human_simulator)
            gs.get_google()

            for comparing_product in comparing_products:

                g2_project = G2Automation(driver, human_simulator, gs)

                try:
                    g2_project.run_g2(product, comparing_product,browser,location)
                except Exception as e:
                    logger.error(f"run_g2 failed for {product}/{comparing_product}: {e}")

            logger.info(f"Comparison Process Completed for {product}")

            # vpn.disconnect()

    except Exception as e:
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
        # vpn.disconnect()
