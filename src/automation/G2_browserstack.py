"""Standalone BrowserStack review-page flow; kept separate from G2Page for now."""

import random
import re
import time

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.automation.G2_page import G2Page
from src.automation.human_simulator import HumanSimulator
from src.commons import save_html
from src.logging import logger


class BrowserStackReviewsProductDetails:
    """Interactions for the BrowserStack Reviews & Product Details card."""

    details_xpath = '//*[@id="details"]/div/div[2]/div/div[1]/div[1]/div'
    show_more_xpath = (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[1]/div/'
        'div[2]/div/div/button/div/span/span'
    )

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    def select_details_phrase(self, details):
        """Select one continuous phrase of 1–10 words in BrowserStack details."""
        word_count = random.randint(1, 10)
        selected = self.driver.execute_script(
            "const root = arguments[0], count = arguments[1];"
            "const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);"
            "const words = []; let node;"
            "while ((node = walker.nextNode())) {"
            "  const parent = node.parentElement;"
            "  if (!parent || !parent.getClientRects().length) continue;"
            "  for (const match of node.data.matchAll(/[A-Za-z]+/g))"
            "    words.push({node, start: match.index, end: match.index + match[0].length});"
            "}"
            "if (words.length < count) return '';"
            "const start = Math.floor(Math.random() * (words.length - count + 1));"
            "const first = words[start], last = words[start + count - 1];"
            "const range = document.createRange();"
            "range.setStart(first.node, first.start);"
            "range.setEnd(last.node, last.end);"
            "const selection = window.getSelection();"
            "selection.removeAllRanges(); selection.addRange(range);"
            "return selection.toString();",
            details,
            word_count,
        ) or ""
        if len(re.findall(r"[A-Za-z]+", selected)) != word_count:
            raise RuntimeError("Could not select a continuous BrowserStack details phrase")
        time.sleep(random.uniform(1.2, 2.5))
        return selected

    def explore(self):
        try:
            details = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, self.details_xpath))
            )
        except TimeoutException as error:
            raise RuntimeError(
                "BrowserStack details did not load; G2 may be showing a verification page"
            ) from error

        self.human_simulator.bring_element_into_view_with_wheel(details)
        self.human_simulator.mouse_hover(details, hover_time=1.0)
        phrase = self.select_details_phrase(details)
        logger.info(f"Selected BrowserStack phrase: {phrase!r}")

        label = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, self.show_more_xpath))
        )
        button = label.find_element(By.XPATH, "./ancestor::button[1]")
        before_length = len(details.text)

        def is_expanded(_):
            try:
                current_label = self.driver.find_element(By.XPATH, self.show_more_xpath)
                current_button = current_label.find_element(By.XPATH, "./ancestor::button[1]")
                return (
                    "show less" in (current_label.text or "").lower()
                    or current_button.get_attribute("aria-expanded") == "true"
                    or len(details.text) > before_length + 10
                )
            except Exception:
                return False

        self.human_simulator.bring_element_into_view_with_wheel(button)
        self.human_simulator.mouse_hover(button, hover_time=0.8)
        self.human_simulator.mouse_click_after_hover(button)
        try:
            WebDriverWait(self.driver, 3, poll_frequency=0.2).until(is_expanded)
        except TimeoutException:
            button = self.driver.find_element(By.XPATH, self.show_more_xpath).find_element(
                By.XPATH, "./ancestor::button[1]"
            )
            self.human_simulator.mouse_hover(button, hover_time=0.5)
            self.human_simulator.mouse_click_after_hover(button)
            try:
                WebDriverWait(self.driver, 3, poll_frequency=0.2).until(is_expanded)
            except TimeoutException as error:
                raise RuntimeError("BrowserStack Show More did not expand") from error
        logger.info("BrowserStack Show More expanded")
        time.sleep(random.uniform(4, 6))


class BrowserStackIntegrations:
    """Scroll to the BrowserStack Integrations section with the mouse wheel."""

    section_xpath = '//*[@id="details"]/div/div[2]/div/div[2]/div'

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    def explore(self):
        section = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.section_xpath))
        )
        self.human_simulator.bring_element_into_view_with_wheel(section)
        WebDriverWait(self.driver, 5).until(lambda _: section.is_displayed())
        self.human_simulator.mouse_hover(section, hover_time=1.0)
        logger.info("Scrolled to BrowserStack Integrations")
        time.sleep(random.uniform(2, 4))


class BrowserStackMedia:
    """Open one randomly chosen image from the BrowserStack Media carousel."""

    section_xpath = '//*[@id="details"]/div/div[2]/div/div[3]'
    wrapper_xpath = '//*[@id="swiper-wrapper-15dc9310a67d1684e"]'

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    def explore(self):
        section = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.section_xpath))
        )
        self.human_simulator.bring_element_into_view_with_wheel(section)
        self.human_simulator.mouse_hover(section, hover_time=1.0)

        def visible_images(_):
            wrappers = section.find_elements(By.XPATH, f".{self.wrapper_xpath}")
            if not wrappers:
                wrappers = section.find_elements(By.CSS_SELECTOR, '[id^="swiper-wrapper-"]')
            images = [image for wrapper in wrappers for image in wrapper.find_elements(By.TAG_NAME, "img")]
            return [
                image for image in images
                if image.is_displayed() and image.size["width"] >= 50
                and self.driver.execute_script(
                    "const r=arguments[0].getBoundingClientRect();"
                    "return r.left < innerWidth && r.right > 0 && r.top < innerHeight && r.bottom > 0;",
                    image,
                )
            ]

        images = WebDriverWait(self.driver, 10, poll_frequency=0.3).until(visible_images)
        image = random.choice(images)
        self.human_simulator.mouse_hover(image, hover_time=0.8)
        self.human_simulator.mouse_click_after_hover(image)
        logger.info("Clicked one random BrowserStack Media image")
        view_seconds = random.uniform(5, 12)
        time.sleep(view_seconds)
        logger.info(f"Viewed BrowserStack Media image for {view_seconds:.1f} seconds")


class G2BrowserStack(G2Page):
    def __init__(self, driver, human_simulator):
        super().__init__(driver, human_simulator, "BrowserStack", "")

    def run(self):
        logger.info("G2 BrowserStack automation started")
        self.driver.get("https://www.google.com")
        self.human_simulator.input_search_query(self.search_query, suggestion=False)

        result = self.scroll_until_result_is_found(self.target_text)
        if result is None:
            raise RuntimeError(f"Could not find Google result: {self.target_text}")

        self.human_simulator.mouse_hover(result, hover_time=1.2)
        self.human_simulator.mouse_click_after_hover(result)
        self._poll(self.switch_to_g2_page, timeout=30, poll=0.3)
        logger.info(f"Opened result: {self.driver.current_url}")

        save_html(self.driver.page_source, "G2_BrowserStack")
        self.close_login_modal_if_present(timeout=0.4)
        BrowserStackReviewsProductDetails(
            self.driver, self.human_simulator
        ).explore()
        BrowserStackIntegrations(self.driver, self.human_simulator).explore()
        BrowserStackMedia(self.driver, self.human_simulator).explore()


def run():
    options = uc.ChromeOptions()
    options.add_argument("window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, version_main=152)
    try:
        G2BrowserStack(driver, HumanSimulator(driver)).run()
        logger.info("G2 BrowserStack automation completed")
    except Exception as error:
        logger.exception(f"G2 BrowserStack automation failed: {error}")
        raise
    finally:
        driver.quit()
        logger.info("Browser closed")


if __name__ == "__main__":
    run()
