import random
import time
import sys
from pathlib import Path

# if __package__ in (None, ""):
#     sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from src.commons import *
from src.automation.human_simulator import HumanSimulator
from src.automation.xpath_pools import G2_COMPARISON_POOL
from src.automation.errors import AccessDeniedError, RetryableFailure   # <-- CHANGED
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
        # save_html(self.driver.page_source, f"G2_Comparison_Page_{self.comparing_product}.html")

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
                            time.sleep(random.uniform(0.5, 2))
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

        compare_element = wait_for_element(
            self.driver, (By.XPATH, compare_xpath),
            condition="clickable", timeout=5, poll=0.5,
        )

        # === FIX: guard against None from wait_for_element ===
        if compare_element is None:
            take_screenshot(self.driver,f"G2_Comparison_Page_{self.comparing_product}_compare_not_found.png")
            save_html(
                self.driver.page_source,
                f"G2_Comparison_Page_{self.comparing_product}_compare_not_found.html",
            )
            logger.error(
                f"Comparison block not found for '{self.comparing_product}' "
                f"on page: {self.driver.current_url}"
            )
            raise RetryableFailure(
                f"Compare Now block not found for {self.comparing_product}"
            )

        logger.info("Clicking comparison button (human)...")

        reject_button = self.driver.find_elements(By.XPATH, "//button[contains(.,'Reject Non-Essential')]")
        if reject_button:
            reject_button = reject_button[0]
            try:
                self.human_simulator.mouse_click(reject_button)
                logger.info("Clicked 'Reject Non-Essential' button.")
            except Exception:
                reject_button.click()
                logger.info("Clicked 'Reject Non-Essential' button (fallback).")
            # time.sleep(random.uniform(0.8, 2.6))

        try:
            # self.human_simulator.scroll_to_element_human(compare_element,align="end")
            self.human_simulator.bring_element_into_view_with_wheel(compare_element)
            self.human_simulator.mouse_click_after_hover(compare_element)
        except Exception as e:
            save_html(self.driver.page_source, f"G2_Comparison_Page_{self.comparing_product}_after_click.html")
            take_screenshot(self.driver, f"G2_Comparison_Page_{self.comparing_product}_after_click.png")
            logger.warning(f"Human click failed, trying JS click.{e}")
            self.driver.execute_script("arguments[0].click();", compare_element)

        logger.info("Comparison button clicked.")
        time.sleep(random.uniform(0.5, 1.2))

    # ==================================================================
    # BROWSE — delegates to HumanSimulator with the pool
    # ==================================================================
    def browse_comparison_page(self, min_seconds=24, max_seconds=33):
        duration = random.uniform(min_seconds, max_seconds)
        self.human_simulator.browse_page_randomly(
                duration=duration,
                pool=G2_COMPARISON_POOL,
                do_scroll_duration=0.65
            )

    # ==================================================================
    # COMPLETE FLOW
    # ==================================================================
    def process_sauce_labs_comparison(self):
        logger.info("Starting Sauce Labs comparison flow")

        self.open_g2_compare_page()
        logger.info("Comparison page opened.")

        # --- CHANGED: raise AccessDeniedError so the outer loop can retry
        #              the whole product/comparing_product pair on a new VPN.
        for refresh_attempt in range(3):
            if not check_for_block(self.driver):
                break
            logger.warning(
                f"[G2 Comparison] Access-Denied page detected "
                f"(refresh {refresh_attempt + 1}/5)"
            )
            self.driver.refresh()
            time.sleep(random.uniform(0.5, 1.5))
        else:
            logger.error("G2 Comparison page is still Access Denied "
                         "after 5 refreshes")
            raise AccessDeniedError("G2 Comparison page got Access Denied")
        # --------------------------------------------------------------------

        self.browse_comparison_page()

        logger.info("Comparison page browsing completed.")

        logger.info("Searching for footer link...")
        footer_xpath = '//div[@id="footer-inner"]/div[2]/ul/li[1]/a'

        try:
            footer_link = wait_for_element(
                self.driver, (By.XPATH, footer_xpath),
                condition="presence", timeout=0.5, poll=0.5,
            )
            logger.info("Footer link found.")

            # try:
            #     self.human_simulator.bring_element_into_view_with_wheel(footer_link)
            # except Exception:
            #     self.driver.execute_script(
            #         "arguments[0].scrollIntoView({block:'center'});", footer_link
            #     )
            # time.sleep(random.uniform(0, 2))

            logger.info("Clicking footer link (human)...")
            try:
                self.human_simulator.mouse_click_after_hover(footer_link)
            except Exception:
                footer_link.click()
            logger.info("Footer link clicked successfully.")

        except Exception as error:
            logger.error(f"Footer link click failed: {error}")
            
            save_html(
                self.driver.page_source,
                f"G2_Comparison_Page_{self.comparing_product}_footer_click_failed.html",
            )
            take_screenshot(self.driver, f"G2_Comparison_Page_{self.comparing_product}_footer_click_failed.png")
            
            raise RetryableFailure(f"Footer link click failed: {error}")

        # time.sleep(random.uniform(3, 5))
        logger.info("New page opened.")

        self.browse_comparison_page(min_seconds=5, max_seconds=10)

        logger.info("Second page browsing completed.")
        logger.info("Complete Sauce Labs flow finished.")

    def run_g2_comparisons(self):
        """
        Run the comparison flow.

        Important: AccessDeniedError and RetryableFailure are RE-RAISED so
        the top-level runner can restart the whole pair on a fresh VPN.
        All other exceptions are logged and re-raised as RetryableFailure.
        """
        try:
            self.process_sauce_labs_comparison()
        except (AccessDeniedError, RetryableFailure):
            raise                                   # <-- let caller retry
        except Exception as error:
            logger.error(f"ERROR OCCURRED: {error}")
            raise RetryableFailure(str(error)) from error


if __name__ == "__main__":
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=152)
    url_dict = {
        "BrowserStack": "https://www.g2.com/products/browserstack/reviews",
        "SauceLabs": "https://www.g2.com/products/sauce-labs/reviews",
    }
    product = "SauceLabs"
    driver.get(url_dict[product])

    comparing_product = "TestComplete"
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