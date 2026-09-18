import random
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.automation.human_simulator import HumanSimulator
from src.logging import logger


TARGET_TEXT = "Sauce Labs Reviews 2026: Details, Pricing, & Features"
SEARCH_QUERY = "g2 sauce labs"
MAX_SCROLL_ATTEMPTS = 4
TOP_RATED_SECTION_XPATH = '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]'
ALTERNATIVE_LINK_XPATH = (
    '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div[2]/a/div/span'
)
BREADCRUMB_XPATH = '//*[@id="breadcrumbs"]/li[5]/a/span'
LOGIN_MODAL_CLOSE_XPATH = '//*[@id="login-modal"]/div[2]/div/div[2]/button'


def find_exact_result_link(driver, expected_text):
    """Return the Google result link with an exactly matching H3 title."""
    headings = driver.find_elements(By.CSS_SELECTOR, "a[href] h3")
    for heading in headings:
        try:
            if (heading.text or "").strip() == expected_text:
                return heading.find_element(By.XPATH, "./ancestor::a[1]")
        except Exception:
            continue

    return None


def scroll_until_result_is_found(driver, human, expected_text):
    """Scroll down in human-sized steps until the exact result is present."""
    for _ in range(MAX_SCROLL_ATTEMPTS):
        result_link = find_exact_result_link(driver, expected_text)
        if result_link is not None:
            return result_link

        human.scroll_page(total_scroll=250, step_delay=0.25, direction="down")
        time.sleep(2)

    return find_exact_result_link(driver, expected_text)


def switch_to_g2_page(driver):
    """Switch to the G2 page whether Google opened it here or in a new tab."""
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "g2.com" in driver.current_url:
            return True
    return False


def close_login_modal_if_present(driver, human, timeout=1):
    """Close G2's login modal with the mouse when it appears."""
    try:
        modal = WebDriverWait(driver, timeout, poll_frequency=0.1).until(
            EC.visibility_of_element_located((By.ID, "login-modal"))
        )
    except TimeoutException:
        return False

    buttons = modal.find_elements(By.CSS_SELECTOR, "button")
    visible_buttons = [button for button in buttons if button.is_displayed()]
    if not visible_buttons:
        close_button = driver.find_element(By.XPATH, LOGIN_MODAL_CLOSE_XPATH)
    else:
        # The cross is the visible button nearest the modal's top-right corner.
        close_button = max(
            visible_buttons,
            key=lambda button: button.rect["x"] - button.rect["y"],
        )

    # Popup dismissal should be quick: short mouse move, tiny pause, click.
    actions = ActionChains(driver)
    actions.move_to_element(close_button).pause(0.05).click().perform()
    WebDriverWait(driver, 2, poll_frequency=0.1).until(
        EC.invisibility_of_element_located((By.ID, "login-modal"))
    )
    logger.info("Closed G2 login modal")
    return True


def click_one_random_show_more(driver, human, wait):
    """Choose exactly one Show More control from the available G2 buttons."""
    close_login_modal_if_present(driver, human, timeout=0.4)

    def show_more_buttons(current_driver):
        buttons = current_driver.find_elements(
            By.XPATH,
            '//button[.//*[@data-elv--accordion--show-more-controller-target="triggerText" '
            'and normalize-space()="Show More"]]',
        )
        return [
            button for button in buttons
            if button.is_displayed() and button.is_enabled()
        ]

    choices = wait.until(lambda current_driver: show_more_buttons(current_driver))
    button = random.choice(choices)
    controller = button.find_element(
        By.XPATH,
        './ancestor::*[contains(@data-controller, "elv--accordion--show-more-controller")][1]',
    )
    panels = controller.find_elements(
        By.CSS_SELECTOR, '[data-elv--accordion--show-more-controller-target="panel"]'
    )
    panel = panels[0] if panels else None
    initial_panel_height = panel.size["height"] if panel else 0

    def accordion_is_open(current_driver):
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

            panel_id = button.get_attribute("aria-controls") or button.get_attribute("aria_controls")
            if panel_id:
                current_panel = current_driver.find_element(By.ID, panel_id)
                if current_panel.get_attribute("aria-hidden") == "false":
                    return True
            if panel is not None and panel.size["height"] > initial_panel_height + 10:
                return True
        except Exception:
            return False
        return False

    human.mouse_hover(button)
    close_login_modal_if_present(driver, human, timeout=0.4)
    try:
        human.mouse_click_after_hover(button)
    except ElementClickInterceptedException:
        close_login_modal_if_present(driver, human, timeout=2)

    try:
        WebDriverWait(driver, 2, poll_frequency=0.1).until(accordion_is_open)
    except TimeoutException:
        # Keep the human mouse attempt first; use Selenium's reliable element
        # click only when G2 ignores that pointer event.
        close_login_modal_if_present(driver, human, timeout=2)
        button.click()
        try:
            WebDriverWait(driver, 2, poll_frequency=0.1).until(accordion_is_open)
        except TimeoutException:
            # Final fallback for G2's Stimulus controller. The earlier attempts
            # are real pointer/element clicks; this dispatches the same click
            # when G2 silently ignores WebDriver input.
            close_login_modal_if_present(driver, human, timeout=1)
            driver.execute_script("arguments[0].click();", button)
            try:
                WebDriverWait(driver, 2, poll_frequency=0.1).until(accordion_is_open)
            except TimeoutException:
                logger.warning("Show More clicked, but G2 did not expose expansion state; continuing")
                return

    logger.info("Clicked one randomly selected Show More button")


def follow_clicked_link(driver, wait, old_url, old_handles):
    """Follow a mouse-clicked link in either the current tab or a new tab."""
    def destination_opened(current_driver):
        new_handles = set(current_driver.window_handles) - old_handles
        if new_handles:
            current_driver.switch_to.window(next(iter(new_handles)))
            return current_driver.current_url != "about:blank"
        return current_driver.current_url != old_url

    wait.until(destination_opened)


def explore_top_rated_alternative(driver, human, wait):
    """Explore the supplied card with the mouse, then open its alternative."""
    close_login_modal_if_present(driver, human, timeout=0.4)
    section = wait.until(
        EC.presence_of_element_located((By.XPATH, TOP_RATED_SECTION_XPATH))
    )
    human.bring_element_into_view_with_wheel(section)
    human.move_mouse_around(moves=3)
    human.mouse_hover(section, hover_time=1.0)
    section_lines = section.text.strip().splitlines()
    heading = driver.find_elements(
        By.XPATH, '//*[@id="details"]//*[normalize-space(.)="Top-Rated Alternatives"]'
    )
    if heading:
        human.mouse_hover(heading[-1], hover_time=1.0)
        logger.info("Explored section: Top-Rated Alternatives")
    else:
        logger.info(
            f"Explored supplied card: {section_lines[0] if section_lines else 'unnamed'}"
        )

    alternative_label = wait.until(
        EC.presence_of_element_located((By.XPATH, ALTERNATIVE_LINK_XPATH))
    )
    alternative_link = alternative_label.find_element(By.XPATH, "./ancestor::a[1]")
    logger.info(f"Alternative: {alternative_link.text.strip()}")
    human.move_mouse_around(moves=2)
    human.mouse_hover(alternative_link, hover_time=1.0)
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    human.mouse_click_after_hover(alternative_link)
    follow_clicked_link(driver, wait, old_url, old_handles)
    logger.info(f"Opened alternative: {driver.current_url}")


def open_fifth_breadcrumb(driver, human, wait):
    """Click the fifth breadcrumb using mouse movement and mouse click."""
    close_login_modal_if_present(driver, human, timeout=0.4)
    breadcrumb_label = wait.until(
        EC.presence_of_element_located((By.XPATH, BREADCRUMB_XPATH))
    )
    breadcrumb_link = breadcrumb_label.find_element(By.XPATH, "./ancestor::a[1]")
    logger.info(f"Breadcrumb: {breadcrumb_link.text.strip()}")
    human.move_mouse_around(moves=2)
    human.mouse_hover(breadcrumb_link, hover_time=0.8)
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    human.mouse_click_after_hover(breadcrumb_link)
    follow_clicked_link(driver, wait, old_url, old_handles)
    logger.info(f"Opened breadcrumb: {driver.current_url}")


def run():
    logger.info("G2 Sauce Labs automation started")
    options = uc.ChromeOptions()
    options.add_argument("window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=152)

    try:
        logger.info("Opening Google")
        driver.get("https://www.google.com")

        # Selenium wheel actions scroll the page through mouse-wheel events;
        # OS-level wheel events were not advancing this G2 page reliably.
        human = HumanSimulator(driver)
        human.input_search_query(SEARCH_QUERY)
        logger.info("Google search submitted")

        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href] h3")))

        result_link = scroll_until_result_is_found(driver, human, TARGET_TEXT)
        if result_link is None:
            raise RuntimeError(f"Could not find the exact Google result: {TARGET_TEXT}")

        human.move_mouse_around(moves=2)
        human.mouse_hover(result_link, hover_time=1.2)
        human.mouse_click_after_hover(result_link)
        wait.until(switch_to_g2_page)
        logger.info(f"Opened result: {driver.current_url}")
        close_login_modal_if_present(driver, human)
        human.move_mouse_around(moves=3)

        click_one_random_show_more(driver, human, wait)
        close_login_modal_if_present(driver, human, timeout=0.4)
        selected_text = human.select_text_once()
        logger.info(f"Selected text once: {selected_text}")
        human.move_mouse_around(moves=2)
        explore_top_rated_alternative(driver, human, wait)
        close_login_modal_if_present(driver, human, timeout=0.4)
        open_fifth_breadcrumb(driver, human, wait)
        browsing = human.browse_g2_page()
        logger.info(f"Varied G2 browsing: {browsing}")
        time.sleep(10)
        logger.info("G2 Sauce Labs automation completed successfully")
    except Exception as error:
        logger.exception(f"G2 Sauce Labs automation failed: {error}")
        raise
    finally:
        driver.quit()
        logger.info("Browser closed")


if __name__ == "__main__":
    run()

