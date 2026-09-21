import random
import time

import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.commons import (
    wait_for_element,
    select_random_visible_text,
)
from src.automation.human_simulator import HumanSimulator
from src.logging import logger


class G2SauceLabs:

    target_text = "Sauce Labs Reviews 2026: Details, Pricing, & Features"
    search_query = "g2 sauce labs"

    max_scroll_attempts = 4

    top_rated_section_xpath = (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]'
    )

    alternative_link_xpath = (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div[2]/a/div/span'
    )

    breadcrumb_xpath = '//*[@id="breadcrumbs"]/li[5]/a/span'

    login_modal_close_xpath = (
        '//*[@id="login-modal"]/div[2]/div/div[2]/button'
    )

    # Visible text browsing duration
    visible_text_duration = 60

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

        # Start timer when G2 automation starts.
        # This timer is passed to common.py visible-text function.
        self.visible_text_start_time = None

    # ------------------------------------------------------------------ #
    # COMMON VISIBLE TEXT
    # ------------------------------------------------------------------ #

    def select_visible_text(self):
        """
        Use the common.py visible-text function.

        The actual visible-text detection and JavaScript Range selection
        are implemented only once in commons.py.
        """

        if self.visible_text_start_time is None:
            self.visible_text_start_time = time.time()

        return select_random_visible_text(
            driver=self.driver,
            duration=self.visible_text_duration,
            start_time=self.visible_text_start_time,
        )

    # ------------------------------------------------------------------ #
    # SMALL POLLING HELPER
    # ------------------------------------------------------------------ #

    def _poll(self, fn, timeout=30, poll=0.5):
        """
        Call fn() until it returns a truthy value.
        """

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

        raise TimeoutError(
            f"Condition not met within {timeout}s (last={last!r})"
        )

    # ------------------------------------------------------------------ #
    # LOGIN MODAL
    # ------------------------------------------------------------------ #

    def close_login_modal_if_present(self, timeout=1):
        """
        Close G2 login modal if it appears.
        """

        try:

            modal = WebDriverWait(
                self.driver,
                timeout,
                poll_frequency=0.1,
            ).until(
                EC.visibility_of_element_located(
                    (By.ID, "login-modal")
                )
            )

        except TimeoutException:
            return False

        buttons = modal.find_elements(
            By.CSS_SELECTOR,
            "button",
        )

        visible_buttons = [
            button
            for button in buttons
            if button.is_displayed()
        ]

        if not visible_buttons:

            close_button = self.driver.find_element(
                By.XPATH,
                self.login_modal_close_xpath,
            )

        else:

            close_button = max(
                visible_buttons,
                key=lambda button: (
                    button.rect["x"] - button.rect["y"]
                ),
            )

        actions = ActionChains(self.driver)

        actions.move_to_element(
            close_button
        ).pause(
            0.05
        ).click().perform()

        try:

            WebDriverWait(
                self.driver,
                2,
                poll_frequency=0.1,
            ).until(
                EC.invisibility_of_element_located(
                    (By.ID, "login-modal")
                )
            )

        except TimeoutException:
            pass

        logger.info("Closed G2 login modal")

        return True

    # ------------------------------------------------------------------ #
    # GOOGLE RESULTS
    # ------------------------------------------------------------------ #

    def find_exact_result_link(self, expected_text):
        """
        Find Google result with exactly matching H3 title.
        """

        headings = self.driver.find_elements(
            By.CSS_SELECTOR,
            "a[href] h3",
        )

        for heading in headings:

            try:

                heading_text = (
                    heading.text or ""
                ).strip()

                if heading_text == expected_text:

                    return heading.find_element(
                        By.XPATH,
                        "./ancestor::a[1]",
                    )

            except Exception:
                continue

        return None

    # ------------------------------------------------------------------ #
    # SCROLLING
    # ------------------------------------------------------------------ #

    def scroll_down(self):

        try:

            scroll_distance = random.randint(
                600,
                1000,
            )

            steps = random.randint(
                5,
                8,
            )

            for _ in range(steps):

                self.driver.execute_script(
                    "window.scrollBy(0, arguments[0]);",
                    scroll_distance / steps,
                )

                time.sleep(
                    random.uniform(
                        0.05,
                        0.12,
                    )
                )

            time.sleep(
                random.uniform(
                    0.5,
                    1.0,
                )
            )

            logger.info(
                f"Scrolled down {scroll_distance}px"
            )

            return True

        except Exception as error:

            logger.warning(
                f"Scrolling failed: {error}"
            )

            return False

    def scroll_until_result_is_found(
        self,
        expected_text,
    ):
        """
        Scroll Google results until exact result is found.
        """

        for _ in range(
            self.max_scroll_attempts
        ):

            result_link = (
                self.find_exact_result_link(
                    expected_text
                )
            )

            if result_link is not None:
                return result_link

            self.scroll_down()

            time.sleep(2)

        return self.find_exact_result_link(
            expected_text
        )

    # ------------------------------------------------------------------ #
    # SWITCH TO G2
    # ------------------------------------------------------------------ #

    def switch_to_g2_page(self):
        """
        Switch to G2 page if it opened in current tab
        or a new tab.
        """

        for handle in self.driver.window_handles:

            try:

                self.driver.switch_to.window(
                    handle
                )

                if "g2.com" in self.driver.current_url:

                    return True

            except Exception:
                continue

        return False

    # ------------------------------------------------------------------ #
    # SHOW MORE
    # ------------------------------------------------------------------ #

    def click_one_random_show_more(self):
        """
        Select exactly one random Show More button.
        """

        self.close_login_modal_if_present(
            timeout=0.4
        )

        def show_more_buttons():

            buttons = self.driver.find_elements(
                By.XPATH,
                '//button[.//*[@data-elv--accordion--show-more-controller-target="triggerText" '
                'and normalize-space()="Show More"]]',
            )

            return [
                button
                for button in buttons
                if button.is_displayed()
                and button.is_enabled()
            ]

        try:

            choices = WebDriverWait(
                self.driver,
                30,
            ).until(
                lambda _: show_more_buttons()
            )

        except TimeoutException:

            logger.warning(
                "No Show More button found"
            )

            return False

        button = random.choice(
            choices
        )

        try:

            controller = button.find_element(
                By.XPATH,
                './ancestor::*[contains(@data-controller, '
                '"elv--accordion--show-more-controller")][1]',
            )

        except Exception:

            controller = None

        panel = None
        initial_panel_height = 0

        if controller:

            try:

                panels = controller.find_elements(
                    By.CSS_SELECTOR,
                    '[data-elv--accordion--show-more-controller-target="panel"]',
                )

                if panels:

                    panel = panels[0]

                    initial_panel_height = (
                        panel.size["height"]
                    )

            except Exception:
                pass

        def accordion_is_open():

            try:

                trigger_text = button.find_element(
                    By.CSS_SELECTOR,
                    '[data-elv--accordion--show-more-controller-target="triggerText"]',
                ).text.strip()

                if trigger_text == "Show Less":

                    return True

                if button.get_attribute(
                    "aria-expanded"
                ) == "true":

                    return True

                if controller:

                    if controller.get_attribute(
                        "data-elv--accordion--show-more-controller-open-value"
                    ) == "true":

                        return True

                panel_id = (
                    button.get_attribute(
                        "aria-controls"
                    )
                    or button.get_attribute(
                        "aria_controls"
                    )
                )

                if panel_id:

                    current_panel = (
                        self.driver.find_element(
                            By.ID,
                            panel_id,
                        )
                    )

                    if current_panel.get_attribute(
                        "aria-hidden"
                    ) == "false":

                        return True

                if panel is not None:

                    if (
                        panel.size["height"]
                        > initial_panel_height + 10
                    ):

                        return True

            except Exception:
                return False

            return False

        # -------------------------------------------------------------- #
        # Human-like mouse click
        # -------------------------------------------------------------- #

        self.human_simulator.mouse_hover(
            button
        )

        self.close_login_modal_if_present(
            timeout=0.4
        )

        try:

            self.human_simulator.mouse_click_after_hover(
                button
            )

        except ElementClickInterceptedException:

            self.close_login_modal_if_present(
                timeout=2
            )

        # -------------------------------------------------------------- #
        # Verify click
        # -------------------------------------------------------------- #

        try:

            WebDriverWait(
                self.driver,
                2,
                poll_frequency=0.1,
            ).until(
                lambda _: accordion_is_open()
            )

        except TimeoutException:

            self.close_login_modal_if_present(
                timeout=2
            )

            try:

                button.click()

                WebDriverWait(
                    self.driver,
                    2,
                    poll_frequency=0.1,
                ).until(
                    lambda _: accordion_is_open()
                )

            except TimeoutException:

                self.close_login_modal_if_present(
                    timeout=1
                )

                self.driver.execute_script(
                    "arguments[0].click();",
                    button,
                )

                try:

                    WebDriverWait(
                        self.driver,
                        2,
                        poll_frequency=0.1,
                    ).until(
                        lambda _: accordion_is_open()
                    )

                except TimeoutException:

                    logger.warning(
                        "Show More clicked, but G2 did not expose "
                        "expansion state; continuing"
                    )

        logger.info(
            "Clicked one randomly selected Show More button"
        )

        return True

    # ------------------------------------------------------------------ #
    # FOLLOW LINK
    # ------------------------------------------------------------------ #

    def follow_clicked_link(
        self,
        old_url,
        old_handles,
    ):
        """
        Follow clicked link in same tab or new tab.
        """

        def destination_opened():

            new_handles = (
                set(self.driver.window_handles)
                - old_handles
            )

            if new_handles:

                new_handle = next(
                    iter(new_handles)
                )

                self.driver.switch_to.window(
                    new_handle
                )

                return (
                    self.driver.current_url
                    != "about:blank"
                )

            return (
                self.driver.current_url
                != old_url
            )

        WebDriverWait(
            self.driver,
            30,
        ).until(
            lambda _: destination_opened()
        )

    # ------------------------------------------------------------------ #
    # TOP-RATED ALTERNATIVE
    # ------------------------------------------------------------------ #

    def explore_top_rated_alternative(self):

        self.close_login_modal_if_present(
            timeout=0.4
        )

        section = wait_for_element(
            self.driver,
            (
                By.XPATH,
                self.top_rated_section_xpath,
            ),
            condition="presence",
            poll=0.5,
        )

        if section is None:

            raise RuntimeError(
                "Top-Rated Alternatives section not found"
            )

        self.human_simulator.bring_element_into_view_with_wheel(
            section
        )

        self.human_simulator.move_mouse_around(
            moves=3
        )

        self.human_simulator.mouse_hover(
            section,
            hover_time=1.0,
        )

        section_lines = (
            section.text.strip().splitlines()
        )

        heading = self.driver.find_elements(
            By.XPATH,
            '//*[@id="details"]//*[normalize-space(.)="Top-Rated Alternatives"]',
        )

        if heading:

            self.human_simulator.mouse_hover(
                heading[-1],
                hover_time=1.0,
            )

            logger.info(
                "Explored section: Top-Rated Alternatives"
            )

        else:

            logger.info(
                "Explored supplied card: "
                f"{section_lines[0] if section_lines else 'unnamed'}"
            )

        alternative_label = wait_for_element(
            self.driver,
            (
                By.XPATH,
                self.alternative_link_xpath,
            ),
            condition="presence",
            poll=0.5,
        )

        if alternative_label is None:

            raise RuntimeError(
                "Alternative link not found"
            )

        alternative_link = (
            alternative_label.find_element(
                By.XPATH,
                "./ancestor::a[1]",
            )
        )

        logger.info(
            f"Alternative: "
            f"{alternative_link.text.strip()}"
        )

        self.human_simulator.move_mouse_around(
            moves=2
        )

        self.human_simulator.mouse_hover(
            alternative_link,
            hover_time=1.0,
        )

        old_url = self.driver.current_url

        old_handles = set(
            self.driver.window_handles
        )

        self.human_simulator.mouse_click_after_hover(
            alternative_link
        )

        self.follow_clicked_link(
            old_url,
            old_handles,
        )

        logger.info(
            f"Opened alternative: "
            f"{self.driver.current_url}"
        )

    # ------------------------------------------------------------------ #
    # BREADCRUMB
    # ------------------------------------------------------------------ #

    def open_fifth_breadcrumb(self):

        self.close_login_modal_if_present(
            timeout=0.4
        )

        breadcrumb_label = wait_for_element(
            self.driver,
            (
                By.XPATH,
                self.breadcrumb_xpath,
            ),
            condition="presence",
            poll=0.5,
        )

        if breadcrumb_label is None:

            raise RuntimeError(
                "Fifth breadcrumb not found"
            )

        breadcrumb_link = (
            breadcrumb_label.find_element(
                By.XPATH,
                "./ancestor::a[1]",
            )
        )

        logger.info(
            f"Breadcrumb: "
            f"{breadcrumb_link.text.strip()}"
        )

        self.human_simulator.move_mouse_around(
            moves=2
        )

        self.human_simulator.mouse_hover(
            breadcrumb_link,
            hover_time=0.8,
        )

        old_url = self.driver.current_url

        old_handles = set(
            self.driver.window_handles
        )

        self.human_simulator.mouse_click_after_hover(
            breadcrumb_link
        )

        self.follow_clicked_link(
            old_url,
            old_handles,
        )

        logger.info(
            f"Opened breadcrumb: "
            f"{self.driver.current_url}"
        )

    # ------------------------------------------------------------------ #
    # VISIBLE TEXT SELECTION
    # ------------------------------------------------------------------ #

    def select_text_multiple_times(
        self,
        count=3,
    ):
        """
        Reuse common.py's visible-text function.

        This function does not contain any text-selection JavaScript.
        All visible text selection is handled by commons.py.
        """

        selected_count = 0

        for _ in range(count):

            remaining = (
                self.visible_text_duration
                - (
                    time.time()
                    - self.visible_text_start_time
                )
            )

            if remaining <= 2:

                break

            result = (
                self.select_visible_text()
            )

            if result:

                selected_count += 1

            # Small human-like pause
            time.sleep(
                random.uniform(
                    0.5,
                    1.2,
                )
            )

        return selected_count

    # ------------------------------------------------------------------ #
    # MAIN G2 AUTOMATION
    # ------------------------------------------------------------------ #

    def run_g2_saucelabs(self):

        try:

            logger.info(
                "G2 Sauce Labs automation started"
            )

            # Start common visible-text timer.
            self.visible_text_start_time = (
                time.time()
            )

            # ---------------------------------------------------------- #
            # Google result page
            # ---------------------------------------------------------- #

            wait_for_element(
                self.driver,
                (
                    By.CSS_SELECTOR,
                    "a[href] h3",
                ),
                condition="presence",
                poll=0.5,
            )

            self.human_simulator.input_search_query(
                query=self.search_query,
                suggestion=False,
            )

            result_link = (
                self.scroll_until_result_is_found(
                    self.target_text
                )
            )

            if result_link is None:

                raise RuntimeError(
                    "Could not find the exact Google result: "
                    f"{self.target_text}"
                )

            self.human_simulator.move_mouse_around(
                moves=2
            )

            self.human_simulator.mouse_hover(
                result_link,
                hover_time=1.2,
            )

            self.human_simulator.mouse_click_after_hover(
                result_link
            )

            self._poll(
                self.switch_to_g2_page,
                timeout=30,
                poll=0.3,
            )

            logger.info(
                f"Opened result: "
                f"{self.driver.current_url}"
            )

            self.close_login_modal_if_present()

            self.human_simulator.move_mouse_around(
                moves=3
            )

            # ---------------------------------------------------------- #
            # G2 page
            # ---------------------------------------------------------- #

            # Open one Show More section.
            self.click_one_random_show_more()

            self.close_login_modal_if_present(
                timeout=0.4
            )

            # ---------------------------------------------------------- #
            # Select visible text from G2 page.
            #
            # The actual function comes from commons.py.
            # ---------------------------------------------------------- #

            selected = (
                self.select_text_multiple_times(
                    count=3
                )
            )

            logger.info(
                f"Visible text selections on G2 page: "
                f"{selected}"
            )

            # ---------------------------------------------------------- #
            # Explore Top-Rated Alternative
            # ---------------------------------------------------------- #

            self.human_simulator.move_mouse_around(
                moves=2
            )

            self.explore_top_rated_alternative()

            self.close_login_modal_if_present(
                timeout=0.4
            )

            # Select visible text on alternative page.
            selected = (
                self.select_text_multiple_times(
                    count=2
                )
            )

            logger.info(
                f"Visible text selections on "
                f"Alternatives page: {selected}"
            )

            # ---------------------------------------------------------- #
            # Open fifth breadcrumb
            # ---------------------------------------------------------- #

            self.open_fifth_breadcrumb()

            self.close_login_modal_if_present(
                timeout=0.4
            )

            # Select visible text after breadcrumb.
            selected = (
                self.select_text_multiple_times(
                    count=2
                )
            )

            logger.info(
                f"Visible text selections after "
                f"breadcrumb: {selected}"
            )

            # ---------------------------------------------------------- #
            # Additional G2 browsing
            # ---------------------------------------------------------- #

            try:

                browsing = (
                    self.human_simulator.browse_g2_page()
                )

                logger.info(
                    f"Varied G2 browsing: {browsing}"
                )

            except Exception as error:

                logger.warning(
                    f"Additional G2 browsing skipped: "
                    f"{error}"
                )

            time.sleep(5)

            logger.info(
                "G2 Sauce Labs automation completed successfully"
            )

        except Exception as error:

            logger.exception(
                f"G2 Sauce Labs automation failed: "
                f"{error}"
            )

            raise

        finally:

            if self.driver:

                try:

                    self.driver.quit()

                    logger.info(
                        "Browser closed"
                    )

                except Exception:
                    pass


# ---------------------------------------------------------------------- #
# MODULE LEVEL ENTRY POINT
# ---------------------------------------------------------------------- #

def run():

    options = uc.ChromeOptions()

    options.add_argument(
        "window-size=1920,1080"
    )

    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    driver = uc.Chrome(
        options=options,
        version_main=152,
    )

    try:

        logger.info(
            "Opening Google"
        )

        driver.get(
            "https://www.google.com"
        )

        human_simulator = (
            HumanSimulator(driver)
        )

        # Initial Google search.
        human_simulator.input_search_query(
            "Sauce Labs Reviews 2026: Details, Pricing, & Features"
        )

        logger.info(
            "Google search submitted"
        )

        automation = G2SauceLabs(
            driver,
            human_simulator,
        )

        # Correct method call.
        automation.run_g2_saucelabs()

    except Exception as error:

        logger.exception(
            f"G2 automation failed: {error}"
        )

        try:
            driver.quit()
        except Exception:
            pass

        raise


if __name__ == "__main__":
    run()