import random
import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.automation.human_simulator import HumanSimulator


TARGET_TEXT = "Sauce Labs Reviews 2026: Details, Pricing, & Features"
SEARCH_QUERY = "g2 sauce labs"
MAX_SCROLL_ATTEMPTS = 4
TOP_RATED_SECTION_XPATH = '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]'
ALTERNATIVE_LINK_XPATH = (
    '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div[2]/a/div/span'
)
BREADCRUMB_XPATH = '//*[@id="breadcrumbs"]/li[5]/a/span'


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


def click_one_random_show_more(driver, human, wait):
    """Choose exactly one Show More control from the available G2 buttons."""
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
    human.mouse_hover(button)
    human.mouse_click_after_hover(button)
    wait.until(
        lambda current_driver: "Show Less" in button.text
        or button.get_attribute("aria-expanded") == "true"
    )
    print("Clicked one randomly selected Show More button")


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
        print("Explored section: Top-Rated Alternatives")
    else:
        print("Explored supplied card:", section_lines[0] if section_lines else "unnamed")

    alternative_label = wait.until(
        EC.presence_of_element_located((By.XPATH, ALTERNATIVE_LINK_XPATH))
    )
    alternative_link = alternative_label.find_element(By.XPATH, "./ancestor::a[1]")
    print("Alternative:", alternative_link.text.strip())
    human.move_mouse_around(moves=2)
    human.mouse_hover(alternative_link, hover_time=1.0)
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    human.mouse_click_after_hover(alternative_link)
    follow_clicked_link(driver, wait, old_url, old_handles)
    print("Opened alternative:", driver.current_url)


def open_fifth_breadcrumb(driver, human, wait):
    """Click the fifth breadcrumb using mouse movement and mouse click."""
    breadcrumb_label = wait.until(
        EC.presence_of_element_located((By.XPATH, BREADCRUMB_XPATH))
    )
    breadcrumb_link = breadcrumb_label.find_element(By.XPATH, "./ancestor::a[1]")
    print("Breadcrumb:", breadcrumb_link.text.strip())
    human.move_mouse_around(moves=2)
    human.mouse_hover(breadcrumb_link, hover_time=0.8)
    old_url = driver.current_url
    old_handles = set(driver.window_handles)
    human.mouse_click_after_hover(breadcrumb_link)
    follow_clicked_link(driver, wait, old_url, old_handles)
    print("Opened breadcrumb:", driver.current_url)


def run():
    options = uc.ChromeOptions()
    options.add_argument("window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, version_main=152)

    try:
        driver.get("https://www.google.com")

        # Selenium wheel actions scroll the page through mouse-wheel events;
        # OS-level wheel events were not advancing this G2 page reliably.
        human = HumanSimulator(driver)
        human.input_search_query(SEARCH_QUERY)

        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href] h3")))

        result_link = scroll_until_result_is_found(driver, human, TARGET_TEXT)
        if result_link is None:
            raise RuntimeError(f"Could not find the exact Google result: {TARGET_TEXT}")

        human.move_mouse_around(moves=2)
        human.mouse_hover(result_link, hover_time=1.2)
        human.mouse_click_after_hover(result_link)
        wait.until(switch_to_g2_page)
        print("Opened result:", driver.current_url)
        human.move_mouse_around(moves=3)

        total_words = random.choice([4, 5, 6, 9])
        first_count = random.randint(1, min(3, total_words - 2))
        second_count = random.randint(1, min(2, total_words - first_count - 1))
        final_count = total_words - first_count - second_count

        click_one_random_show_more(driver, human, wait)
        first_words = human.select_random_words(first_count)
        print("Mouse-selected on Sauce Labs page:", first_words)
        human.move_mouse_around(moves=2)
        explore_top_rated_alternative(driver, human, wait)
        second_words = human.select_random_words(second_count, already_selected=first_words)
        print("Mouse-selected on Alternatives page:", second_words)
        open_fifth_breadcrumb(driver, human, wait)
        final_words = human.select_random_words(
            final_count, already_selected=first_words + second_words
        )
        print("Mouse-selected after breadcrumb:", final_words)
        print("Total distinct words selected:", len(first_words + second_words + final_words))
        browsing = human.browse_g2_page()
        print("Varied G2 browsing:", browsing)
        time.sleep(10)
    finally:
        driver.quit()


if __name__ == "__main__":
    run()
