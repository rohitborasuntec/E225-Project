import random
import time
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from src.commons import wait_for_element, save_html
from src.automation.human_simulator import HumanSimulator
from src.automation.xpath_pools import G2_COMPARISON_POOL
from src.logging import logger


class G2Comparison:

    def __init__(self, driver, human_simulator, comparing_product):
        self.driver = driver
        self.human_simulator = human_simulator
        self.comparing_product = comparing_product

    # ==================================================================
    # OPEN G2 COMPARE PAGE
    # ==================================================================
    def open_g2_compare_page(self):
        # logger.info("Opening Sauce Labs reviews page...")
        save_html(self.driver.page_source, "G2_Comparison_Page")
        
        # Cookie banner
        try:
            cookie_banner = self.driver.find_elements(
                By.XPATH,
                '//div[@role="dialog" and @aria-label="Cookie Consent Banner"]',
            )
            if cookie_banner:
                logger.info("Cookie Consent Banner found.")
                cookie_buttons = cookie_banner[0].find_elements(By.XPATH, ".//button")
                for button in cookie_buttons:
                    try:
                        if button.is_displayed():
                            logger.info(f"Cookie button found: {button.text.strip()}")
                            try:
                                self.human_simulator.mouse_click(button)
                            except Exception:
                                button.click()
                            time.sleep(random.uniform(1, 3))
                            logger.info("Cookie Consent handled.")
                            break
                    except Exception:
                        continue
        except Exception as error:
            logger.warning(f"Cookie Consent handling skipped: {error}")

        # Find comparison block
        compare_xpath = (
            f"//div[@class='inset-card inset-card--sm']"
            f"//*[contains(text(),'{self.comparing_product}')]"
            f"/../../..//*[contains(text(),'Compare Now')]//ancestor::a"
        )
        logger.info("Searching for comparison block...")
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                compare_element = self.driver.find_element(By.XPATH, compare_xpath)
                if compare_element.is_displayed():
                    logger.info("Comparison block found.")
                    break
            except Exception:
                pass
            self.human_simulator.scroll_page()
            time.sleep(random.uniform(0.5, 1))
        else:
            logger.error("Comparison block was not found.")

        compare_element = wait_for_element(
            self.driver, (By.XPATH, compare_xpath),
            condition="clickable", timeout=10, poll=0.5,
        )

        logger.info("Clicking comparison button (human)...")
        try:
            self.human_simulator.mouse_click(compare_element)
        except Exception:
            logger.warning("Human click failed, trying JS click.")
            self.driver.execute_script("arguments[0].click();", compare_element)

        logger.info("Comparison button clicked.")
        time.sleep(random.uniform(3, 5))

    # ==================================================================
    # BROWSE — delegates to HumanSimulator with the pool
    # ==================================================================
    def browse_comparison_page(self, duration=60):
        self.human_simulator.browse_page_randomly(
            duration=duration,
            pool=G2_COMPARISON_POOL,
        )

    # ==================================================================
    # COMPLETE FLOW
    # ==================================================================
    def process_sauce_labs_comparison(self):
        logger.info("=" * 60)
        logger.info("Starting Sauce Labs comparison flow")
        logger.info("=" * 60)

        self.open_g2_compare_page()
        logger.info("Comparison page opened.")

        self.browse_comparison_page(duration=60)
        logger.info("Comparison page browsing completed.")

        logger.info("Searching for footer link...")
        footer_xpath = '//div[@id="footer-inner"]/div[2]/ul/li[1]/a'
        try:
            footer_link = wait_for_element(
                self.driver, (By.XPATH, footer_xpath),
                condition="presence", timeout=15, poll=0.5,
            )
            logger.info("Footer link found.")
            try:
                self.human_simulator.bring_element_into_view_with_wheel(footer_link)
            except Exception:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", footer_link
                )
            time.sleep(random.uniform(1, 2))

            logger.info("Clicking footer link (human)...")
            try:
                self.human_simulator.mouse_click_after_hover(footer_link)
            except Exception:
                footer_link.click()
            logger.info("Footer link clicked successfully.")
        except Exception as error:
            logger.error(f"Footer link click failed: {error}")
            return

        time.sleep(random.uniform(3, 5))
        logger.info("New page opened.")

        self.browse_comparison_page(duration=5)
        logger.info("Second page browsing completed.")
        logger.info("Complete Sauce Labs flow finished.")

    def run_g2_comparisons(self):
        try:
            self.process_sauce_labs_comparison()
        except Exception as error:
            logger.error(f"ERROR OCCURRED: {error}")


if __name__ == "__main__":
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=152)
    url_dict = {
        "BrowserStack": "https://www.g2.com/products/browserstack/reviews",
        "SauceLabs": "https://www.g2.com/products/sauce-labs/reviews",
    }
    product = "BrowserStack"
    driver.get(url_dict[product])

    comparing_product = "Qase"
    human_simulator = HumanSimulator(driver, use_native_cursor=False)

    try:
        G2Comparison(driver, human_simulator, comparing_product).run_g2_comparisons()
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass