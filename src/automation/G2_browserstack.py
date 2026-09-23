"""Standalone BrowserStack review-page flow; kept separate from G2Page for now."""

import argparse
import random
import re
import time
from urllib.parse import urlsplit

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.automation.G2_page import G2Page
from src.automation.human_simulator import HumanSimulator
from src.commons import save_html
from src.logging import logger


def native_mouse(driver):
    human = getattr(driver, "_browserstack_human", None)
    if human is None or not human.use_native_cursor or human.pyautogui is None:
        raise RuntimeError("BrowserStack requires a working native mouse cursor")
    return human.pyautogui


def screen_point(driver, viewport_x, viewport_y, allow_path_overshoot=False):
    metrics = driver.execute_script(
        "return {x:screenX, y:screenY, chrome:outerHeight-innerHeight};"
    )
    point = (
        round(metrics["x"] + viewport_x),
        round(metrics["y"] + metrics["chrome"] + viewport_y),
    )
    desktop = native_mouse(driver).size()
    if allow_path_overshoot:
        # HumanSimulator's Bezier path can briefly curve just past an edge.
        # Keep those movement-only points away from PyAutoGUI's corner fail-safe.
        if not (-80 <= point[0] < desktop.width + 80
                and -80 <= point[1] < desktop.height + 80):
            raise RuntimeError(
                f"Native mouse path point {point} is too far outside desktop {desktop}"
            )
        return (
            min(max(point[0], 2), desktop.width - 3),
            min(max(point[1], 2), desktop.height - 3),
        )
    if not (0 <= point[0] < desktop.width and 0 <= point[1] < desktop.height):
        raise RuntimeError(
            f"Native mouse target {point} is outside the visible desktop {desktop}"
        )
    return point


def scroll_with_mouse(driver, pixels, area=None):
    mouse = native_mouse(driver)
    if area is None:
        viewport = driver.execute_script("return [innerWidth, innerHeight];")
        viewport_x, viewport_y = viewport[0] / 2, viewport[1] / 2
    else:
        point = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect();"
            "const left=Math.max(0,r.left), right=Math.min(innerWidth,r.right);"
            "const top=Math.max(0,r.top), bottom=Math.min(innerHeight,r.bottom);"
            "return right>left && bottom>top ? {x:(left+right)/2,y:(top+bottom)/2} : null;",
            area,
        )
        if point is None:
            raise RuntimeError("Reviews scroll area is outside the visible viewport")
        viewport_x, viewport_y = point["x"], point["y"]
    x, y = screen_point(driver, viewport_x, viewport_y)
    mouse.moveTo(x, y, duration=random.uniform(0.15, 0.3))
    before_y = driver.execute_script("return window.scrollY;")
    notches = max(2, min(6, round(abs(pixels) / 70)))
    wheel_tick = -1 if pixels > 0 else 1
    for _ in range(notches):
        mouse.scroll(wheel_tick)
        time.sleep(random.uniform(0.06, 0.14))
    time.sleep(0.2)

    after_y = driver.execute_script("return window.scrollY;")
    if after_y == before_y:
        viewport = driver.execute_script("return [innerWidth, innerHeight];")
        retry_x, retry_y = screen_point(
            driver, viewport[0] * 0.6, viewport[1] * 0.55
        )
        mouse.moveTo(retry_x, retry_y, duration=random.uniform(0.15, 0.3))
        for _ in range(notches + 1):
            mouse.scroll(wheel_tick)
            time.sleep(random.uniform(0.07, 0.15))
        time.sleep(0.2)


def wheel_to_element(driver, element):
    """Reach an element using the visible OS mouse wheel."""
    for _ in range(35):
        position = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect();"
            "return {middle:r.top+r.height/2, viewport:innerHeight};",
            element,
        )
        distance = position["middle"] - position["viewport"] * 0.5
        if abs(distance) < position["viewport"] * 0.3:
            return
        step = min(280, max(70, int(abs(distance))))
        scroll_with_mouse(driver, step if distance > 0 else -step)
        time.sleep(random.uniform(0.15, 0.35))
    raise RuntimeError("Could not reach page section with mouse-wheel scrolling")


def hover_with_mouse(driver, element, seconds=0.8):
    rect = driver.execute_script(
        "const r=arguments[0].getBoundingClientRect();"
        "return {x:r.x+r.width/2, y:r.y+r.height/2,"
        "width:innerWidth, height:innerHeight};", element
    )
    if not (0 < rect["x"] < rect["width"] and 0 < rect["y"] < rect["height"]):
        raise RuntimeError("Mouse target is outside the visible browser viewport")
    x, y = screen_point(driver, rect["x"], rect["y"])
    native_mouse(driver).moveTo(x, y, duration=random.uniform(0.25, 0.65))
    time.sleep(seconds)


def click_with_mouse(driver, element):
    hover_with_mouse(driver, element, random.uniform(0.2, 0.5))
    native_mouse(driver).click()


class BrowserStackHumanSimulator(HumanSimulator):
    """Use native cursor coordinates and wheel scrolling in shared helpers."""

    def _apply_screen_offset(self, browser_x, browser_y):
        return screen_point(self.driver, browser_x, browser_y, allow_path_overshoot=True)

    def _scroll_element_into_view(self, element, **_kwargs):
        wheel_to_element(self.driver, element)


def select_visible_phrase_with_mouse(driver, root, min_words=1, max_words=10):
    """Drag across one visible phrase without changing DOM selection via JS."""
    word_count = random.randint(min_words, max_words)
    points = driver.execute_script(
        "const root = arguments[0], count = arguments[1];"
        "const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);"
        "const candidates = []; let node;"
        "while ((node = walker.nextNode())) {"
        "  const parent = node.parentElement;"
        "  if (!parent || !parent.getClientRects().length) continue;"
        "  const words = [...node.data.matchAll(/[A-Za-z]+/g)];"
        "  if (words.length < count) continue;"
        "  for (let i = 0; i <= words.length - count; i++) {"
        "    const first=words[i], last=words[i+count-1];"
        "    const a=document.createRange(), b=document.createRange();"
        "    a.setStart(node, first.index); a.setEnd(node, first.index+1);"
        "    b.setStart(node, last.index+last[0].length-1);"
        "    b.setEnd(node, last.index+last[0].length);"
        "    const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();"
        "    if (ar.top>=80 && br.bottom<innerHeight-20 && ar.left>=0"
        "        && br.right<innerWidth) candidates.push({"
        "      startX:ar.left+1, startY:ar.top+ar.height/2,"
        "      endX:br.right-1, endY:br.top+br.height/2});"
        "  }"
        "}"
        "return candidates.length ? candidates[Math.floor(Math.random()*candidates.length)] : null;",
        root,
        word_count,
    )
    if not points:
        raise RuntimeError("No visible phrase available for mouse selection")

    mouse = native_mouse(driver)
    start_x, start_y = screen_point(driver, points["startX"], points["startY"])
    end_x, end_y = screen_point(driver, points["endX"], points["endY"])
    mouse.moveTo(start_x, start_y, duration=random.uniform(0.2, 0.4))
    mouse.mouseDown()
    try:
        time.sleep(random.uniform(0.15, 0.35))
        mouse.moveTo(end_x, end_y, duration=random.uniform(0.35, 0.7))
    finally:
        mouse.mouseUp()
    selected = driver.execute_script("return window.getSelection().toString();") or ""
    if not min_words <= len(re.findall(r"[A-Za-z]+", selected)) <= max_words:
        raise RuntimeError("Mouse drag did not select the requested phrase length")
    time.sleep(random.uniform(1.2, 2.5))
    return selected


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
        """Drag the mouse across one visible 1–10-word phrase."""
        return select_visible_phrase_with_mouse(self.driver, details)

    def explore(self):
        try:
            details = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, self.details_xpath))
            )
        except TimeoutException as error:
            raise RuntimeError(
                "BrowserStack details did not load; G2 may be showing a verification page"
            ) from error

        wheel_to_element(self.driver, details)
        hover_with_mouse(self.driver, details, 1.0)
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

        wheel_to_element(self.driver, button)
        hover_with_mouse(self.driver, button, 0.8)
        click_with_mouse(self.driver, button)
        try:
            WebDriverWait(self.driver, 3, poll_frequency=0.2).until(is_expanded)
        except TimeoutException:
            button = self.driver.find_element(By.XPATH, self.show_more_xpath).find_element(
                By.XPATH, "./ancestor::button[1]"
            )
            hover_with_mouse(self.driver, button, 0.5)
            click_with_mouse(self.driver, button)
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
        wheel_to_element(self.driver, section)
        WebDriverWait(self.driver, 5).until(lambda _: section.is_displayed())
        hover_with_mouse(self.driver, section, 1.0)
        logger.info("Scrolled to BrowserStack Integrations")
        time.sleep(random.uniform(2, 4))


class BrowserStackMedia:
    """Open one randomly chosen image from the BrowserStack Media carousel."""

    section_xpath = '//*[@id="details"]/div/div[2]/div/div[3]'

    def __init__(self, driver, human_simulator):
        self.driver = driver
        self.human_simulator = human_simulator

    def explore(self):
        section = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.section_xpath))
        )
        wheel_to_element(self.driver, section)
        hover_with_mouse(self.driver, section, 1.0)
        carousel = section.find_element(
            By.CSS_SELECTOR, '[data-media-carousel-target="mainCarousel"]'
        )

        # The supplied markup puts both arrows inside the main Swiper carousel.
        # Visit next and previous, then move to a randomly chosen nearby slide.
        directions = ["next", "prev"] + ["next"] * random.randint(1, 3)
        if random.random() < 0.5:
            directions.append(random.choice(["next", "prev"]))
        for direction in directions:
            controls = carousel.find_elements(By.CSS_SELECTOR, f".swiper-button-{direction}")
            if (not controls or controls[0].get_attribute("aria-disabled") == "true"
                    or "swiper-button-disabled" in (controls[0].get_attribute("class") or "")):
                continue
            control = controls[0]
            active = carousel.find_element(By.CSS_SELECTOR, ".swiper-slide-active")
            previous_id = active.get_attribute("data-media-id")
            wheel_to_element(self.driver, control)
            hover_with_mouse(self.driver, control, random.uniform(0.3, 0.7))
            click_with_mouse(self.driver, control)
            WebDriverWait(self.driver, 4, poll_frequency=0.2).until(
                lambda _: carousel.find_element(
                    By.CSS_SELECTOR, ".swiper-slide-active"
                ).get_attribute("data-media-id") != previous_id
            )
            logger.info(f"Clicked BrowserStack Media {direction} arrow")
            time.sleep(random.uniform(0.5, 1.2))

        def visible_images(_):
            images = carousel.find_elements(By.CSS_SELECTOR, ".swiper-slide-active img")
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
        wheel_to_element(self.driver, image)
        hover_with_mouse(self.driver, image, 0.8)
        # Video thumbnails have an SVG play icon over the <img>. A pointer click
        # at the tile's center reaches that visible overlay without interception.
        click_with_mouse(self.driver, image)
        logger.info("Clicked one random BrowserStack Media tile")
        view_seconds = random.uniform(5, 12)
        time.sleep(view_seconds)
        logger.info(f"Viewed BrowserStack Media image for {view_seconds:.1f} seconds")
        close_buttons = self.driver.find_elements(
            By.CSS_SELECTOR,
            '#cboxClose, .modal[aria-modal="true"] .modal-close',
        )
        for close_button in close_buttons:
            if close_button.is_displayed():
                hover_with_mouse(self.driver, close_button, 0.4)
                click_with_mouse(self.driver, close_button)
                logger.info("Closed BrowserStack Media viewer with mouse")
                break


class BrowserStackOfficialDownloads:
    """Expand the Official Downloads section with a mouse click."""

    section_xpath = '//*[@id="details"]/div/div[2]/div/div[3]/div[2]/div'
    show_more_xpath = (
        '//*[@id="details"]/div/div[2]/div/div[3]/div[2]/div/'
        'div[2]/div[2]/div'
    )

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        section = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.section_xpath))
        )
        wheel_to_element(self.driver, section)
        hover_with_mouse(self.driver, section, 1.0)
        control = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, self.show_more_xpath))
        )
        candidates = control.find_elements(
            By.XPATH,
            './/button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "show more")]'
            ' | .//a[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "show more")]',
        )
        target = candidates[0] if candidates else control
        before_length = len(section.text)
        wheel_to_element(self.driver, target)
        hover_with_mouse(self.driver, target, 0.7)
        click_with_mouse(self.driver, target)
        try:
            WebDriverWait(self.driver, 4, poll_frequency=0.2).until(
                lambda _: "show less" in section.text.lower()
                or len(section.text) > before_length + 10
                or target.get_attribute("aria-expanded") == "true"
            )
            logger.info("Expanded BrowserStack Official Downloads")
        except TimeoutException:
            logger.warning("Clicked Official Downloads Show More, but expansion was not confirmed")
        time.sleep(random.uniform(3, 5))


class BrowserStackReviews:
    """Briefly view the first review card and select one phrase."""

    heading_xpath = '//*[@id="reviews-and-filters"]/div/div[1]/div[1]'
    text_xpath = (
        '//*[@id="reviews-and-filters"]/div/div[1]/div[1]/div[2]/div/div[2]'
    )

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        heading = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.heading_xpath))
        )
        logger.info("Moving to BrowserStack Reviews section with mouse wheel")
        wheel_to_element(self.driver, heading)
        review_text = WebDriverWait(self.driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, self.text_xpath))
        )
        hover_time = random.uniform(0.4, 1.3)
        logger.info(f"Moving mouse over BrowserStack review text for {hover_time:.1f}s")
        hover_with_mouse(self.driver, review_text, hover_time)
        try:
            phrase = select_visible_phrase_with_mouse(
                self.driver,
                review_text,
                min_words=random.randint(1, 3),
                max_words=random.randint(5, 10),
            )
            logger.info(f"Mouse-selected BrowserStack review phrase: {phrase!r}")
        except RuntimeError as error:
            logger.warning(f"Could not select BrowserStack review phrase: {error}")
        logger.info("Finished brief BrowserStack Reviews view")


class BrowserStackReviewCard:
    """Visit one specific review and interact with it using the native mouse."""

    review_xpath = '//*[@id="browserstack-review-10504282"]'

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        review = WebDriverWait(self.driver, 12).until(
            EC.visibility_of_element_located((By.XPATH, self.review_xpath))
        )
        logger.info("Moving to targeted BrowserStack review with mouse wheel")
        wheel_to_element(self.driver, review)
        text_candidates = [
            element for element in review.find_elements(By.CSS_SELECTOR, "p, h3, h4, span")
            if element.is_displayed()
            and len(re.findall(r"[A-Za-z]+", element.text or "")) >= 4
            and self.driver.execute_script(
                "const r=arguments[0].getBoundingClientRect();"
                "return r.top<innerHeight-60 && r.bottom>60;", element
            )
        ]
        target = random.choice(text_candidates) if text_candidates else review
        hover_time = random.uniform(0.5, 1.5)
        logger.info(f"Moving mouse over random targeted review text for {hover_time:.1f}s")
        hover_with_mouse(self.driver, target, hover_time)
        phrase = select_visible_phrase_with_mouse(
            self.driver,
            target,
            min_words=random.randint(1, 4),
            max_words=random.randint(6, 10),
        )
        logger.info(f"Mouse-selected targeted review text: {phrase!r}")
        time.sleep(random.uniform(0.6, 1.8))


class BrowserStackReviewsScrollArea:
    """Read the reviews area with a varied native-mouse scroll pattern."""

    area_xpath = '//*[@id="reviews-and-filters"]/div/div[3]/div'

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        area = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, self.area_xpath))
        )
        logger.info("Found BrowserStack Reviews reading and scroll area")
        read_more = [
            element for element in area.find_elements(
                By.XPATH,
                './/*[self::button or self::a or @role="button"]'
                '[contains(translate(normalize-space(.), '
                '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), '
                '"read more")]',
            )
            if element.is_displayed()
        ]
        if read_more:
            target = random.choice(read_more)
            logger.info(f"Selected one Read More from {len(read_more)} available controls")
            logger.info("Moving to selected Read More with mouse wheel")
            wheel_to_element(self.driver, target)
            hover_time = random.uniform(0.4, 1.2)
            logger.info(f"Hovering over selected Read More for {hover_time:.1f}s")
            hover_with_mouse(self.driver, target, hover_time)
            pre_click_pause = random.uniform(0.3, 1.0)
            logger.info(f"Pausing {pre_click_pause:.1f}s before Read More click")
            time.sleep(pre_click_pause)
            click_with_mouse(self.driver, target)
            logger.info("Clicked one random review Read More with mouse")
            time.sleep(random.uniform(0.7, 1.8))
        else:
            logger.warning("No review Read More control was available")

        directions = []
        target_moves = random.randint(3, 6)
        while len(directions) < target_moves:
            directions.extend([1] * random.randint(1, 3))
            directions.extend([-1] * random.randint(1, 2))
        directions = directions[:target_moves]
        logger.info(f"Created random Reviews pattern with {target_moves} mouse scrolls")
        selection_step = (
            random.randrange(1, target_moves)
            if target_moves > 1 and random.random() < 0.55
            else None
        )

        for step_index, planned_direction in enumerate(directions, start=1):
            visible_text = [
                element for element in area.find_elements(By.CSS_SELECTOR, "p, h3, h4")
                if element.is_displayed()
                and len(re.findall(r"[A-Za-z]+", element.text or "")) >= 4
                and self.driver.execute_script(
                    "const r=arguments[0].getBoundingClientRect();"
                    "return r.top<innerHeight-80 && r.bottom>80;", element
                )
            ]
            if visible_text:
                reading_text = random.choice(visible_text)
                hover_time = random.uniform(0.4, 1.0)
                logger.info(
                    f"Moving mouse over random review text for {hover_time:.1f}s"
                )
                hover_with_mouse(
                    self.driver, reading_text, hover_time
                )
                if step_index == selection_step:
                    try:
                        phrase = select_visible_phrase_with_mouse(
                            self.driver,
                            reading_text,
                            min_words=random.randint(2, 4),
                            max_words=random.randint(6, 10),
                        )
                        logger.info(f"Mouse-selected random review text: {phrase!r}")
                    except RuntimeError as error:
                        logger.warning(f"Skipped random review text selection: {error}")
            reading_time = random.uniform(0.6, 1.6)
            logger.info(f"Reading visible review text for {reading_time:.1f}s")
            time.sleep(reading_time)
            bounds = self.driver.execute_script(
                "const r=arguments[0].getBoundingClientRect();"
                "return {top:r.top,bottom:r.bottom,height:innerHeight};", area
            )
            if bounds["top"] > 100:
                direction = 1
            elif bounds["bottom"] < bounds["height"] * 0.7:
                direction = -1
            else:
                direction = planned_direction
            distance = random.randint(110, 260)
            logger.info(
                f"Reviews mouse scroll {step_index}/{target_moves}: "
                f"{'down' if direction > 0 else 'up'} {distance}px"
            )
            scroll_with_mouse(
                self.driver,
                direction * distance,
                area=area,
            )
            time.sleep(random.uniform(0.2, 0.6))
        logger.info("Finished BrowserStack Reviews scroll pass")


class BrowserStackReviewsPagination:
    """Open one random numbered reviews page using the native mouse."""

    pagination_xpath = '//*[@id="reviews-and-filters"]/div/div[3]/div/div/ul'

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        pagination = WebDriverWait(self.driver, 15).until(
            EC.visibility_of_element_located((By.XPATH, self.pagination_xpath))
        )
        logger.info("Found BrowserStack Reviews pagination")
        logger.info("Moving to Reviews pagination with mouse wheel")
        wheel_to_element(self.driver, pagination)
        page_links = [
            link for link in pagination.find_elements(
                By.CSS_SELECTOR, "li.pagination__page-number a"
            )
            if link.is_displayed() and (link.text or "").strip().isdigit()
        ]
        if not page_links:
            logger.warning("No clickable numbered Reviews pages were available")
            return

        target = random.choice(page_links)
        page_number = (target.text or "").strip()
        logger.info(
            f"Randomly selected Reviews page {page_number} from {len(page_links)} pages"
        )
        hover_time = random.uniform(0.4, 1.2)
        logger.info(f"Hovering over Reviews page {page_number} for {hover_time:.1f}s")
        hover_with_mouse(self.driver, target, hover_time)
        old_url = self.driver.current_url
        click_with_mouse(self.driver, target)
        logger.info(f"Clicked Reviews page {page_number} with mouse")
        try:
            WebDriverWait(self.driver, 8, poll_frequency=0.2).until(
                lambda driver: driver.current_url != old_url
            )
            logger.info(f"Opened Reviews page {page_number}")
        except TimeoutException:
            logger.warning(f"Reviews page {page_number} navigation was not confirmed")
        view_time = random.uniform(1.5, 4.0)
        logger.info(f"Viewing Reviews page {page_number} for {view_time:.1f}s")
        time.sleep(view_time)
        logger.info(f"Finished viewing Reviews page {page_number}")


class TopRatedAlternatives:
    """Reach the Top-Rated Alternatives section using the native mouse wheel."""

    section_xpath = '//*[@id="additional_information"]/div/div[3]/div[1]/div[1]'

    def __init__(self, driver):
        self.driver = driver

    def explore(self):
        section = WebDriverWait(self.driver, 15).until(
            EC.visibility_of_element_located((By.XPATH, self.section_xpath))
        )
        logger.info("Found Top-Rated Alternatives section")
        logger.info("Scrolling to Top-Rated Alternatives with mouse wheel")
        wheel_to_element(self.driver, section)
        hover_time = random.uniform(0.4, 1.2)
        logger.info(f"Moving mouse over Top-Rated Alternatives for {hover_time:.1f}s")
        hover_with_mouse(self.driver, section, hover_time)
        logger.info("Reached Top-Rated Alternatives section")


class G2BrowserStack(G2Page):
    def __init__(self, driver, human_simulator):
        super().__init__(driver, human_simulator, "BrowserStack", "")
        self.search_query = "g2 browserstack"

    def close_login_modal_if_present(self, timeout=1):
        """Dismiss the G2 modal with the native mouse, if it appears."""
        try:
            modal = WebDriverWait(self.driver, timeout, poll_frequency=0.1).until(
                EC.visibility_of_element_located((By.ID, "login-modal"))
            )
        except TimeoutException:
            return False
        buttons = [
            button for button in modal.find_elements(By.CSS_SELECTOR, "button")
            if button.is_displayed()
        ]
        if not buttons:
            raise RuntimeError("G2 login modal has no visible close button")
        close_button = max(buttons, key=lambda button: button.rect["x"] - button.rect["y"])
        click_with_mouse(self.driver, close_button)
        WebDriverWait(self.driver, 3, poll_frequency=0.1).until(
            EC.invisibility_of_element_located((By.ID, "login-modal"))
        )
        logger.info("Closed G2 login modal with native mouse")
        return True

    def explore_reviews(self):
        """Run a random subset of review interactions in safe page order."""
        started_at = time.monotonic()
        target_duration = random.uniform(20, 40)
        logger.info(
            f"Random Reviews interaction target: {target_duration:.1f}s"
        )
        interactions = [
            ("BrowserStack Reviews", BrowserStackReviews(self.driver).explore),
            ("Targeted Review", BrowserStackReviewCard(self.driver).explore),
            ("Reviews Scroll Area", BrowserStackReviewsScrollArea(self.driver).explore),
            ("Reviews Pagination", BrowserStackReviewsPagination(self.driver).explore),
            ("Top-Rated Alternatives", TopRatedAlternatives(self.driver).explore),
        ]
        selected_count = random.randint(2, len(interactions))
        selected_indexes = set(
            random.sample(range(len(interactions)), selected_count)
        )
        selected_names = [
            name for index, (name, _) in enumerate(interactions)
            if index in selected_indexes
        ]
        logger.info(f"Randomly selected interaction classes: {selected_names}")

        for index, (name, action) in enumerate(interactions):
            if index not in selected_indexes:
                logger.info(f"Randomly skipped interaction class: {name}")
                continue
            logger.info(f"Starting interaction class: {name}")
            try:
                action()
                logger.info(f"Completed interaction class: {name}")
            except (RuntimeError, TimeoutException) as error:
                logger.warning(f"Skipped unavailable interaction class {name}: {error}")
        elapsed = time.monotonic() - started_at
        remaining = target_duration - elapsed
        if remaining > 0:
            logger.info(f"Reading final section for {remaining:.1f}s")
            time.sleep(remaining)
        logger.info(
            f"Completed randomized Reviews process in "
            f"{time.monotonic() - started_at:.1f}s"
        )

    def find_exact_result_link(self, expected_text):
        """Match BrowserStack's review result even if G2 changes the year."""
        exact = super().find_exact_result_link(expected_text)
        if exact is not None:
            return exact
        for heading in self.driver.find_elements(By.CSS_SELECTOR, "a[href] h3"):
            title = (heading.text or "").lower()
            if title.startswith("browserstack reviews") and "details" in title:
                return heading.find_element(By.XPATH, "./ancestor::a[1]")
        return None

    def scroll_until_result_is_found(self, expected_text):
        """Search Google results with mouse-wheel events only."""
        for _ in range(self.max_scroll_attempts + 1):
            self.wait_for_google_verification()
            result = self.find_exact_result_link(expected_text)
            if result is not None:
                wheel_to_element(self.driver, result)
                return result
            scroll_with_mouse(self.driver, random.randint(220, 380))
            time.sleep(random.uniform(0.8, 1.4))
        return None

    def wait_for_google_verification(self):
        if not urlsplit(self.driver.current_url).path.startswith("/sorry"):
            return
        logger.warning(
            "Google verification page opened. Complete it manually in Chrome "
            "within 90 seconds to continue."
        )
        try:
            WebDriverWait(self.driver, 90, poll_frequency=1).until(
                lambda driver: (
                    not urlsplit(driver.current_url).path.startswith("/sorry")
                    and bool(driver.find_elements(By.CSS_SELECTOR, "a[href] h3"))
                )
            )
        except TimeoutException as error:
            raise RuntimeError(
                "Google verification was not completed; no search results are available"
            ) from error

    def wait_for_g2_result(self, timeout=30):
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=0.3).until(
                lambda _: self.switch_to_g2_page()
            )
        except TimeoutException as error:
            locations = []
            for handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                parsed = urlsplit(self.driver.current_url)
                locations.append(f"{parsed.netloc}{parsed.path}")
            raise RuntimeError(
                f"Google result did not open G2; browser tabs: {locations}"
            ) from error

    def run(self):
        logger.info("G2 BrowserStack automation started")
        self.driver.get("https://www.google.com")
        self.human_simulator.input_search_query(self.search_query, suggestion=False)
        self.wait_for_google_verification()

        result = self.scroll_until_result_is_found(self.target_text)
        if result is None:
            titles = [
                heading.text.strip()
                for heading in self.driver.find_elements(By.CSS_SELECTOR, "a[href] h3")
            ]
            logger.warning(f"Google result titles seen: {titles[:8]}")
            parsed = urlsplit(self.driver.current_url)
            logger.warning(f"Google page location: {parsed.netloc}{parsed.path}")
            raise RuntimeError(f"Could not find Google result: {self.target_text}")

        hover_with_mouse(self.driver, result, 1.2)
        search_url = self.driver.current_url
        search_handles = set(self.driver.window_handles)
        click_with_mouse(self.driver, result)
        try:
            self.wait_for_g2_result(timeout=18)
        except RuntimeError:
            if (self.driver.current_url != search_url
                    or set(self.driver.window_handles) != search_handles):
                raise
            logger.warning("Google result click did not navigate; retrying mouse click once")
            hover_with_mouse(self.driver, result, 0.6)
            click_with_mouse(self.driver, result)
            self.wait_for_g2_result(timeout=18)
        logger.info(f"Opened result: {self.driver.current_url}")

        save_html(self.driver.page_source, "G2_BrowserStack")
        self.close_login_modal_if_present(timeout=0.4)
        BrowserStackReviewsProductDetails(
            self.driver, self.human_simulator
        ).explore()
        BrowserStackIntegrations(self.driver, self.human_simulator).explore()
        BrowserStackMedia(self.driver, self.human_simulator).explore()
        BrowserStackOfficialDownloads(self.driver).explore()
        self.explore_reviews()

    def run_reviews_only(self):
        """Development shortcut that opens and tests only the Reviews area."""
        logger.info("BrowserStack Reviews-only development run started")
        self.driver.get("https://www.g2.com/products/browserstack/reviews")
        self.close_login_modal_if_present(timeout=1)
        self.explore_reviews()


def run(reviews_only=False):
    options = uc.ChromeOptions()
    options.add_argument("window-size=1920,1080")
    options.add_argument("--incognito")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=options, version_main=152)
    try:
        human = BrowserStackHumanSimulator(driver, use_native_cursor=True)
        if not human.use_native_cursor:
            raise RuntimeError("Native mouse control is unavailable; BrowserStack run stopped")
        desktop = human.pyautogui.size()
        if desktop.width <= 0 or desktop.height <= 0:
            raise RuntimeError("No visible desktop is available for native mouse control")
        driver._browserstack_human = human
        logger.info("Native mouse cursor and wheel enabled")
        browserstack = G2BrowserStack(driver, human)
        if reviews_only:
            browserstack.run_reviews_only()
        else:
            browserstack.run()
        logger.info("G2 BrowserStack automation completed")
    except Exception as error:
        logger.exception(f"G2 BrowserStack automation failed: {error}")
        raise
    finally:
        driver.quit()
        logger.info("Browser closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reviews-only",
        action="store_true",
        help="Open G2 directly and test only the BrowserStack Reviews area",
    )
    args = parser.parse_args()
    run(reviews_only=args.reviews_only)
