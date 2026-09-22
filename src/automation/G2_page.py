import random
import time
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.commons import wait_for_element, save_html
from src.automation.human_simulator import HumanSimulator
from src.logging import logger


class G2Page:

    target_dic = {
        "SauceLabs": "Sauce Labs Reviews 2026: Details, Pricing, & Features",
        "BrowserStack" : "BrowserStack Reviews 2026: Details, Pricing, & Features"
    }

    # search_query = "g2 sauce labs"
    max_scroll_attempts = 4
    top_rated_section_xpath = '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]'
    alternative_link_xpath = (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div[2]/a/div/span'
    )
    breadcrumb_xpath = '//*[@id="breadcrumbs"]/li[5]/a/span'
    login_modal_close_xpath = '//*[@id="login-modal"]/div[2]/div/div[2]/button'
    
    def __init__(self, driver, human_simulator,product,comparing_product):
        self.driver = driver
        self.human_simulator = human_simulator
        self.target_text = self.target_dic[product]
        self.search_query = f"G2 {product}"
        self.comparing_product = comparing_product
    # ------------------------------------------------------------------ #
    # small polling helper (replaces WebDriverWait for non-locator cases)
    # ------------------------------------------------------------------ #
    def _poll(self, fn, timeout=30, poll=0.5):
        """Call fn() until it returns something truthy, else raise TimeoutError."""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = fn()
                if last:
                    return last
            except Exception:
                pass
            time.sleep(poll)
        raise TimeoutError(f"Condition not met within {timeout}s (last={last!r})")

    # ------------------------------------------------------------------ #
    # login modal (ported from old script)
    # ------------------------------------------------------------------ #
    def close_login_modal_if_present(self, timeout=1):
        """Close G2's login modal with the mouse when it appears."""
        try:
            modal = WebDriverWait(self.driver, timeout, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.ID, "login-modal"))
            )
        except TimeoutException:
            return False

        buttons = modal.find_elements(By.CSS_SELECTOR, "button")
        visible_buttons = [b for b in buttons if b.is_displayed()]
        if not visible_buttons:
            close_button = self.driver.find_element(By.XPATH, self.login_modal_close_xpath)
        else:
            # The cross is the visible button nearest the modal's top-right corner.
            close_button = max(
                visible_buttons,
                key=lambda b: b.rect["x"] - b.rect["y"],
            )

        # Popup dismissal should be quick: short mouse move, tiny pause, click.
        actions = ActionChains(self.driver)
        actions.move_to_element(close_button).pause(0.05).click().perform()
        WebDriverWait(self.driver, 2, poll_frequency=0.1).until(
            EC.invisibility_of_element_located((By.ID, "login-modal"))
        )
        logger.info("Closed G2 login modal")
        return True

    # ------------------------------------------------------------------ #
    # Google results
    # ------------------------------------------------------------------ #
    def find_exact_result_link(self, expected_text):
        """Return the Google result link with an exactly matching H3 title."""
        headings = self.driver.find_elements(By.CSS_SELECTOR, "a[href] h3")
        for heading in headings:
            try:
                if (heading.text or "").strip() == expected_text:
                    return heading.find_element(By.XPATH, "./ancestor::a[1]")
            except Exception:
                continue
        return None

    def scroll_down(self):
        try:
            scroll_distance = random.randint(600, 1000)
            steps = random.randint(5, 8)

            for _ in range(steps):
                self.driver.execute_script(
                    "window.scrollBy(0, arguments[0]);",
                    scroll_distance / steps
                )
                time.sleep(random.uniform(0.05, 0.12))

            time.sleep(random.uniform(0.5, 1.0))

            logger.info(
                f"Scrolled down {scroll_distance}px"
            )

            return True

        except Exception as error:
            logger.warning(f"Scrolling failed: {error}")
            return False
        
    def scroll_until_result_is_found(self, expected_text):
        """Scroll down in human-sized steps until the exact result is present."""
        for _ in range(self.max_scroll_attempts):
            result_link = self.find_exact_result_link(expected_text)
            if result_link is not None:
                return result_link

            # self.human_simulator.scroll_page(total_scroll=250, step_delay=0.25, direction="down")
            self.scroll_down()
            time.sleep(2)

        return self.find_exact_result_link(expected_text)

    def switch_to_g2_page(self):
        """Switch to the G2 page whether Google opened it here or in a new tab."""
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if "g2.com" in self.driver.current_url:
                return True
        return False
    
    # ------------------------------------------------------------------ #
    # G2 page interactions
    # ------------------------------------------------------------------ #
    def click_one_random_show_more(self):
        """Choose exactly one Show More control from the available G2 buttons."""
        self.close_login_modal_if_present(timeout=0.4)

        def show_more_buttons():
            buttons = self.driver.find_elements(
                By.XPATH,
                '//button[.//*[@data-elv--accordion--show-more-controller-target="triggerText" '
                'and normalize-space()="Show More"]]',
            )
            return [b for b in buttons if b.is_displayed() and b.is_enabled()]

        choices = WebDriverWait(self.driver, 30).until(lambda _: show_more_buttons())
        button = random.choice(choices)

        # --- resolve accordion controller + panel for robust open detection ---
        controller = button.find_element(
            By.XPATH,
            './ancestor::*[contains(@data-controller, '
            '"elv--accordion--show-more-controller")][1]',
        )
        panels = controller.find_elements(
            By.CSS_SELECTOR,
            '[data-elv--accordion--show-more-controller-target="panel"]',
        )
        panel = panels[0] if panels else None
        initial_panel_height = panel.size["height"] if panel else 0

        def accordion_is_open():
            try:
                trigger_text = button.find_element(
                    By.CSS_SELECTOR,
                    '[data-elv--accordion--show-more-controller-target="triggerText"]',
                ).text.strip()
                if trigger_text == "Show Less" or button.get_attribute("aria-expanded") == "true":
                    return True
                if (
                    controller.get_attribute(
                        "data-elv--accordion--show-more-controller-open-value"
                    ) == "true"
                ):
                    return True
                panel_id = (
                    button.get_attribute("aria-controls")
                    or button.get_attribute("aria_controls")
                )
                if panel_id:
                    current_panel = self.driver.find_element(By.ID, panel_id)
                    if current_panel.get_attribute("aria-hidden") == "false":
                        return True
                if panel is not None and panel.size["height"] > initial_panel_height + 10:
                    return True
            except Exception:
                return False
            return False

        # --- click with fallback chain (human → element → JS) ---
        self.human_simulator.mouse_hover(button)
        self.close_login_modal_if_present(timeout=0.4)
        try:
            self.human_simulator.mouse_click_after_hover(button)
        except ElementClickInterceptedException:
            self.close_login_modal_if_present(timeout=2)

        try:
            WebDriverWait(self.driver, 2, poll_frequency=0.1).until(
                lambda _: accordion_is_open()
            )
        except TimeoutException:
            # Human mouse click may be ignored by G2's Stimulus controller.
            self.close_login_modal_if_present(timeout=2)
            button.click()
            try:
                WebDriverWait(self.driver, 2, poll_frequency=0.1).until(
                    lambda _: accordion_is_open()
                )
            except TimeoutException:
                self.close_login_modal_if_present(timeout=1)
                self.driver.execute_script("arguments[0].click();", button)
                try:
                    WebDriverWait(self.driver, 2, poll_frequency=0.1).until(
                        lambda _: accordion_is_open()
                    )
                except TimeoutException:
                    logger.warning(
                        "Show More clicked, but G2 did not expose expansion "
                        "state; continuing"
                    )
                    return

        logger.info("Clicked one randomly selected Show More button")

    def follow_clicked_link(self, old_url, old_handles):
        """Follow a mouse-clicked link in either the current tab or a new tab."""
        def destination_opened():
            new_handles = set(self.driver.window_handles) - old_handles
            if new_handles:
                self.driver.switch_to.window(next(iter(new_handles)))
                return self.driver.current_url != "about:blank"
            return self.driver.current_url != old_url

        WebDriverWait(self.driver, 30).until(lambda _: destination_opened())

    def explore_top_rated_alternative(self):
        """Explore the supplied card with the mouse, then open its alternative."""
        self.close_login_modal_if_present(timeout=0.4)
        section = wait_for_element(
            self.driver,
            (By.XPATH, self.top_rated_section_xpath),
            condition="presence",
            poll=0.5,
        )
        self.human_simulator.bring_element_into_view_with_wheel(section)
        self.human_simulator.move_mouse_around(moves=3)
        self.human_simulator.mouse_hover(section, hover_time=1.0)
        section_lines = section.text.strip().splitlines()
        heading = self.driver.find_elements(
            By.XPATH,
            '//*[@id="details"]//*[normalize-space(.)="Top-Rated Alternatives"]',
        )
        if heading:
            self.human_simulator.mouse_hover(heading[-1], hover_time=1.0)
            logger.info("Explored section: Top-Rated Alternatives")
        else:
            logger.info(
                f"Explored supplied card: "
                f"{section_lines[0] if section_lines else 'unnamed'}"
            )

        alternative_label = wait_for_element(
            self.driver,
            (By.XPATH, self.alternative_link_xpath),
            condition="presence",
            poll=0.5,
        )
        alternative_link = alternative_label.find_element(By.XPATH, "./ancestor::a[1]")
        logger.info(f"Alternative: {alternative_link.text.strip()}")
        self.human_simulator.move_mouse_around(moves=2)
        self.human_simulator.mouse_hover(alternative_link, hover_time=1.0)
        old_url = self.driver.current_url
        old_handles = set(self.driver.window_handles)
        self.human_simulator.mouse_click_after_hover(alternative_link)
        self.follow_clicked_link(old_url, old_handles)
        logger.info(f"Opened alternative: {self.driver.current_url}")

    def open_fifth_breadcrumb(self):
        """Click the fifth breadcrumb using mouse movement and mouse click."""
        self.close_login_modal_if_present(timeout=0.4)
        breadcrumb_label = wait_for_element(
            self.driver,
            (By.XPATH, self.breadcrumb_xpath),
            condition="presence",
            poll=0.5,
        )
        breadcrumb_link = breadcrumb_label.find_element(By.XPATH, "./ancestor::a[1]")
        logger.info(f"Breadcrumb: {breadcrumb_link.text.strip()}")
        self.human_simulator.move_mouse_around(moves=2)
        self.human_simulator.mouse_hover(breadcrumb_link, hover_time=0.8)
        old_url = self.driver.current_url
        old_handles = set(self.driver.window_handles)
        self.human_simulator.mouse_click_after_hover(breadcrumb_link)
        self.follow_clicked_link(old_url, old_handles)
        logger.info(f"Opened breadcrumb: {self.driver.current_url}")


    def browse_g2_page(self, min_seconds=75, max_seconds=150):
        """Read, hover, and occasionally inspect one image without continuous scrolling."""
        duration = random.uniform(min_seconds, max_seconds)
        deadline = time.monotonic() + duration
        actions = []
        image_clicked = False
        while time.monotonic() < deadline:
            readable = self._visible_reading_elements()
            images = [
                image for image in self.driver.find_elements(By.CSS_SELECTOR, "main img")
                if image.is_displayed() and image.size["width"] >= 80
                and image.size["height"] >= 60
            ]
            if images and not image_clicked and random.random() < 0.25:
                image = random.choice(images)
                self.human_simulator.mouse_hover(image)
                self.human_simulator.mouse_click_after_hover(image)
                time.sleep(self._gauss(5, 1, 3, 8))
                image_clicked = True
                actions.append("image")
            elif readable:
                element = random.choice(readable)
                self.human_simulator.mouse_hover(element)
                time.sleep(self._gauss(4, 1, 2, 7))
                actions.append("read")
            else:
                self.human_simulator.move_mouse_around(1)
                actions.append("wander")

        return {"seconds": round(duration), "actions": actions, "picture_clicked": image_clicked}

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def run_g2_saucelabs(self):
        try:
            logger.info("G2 Sauce Labs automation started")

            wait_for_element(
                self.driver,
                (By.CSS_SELECTOR, "a[href] h3"),
                condition="presence",
                poll=0.5,
            )

            self.human_simulator.input_search_query(query=self.search_query, suggestion=False)
            
            result_link = self.scroll_until_result_is_found(self.target_text)
            if result_link is None:
                raise RuntimeError(
                    f"Could not find the exact Google result: {self.target_text}"
                )

            self.human_simulator.move_mouse_around(moves=2)
            self.human_simulator.mouse_hover(result_link, hover_time=1.2)
            self.human_simulator.mouse_click_after_hover(result_link)
            self._poll(self.switch_to_g2_page, timeout=30, poll=0.3)
            logger.info(f"Opened result: {self.driver.current_url}")
            save_html(self.driver.page_source,"G2_SauceLabs")
            self.close_login_modal_if_present()
            self.human_simulator.move_mouse_around(moves=3)

            total_words = random.choice([4, 5, 6, 9])
            first_count = random.randint(1, min(3, total_words - 2))
            second_count = random.randint(1, min(2, total_words - first_count - 1))
            final_count = total_words - first_count - second_count

            self.click_one_random_show_more()
            self.close_login_modal_if_present(timeout=0.4)
            first_words = self.human_simulator.select_random_words(first_count)
            logger.info(f"Mouse-selected on Sauce Labs page: {first_words}")
            self.human_simulator.move_mouse_around(moves=2)
            # self.explore_top_rated_alternative()
            self.close_login_modal_if_present(timeout=0.4)
            second_words = self.human_simulator.select_random_words(
                second_count, already_selected=first_words
            )
            logger.info(f"Mouse-selected on Alternatives page: {second_words}")
            try:
                self.open_fifth_breadcrumb()
            except:
                logger.error("Not Found fifth breadcrumb")
            final_words = self.human_simulator.select_random_words(
                final_count, already_selected=first_words + second_words
            )
            logger.info(f"Mouse-selected after breadcrumb: {final_words}")
            logger.info(
                f"Total distinct words selected: "
                f"{len(first_words + second_words + final_words)}"
            )
            try:
                browsing = self.browse_g2_page()
                logger.info(f"Varied G2 browsing: {browsing}")
            except:
                logger.error("Browse g2 error")
            time.sleep(10)
            logger.info("G2 Sauce Labs automation completed successfully")
        except Exception as error:
            logger.exception(f"G2 Sauce Labs automation failed: {error}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")

# ---------------------------------------------------------------------- #
# module-level entry point (matches old script's `run()`)
# ---------------------------------------------------------------------- #
def run():
    options = uc.ChromeOptions()
    options.add_argument("window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=152)

    try:
        logger.info("Opening Google")
        driver.get("https://www.google.com")

        human_simulator = HumanSimulator(driver)
        product = "BrowserStack" 
        comparing_product = "Testrail"
        automation = G2Page(driver, human_simulator,product,comparing_product)
        automation.run_g2_saucelabs()
    except Exception:
        # run() already logs + quits; this just prevents double-quit
        raise


if __name__ == "__main__":
    run()
