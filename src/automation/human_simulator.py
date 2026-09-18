import random
import time
import math
import re
import numpy as np
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.logging import logger


class HumanSimulator:
    def __init__(self, driver, use_native_cursor=False):
        """
        use_native_cursor: if True, attempts to use pyautogui to move the REAL
        OS mouse cursor (visible on screen) instead of Selenium's synthetic
        in-browser pointer events. Requires pyautogui + a working display
        (X server / DISPLAY set). Falls back to Selenium ActionChains if
        unavailable (e.g. headless server, no X display).
        """
        self.driver = driver
        self.current_x = 0
        self.current_y = 0
        self.use_native_cursor = False
        self.pyautogui = None

        if use_native_cursor:
            try:
                import pyautogui  # imported lazily - triggers mouseinfo/X connection
                self.pyautogui = pyautogui
                self.use_native_cursor = True
            except Exception as e:
                # Catches ImportError (not installed) AND runtime errors like
                # Xlib.error.DisplayConnectionError (no DISPLAY / headless env)
                print(f"Warning: native cursor mode unavailable ({type(e).__name__}: {e}). "
                      f"Falling back to Selenium ActionChains (no visible OS cursor movement).")

    # ---------- helper for safe gaussian sampling ----------

    def _gauss(self, mean, stdev, min_val=None, max_val=None):
        val = random.gauss(mean, stdev)
        if min_val is not None:
            val = max(val, min_val)
        if max_val is not None:
            val = min(val, max_val)
        return val

    # ---------- Core: human-like mouse path generation ----------

    def _bezier_curve(self, start, end, control_points=2, steps=30):
        points = [start]
        for _ in range(control_points):
            t = self._gauss(0.5, 0.15, 0.05, 0.95)
            mid_x = start[0] + (end[0] - start[0]) * t
            mid_y = start[1] + (end[1] - start[1]) * t
            offset_x = self._gauss(0, 20, -60, 60)
            offset_y = self._gauss(0, 20, -60, 60)
            points.append((mid_x + offset_x, mid_y + offset_y))
        points.append(end)

        curve = []
        for t in np.linspace(0, 1, steps):
            x, y = self._bezier_point(points, t)
            curve.append((x, y))
        return curve

    def _bezier_point(self, points, t):
        pts = points[:]
        while len(pts) > 1:
            pts = [
                ((1 - t) * pts[i][0] + t * pts[i + 1][0],
                 (1 - t) * pts[i][1] + t * pts[i + 1][1])
                for i in range(len(pts) - 1)
            ]
        return pts[0]

    def _ease_in_out(self, t):
        return t * t * (3 - 2 * t)

    # ---------- Dynamic timing calculators ----------

    def _dynamic_move_delay(self, distance, steps):
        total_duration = self._gauss(0.15 + distance * 0.0006, 0.05, 0.1, 1.5)
        per_step_mean = total_duration / max(steps, 1)
        return per_step_mean, per_step_mean * 0.3

    def _dynamic_click_delay(self):
        return self._gauss(0.12, 0.05, 0.02, 0.3)

    def _dynamic_hover_time(self, element=None):
        base_mean = 1.2
        if element is not None:
            try:
                area = element.size["width"] * element.size["height"]
                base_mean = min(1.0 + area / 40000, 3.0)
            except Exception:
                pass
        return self._gauss(base_mean, base_mean * 0.3, 0.3, 4.0)

    def _dynamic_typing_delay(self, char=None):
        base_mean = 0.13
        if char in (" ", ",", ".", "!", "?"):
            base_mean += 0.05
        return self._gauss(base_mean, 0.05, 0.03, 0.4)

    def _dynamic_think_pause(self):
        return self._gauss(0.5, 0.15, 0.2, 1.2)

    def _dynamic_scroll_step_delay(self):
        return self._gauss(0.25, 0.08, 0.05, 0.6)

    def _dynamic_scroll_amount(self, remaining):
        return int(self._gauss(120, 35, 30, min(220, max(remaining, 40))))

    def _dynamic_idle_pause(self):
        return self._gauss(0.9, 0.3, 0.2, 2.0)

    def _dynamic_drift_delay(self):
        return self._gauss(0.2, 0.06, 0.05, 0.4)

    # ---------- Scroll position helpers ----------

    def _get_scroll_state(self):
        return self.driver.execute_script(
            "return [document.documentElement.scrollTop || document.body.scrollTop, "
            "document.documentElement.scrollHeight, "
            "document.documentElement.clientHeight];"
        )

    def _can_scroll_down(self):
        scroll_top, scroll_height, client_height = self._get_scroll_state()
        return scroll_top + client_height < scroll_height - 5

    def _can_scroll_up(self):
        scroll_top, _, _ = self._get_scroll_state()
        return scroll_top > 5

    # ---------- Mouse movement ----------

    def _apply_screen_offset(self, browser_x, browser_y):
        win_pos = self.driver.get_window_position()
        toolbar_offset = 85  # approximate; calibrate for your OS/browser/zoom
        return win_pos["x"] + browser_x, win_pos["y"] + toolbar_offset + browser_y

    # def move_to_element_like_human(self, element, steps=None, step_delay=None):
    #     location = element.location_once_scrolled_into_view
    #     size = element.size
    #     end_x = location["x"] + size["width"] / 2 + self._gauss(0, 2, -5, 5)
    #     end_y = location["y"] + size["height"] / 2 + self._gauss(0, 2, -5, 5)

    #     start = (self.current_x, self.current_y)
    #     end = (end_x, end_y)
    #     distance = math.hypot(end_x - start[0], end_y - start[1])

    #     steps = steps if steps is not None else int(self._gauss(30, 6, 15, 60))
    #     control_points = int(self._gauss(2, 0.7, 1, 3))
    #     path = self._bezier_curve(start, end, control_points=control_points, steps=steps)

    #     if step_delay is None:
    #         delay_mean, delay_stdev = self._dynamic_move_delay(distance, steps)
    #     else:
    #         delay_mean, delay_stdev = step_delay, step_delay * 0.3

    #     if self.use_native_cursor:
    #         for i, (x, y) in enumerate(path):
    #             t = self._ease_in_out(i / max(len(path) - 1, 1))
    #             jitter_x = self._gauss(0, 0.6, -2, 2)
    #             jitter_y = self._gauss(0, 0.6, -2, 2)
    #             sx, sy = self._apply_screen_offset(x + jitter_x, y + jitter_y)
    #             self.pyautogui.moveTo(sx, sy, duration=0)
    #             step_time = delay_mean * (1.5 - abs(0.5 - t))
    #             time.sleep(self._gauss(step_time, delay_stdev, 0.001, None))
    #         self.current_x, self.current_y = path[-1]
    #     else:
    #         actions = ActionChains(self.driver)
    #         prev_x, prev_y = start
    #         for i, (x, y) in enumerate(path):
    #             t = self._ease_in_out(i / max(len(path) - 1, 1))
    #             jitter_x = self._gauss(0, 0.6, -2, 2)
    #             jitter_y = self._gauss(0, 0.6, -2, 2)
    #             dx = (x - prev_x) + jitter_x
    #             dy = (y - prev_y) + jitter_y
    #             actions.move_by_offset(dx, dy)
    #             prev_x, prev_y = x + jitter_x, y + jitter_y
    #             step_time = delay_mean * (1.5 - abs(0.5 - t))
    #             time.sleep(self._gauss(step_time, delay_stdev, 0.001, None))
    #         actions.perform()
    #         self.current_x, self.current_y = prev_x, prev_y
    
    def _scroll_element_into_view(self, element, settle_checks=3, settle_delay=0.05):
        """
        Scrolls the element to the center of the viewport (avoids sticky headers
        covering it) and waits for the scroll position to stop changing before
        proceeding - scrollIntoView can be async/animated in some browsers.
        """
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});",
            element
        )
        # Wait for scroll to settle (position stable across consecutive reads)
        last_scroll = None
        stable_count = 0
        for _ in range(20):  # hard cap to avoid infinite loop
            scroll_top = self.driver.execute_script(
                "return document.documentElement.scrollTop || document.body.scrollTop;"
            )
            if scroll_top == last_scroll:
                stable_count += 1
                if stable_count >= settle_checks:
                    break
            else:
                stable_count = 0
            last_scroll = scroll_top
            time.sleep(settle_delay)

    def _get_viewport_rect(self, element):
        """
        Returns the element's bounding box in VIEWPORT-relative coordinates
        (matches what ActionChains pointer movement uses), NOT document-relative
        coordinates (which is what element.location / location_once_scrolled_into_view
        returns - that mismatch was the root cause of clicks landing on the wrong
        on-screen element after scrolling).
        """
        rect = self.driver.execute_script(
            "var r = arguments[0].getBoundingClientRect();"
            "return {x: r.x, y: r.y, width: r.width, height: r.height};",
            element
        )
        return rect

    def _verify_pointer_target(self, x, y, expected_element):
        """
        Checks that the element actually under the cursor at (x, y) matches
        (or is contained within) the intended target, using elementFromPoint -
        the same viewport coordinate space. Returns True/False.
        """
        try:
            is_match = self.driver.execute_script(
                "var el = document.elementFromPoint(arguments[0], arguments[1]);"
                "return el === arguments[2] || arguments[2].contains(el);",
                x, y, expected_element
            )
            return bool(is_match)
        except Exception:
            return False  # can't verify, caller decides how to handle

    def move_to_element_like_human(self, element, steps=None, step_delay=None, verify=True):
        # Ensure element is scrolled into view and not hidden behind sticky headers,
        # and that the scroll has actually settled before we read coordinates.
        self._scroll_element_into_view(element)

        # Use viewport-relative coordinates (getBoundingClientRect), NOT
        # element.location / location_once_scrolled_into_view, which are
        # document-relative and drift from the visible pointer position once
        # the page has been scrolled.
        rect = self._get_viewport_rect(element)
        end_x = rect["x"] + rect["width"] / 2 + self._gauss(0, 2, -5, 5)
        end_y = rect["y"] + rect["height"] / 2 + self._gauss(0, 2, -5, 5)

        start = (self.current_x, self.current_y)
        end = (end_x, end_y)
        distance = math.hypot(end_x - start[0], end_y - start[1])

        steps = steps if steps is not None else int(self._gauss(30, 6, 15, 60))
        control_points = int(self._gauss(2, 0.7, 1, 3))
        path = self._bezier_curve(start, end, control_points=control_points, steps=steps)

        if step_delay is None:
            delay_mean, delay_stdev = self._dynamic_move_delay(distance, steps)
        else:
            delay_mean, delay_stdev = step_delay, step_delay * 0.3

        if self.use_native_cursor:
            for i, (x, y) in enumerate(path):
                t = self._ease_in_out(i / max(len(path) - 1, 1))
                jitter_x = self._gauss(0, 0.6, -2, 2)
                jitter_y = self._gauss(0, 0.6, -2, 2)
                sx, sy = self._apply_screen_offset(x + jitter_x, y + jitter_y)
                self.pyautogui.moveTo(sx, sy, duration=0)
                step_time = delay_mean * (1.5 - abs(0.5 - t))
                time.sleep(self._gauss(step_time, delay_stdev, 0.001, None))
            self.current_x, self.current_y = path[-1]
        else:
            # Sending dozens of queued pointer moves can make ChromeDriver's
            # local HTTP command hang until its 120-second timeout. Use one
            # real WebDriver pointer move with a small natural pause instead.
            self.driver.execute_script(
                "for (const type of ['mousemove','mouseover','mouseenter']) "
                "arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true}));",
                element,
            )
            time.sleep(self._gauss(0.18, 0.05, 0.08, 0.3))
            self.current_x, self.current_y = end

        # Sanity check: confirm the pointer actually landed on the intended
        # element. If not (e.g. an overlay/lazy-loaded element shifted things
        # mid-movement), re-sync coordinates once via a direct correction move.
        if verify and not self.use_native_cursor:
            if not self._verify_pointer_target(self.current_x, self.current_y, element):
                rect = self._get_viewport_rect(element)  # re-fetch in case layout shifted
                corrected_x = rect["x"] + rect["width"] / 2
                corrected_y = rect["y"] + rect["height"] / 2
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('mousemove', {bubbles:true}));",
                    element,
                )
                self.current_x, self.current_y = corrected_x, corrected_y
    # ---------- Public methods ----------

    def simulate_human_behavior(self, num_actions=None):
        num_actions = num_actions if num_actions is not None else int(self._gauss(2, 0.8, 1, 4))
        for _ in range(num_actions):
            action = random.choice([self.scroll_page, self._idle_pause, self._random_drift])
            action()

    def input_search_query(self, query, char_delay=None, think_pause=None, pre_submit_pause=None):

        def click_suggestion_box():
            try:
                required_words = input_query.lower().split()
                suggestions = []
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not suggestions:
                    candidates = self.driver.find_elements(
                        By.CSS_SELECTOR, 'ul[role="listbox"] li'
                    )
                    suggestions = [
                        suggestion for suggestion in candidates
                        if suggestion.is_displayed()
                        and suggestion.text.strip()
                        and all(
                            word in suggestion.text.strip().lower()
                            for word in required_words
                        )
                    ]
                    if not suggestions:
                        time.sleep(0.15)
                logger.info(f"{'-' * 10} Suggestion Box {'-' * 10}")
                if not suggestions:
                    return ""

                suggestion = random.choice(suggestions)
                sugg_used = suggestion.text.strip()
                logger.info(f"Suggestion using for this search {sugg_used}")
                previous_url = self.driver.current_url
                self.move_to_element_like_human(
                    suggestion, steps=10, step_delay=0.01
                )
                time.sleep(self._gauss(0.12, 0.03, 0.06, 0.2))
                suggestion.click()
                logger.info(f"{'-' * 10} Clicked {'-' * 10}")

                # Google can fill/highlight a suggestion without submitting it.
                # Confirm results appeared; otherwise submit with Enter.
                submitted = False
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if (
                        self.driver.current_url != previous_url
                        or self.driver.find_elements(By.CSS_SELECTOR, "a[href] h3")
                    ):
                        submitted = True
                        break
                    time.sleep(0.2)
                if not submitted:
                    search_box.send_keys(Keys.ENTER)
                    logger.info("Suggestion did not submit; pressed Enter")
                return sugg_used
            
            except Exception as e:
                logger.info(f"Default Search Input Useing due to {e}")
                return ""
            
        search_box = self.driver.find_element(By.NAME, "q")
        self.mouse_click(search_box)
        search_box.clear()
        # is_query_selection = random.choice([True , False])
        input_query = query
        logger.info(f"Query Used {input_query}")

        typo_positions = set()
        words = list(re.finditer(r"[A-Za-z]+", input_query))
        # Pick either one random word or None, so sometimes the full query is correct.
        selected_word = random.choice(words + [None]) if words else None
        if selected_word is not None:
            typo_positions.add(
                random.randrange(selected_word.start(), selected_word.end())
            )
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        logger.info(f"Typing with {len(typo_positions)} spelling mistakes")

        for index, char in enumerate(input_query):
            if index in typo_positions:
                wrong_char = random.choice(
                    [letter for letter in alphabet if letter != char.lower()]
                )
                search_box.send_keys(wrong_char.upper() if char.isupper() else wrong_char)
            else:
                search_box.send_keys(char)
            delay = char_delay if char_delay is not None else self._gauss(
                0.24 if char not in (" ", ",", ".", "!", "?") else 0.38,
                0.07,
                0.12,
                0.5,
            )
            time.sleep(delay)
            if random.random() < 0.03:
                pause = think_pause if think_pause is not None else self._dynamic_think_pause()
                time.sleep(pause)
        query_used = click_suggestion_box()
        if query_used:
            return query_used

        # No relevant suggestion appeared. Replace any typo and submit the
        # intended query so later polling waits for the correct result page.
        final_pause = pre_submit_pause if pre_submit_pause is not None else self._gauss(0.6, 0.2, 0.2, 1.5)
        time.sleep(final_pause)
        search_box.clear()
        for char in input_query:
            search_box.send_keys(char)
            time.sleep(self._gauss(0.18, 0.05, 0.09, 0.35))
        self.mouse_click(search_box)
        search_box.submit()
        return input_query

    def mouse_click(self, element, click_delay=None):
        self.move_to_element_like_human(element)
        delay = click_delay if click_delay is not None else self._dynamic_click_delay()
        time.sleep(delay)

        if self.use_native_cursor:
            self.pyautogui.click()
        else:
            element.click()

    def mouse_hover(self, element, hover_time=None):
        self.move_to_element_like_human(element)
        duration = hover_time if hover_time is not None else self._dynamic_hover_time(element)
        time.sleep(duration)

    def scroll_page(self, total_scroll=None, step_delay=None, direction=None):
        total_scroll = total_scroll if total_scroll is not None else int(self._gauss(700, 200, 200, 1400))

        current_direction = direction or random.choice(["down", "down", "up"])
        scrolled = 0

        while scrolled < total_scroll:
            can_down = self._can_scroll_down()
            can_up = self._can_scroll_up()

            if not can_down and not can_up:
                break

            if current_direction == "down" and not can_down:
                current_direction = "up"
            elif current_direction == "up" and not can_up:
                current_direction = "down"
            elif random.random() < 0.08:
                flip_to = "up" if current_direction == "down" else "down"
                if (flip_to == "up" and can_up) or (flip_to == "down" and can_down):
                    current_direction = flip_to

            step = self._dynamic_scroll_amount(total_scroll - scrolled)
            signed_step = step if current_direction == "down" else -step

            if self.use_native_cursor:
                self.pyautogui.scroll(-signed_step if current_direction == "down" else abs(signed_step))
            else:
                self.driver.execute_script(f"window.scrollBy(0, {signed_step});")

            scrolled += step
            delay = step_delay if step_delay is not None else self._dynamic_scroll_step_delay()
            time.sleep(delay)

    # ---------- Page exploration helpers ----------

    def bring_element_into_view_with_wheel(self, element):
        """Bring a requested element into view using the simulator's scrolling."""
        self._scroll_element_into_view(element)

    def mouse_click_after_hover(self, element):
        """Click an element that has already been reached and hovered."""
        time.sleep(self._gauss(0.4, 0.12, 0.2, 0.7))
        element.click()

    def move_mouse_around(self, moves=3):
        """Move the pointer through a few safe viewport positions."""
        width, height = self.driver.execute_script(
            "return [window.innerWidth, window.innerHeight];"
        )
        for _ in range(moves):
            x = random.randint(round(width * 0.25), round(width * 0.75))
            y = random.randint(round(height * 0.25), round(height * 0.75))
            self.driver.execute_script(
                "document.dispatchEvent(new MouseEvent('mousemove', "
                "{clientX:arguments[0], clientY:arguments[1], bubbles:true}));",
                x, y,
            )
            time.sleep(self._gauss(0.3, 0.08, 0.15, 0.5))
            self.current_x, self.current_y = x, y
            self._idle_pause()

    def _visible_reading_elements(self):
        elements = self.driver.find_elements(
            By.CSS_SELECTOR,
            "main p, main h1, main h2, main h3, "
            "#details p, .content-card p, article p, body p, body h1, body h2, body h3",
        )
        return self.driver.execute_script(
            "return arguments[0].filter(e => { const r=e.getBoundingClientRect(); "
            "const s=getComputedStyle(e); return r.width>0 && r.height>0 "
            "&& r.bottom>100 && r.top<innerHeight-30 "
            "&& s.display!=='none' && s.visibility!=='hidden'; });",
            elements,
        ) or []

    def select_random_words(self, count, already_selected=None):
        """Select distinct visible words with mouse double-clicks."""
        selected = []
        seen = {word.lower() for word in (already_selected or [])}
        for _ in range(count * 12):
            if len(selected) == count:
                return selected
            candidates = []
            for element in self._visible_reading_elements():
                for word in re.findall(r"[A-Za-z]{3,}", element.text):
                    if word.lower() not in seen:
                        candidates.append((element, word))
            if not candidates:
                break
            element, candidate = random.choice(candidates)
            self.mouse_hover(element)
            value = self.driver.execute_script(
                "const root=arguments[0], wanted=arguments[1];"
                "const walker=document.createTreeWalker(root, NodeFilter.SHOW_TEXT);"
                "let node; while(node=walker.nextNode()){"
                "const i=node.data.toLowerCase().indexOf(wanted.toLowerCase());"
                "if(i>=0){const r=document.createRange(); r.setStart(node,i);"
                "r.setEnd(node,i+wanted.length); const s=getSelection();"
                "s.removeAllRanges(); s.addRange(r); return s.toString();}} return '';",
                element,
                candidate,
            ) or ""
            words = re.findall(r"[A-Za-z]+", value)
            if len(words) == 1 and words[0].lower() not in seen:
                selected.append(words[0])
                seen.add(words[0].lower())
            time.sleep(self._gauss(2.0, 0.5, 1.0, 3.2))
        if len(selected) != count:
            logger.warning(
                f"Selected {len(selected)} of {count} requested words; continuing"
            )
        return selected

    def select_text_once(self):
        """Select one visible phrase containing either 4 or 10-20 words."""
        word_count = random.choice([4, random.randint(10, 20)])
        elements = self._visible_reading_elements()
        random.shuffle(elements)

        for element in elements:
            if len(re.findall(r"[A-Za-z]+", element.text)) < word_count:
                continue
            self.mouse_hover(element)
            selected_text = self.driver.execute_script(
                "const root=arguments[0], count=arguments[1];"
                "const walker=document.createTreeWalker(root, NodeFilter.SHOW_TEXT);"
                "const candidates=[]; let node;"
                "while(node=walker.nextNode()){"
                "const matches=[...node.data.matchAll(/[A-Za-z]+/g)];"
                "if(matches.length>=count) candidates.push([node,matches]);}"
                "if(!candidates.length) return '';"
                "const pair=candidates[Math.floor(Math.random()*candidates.length)];"
                "const maxStart=pair[1].length-count;"
                "const start=Math.floor(Math.random()*(maxStart+1));"
                "const first=pair[1][start], last=pair[1][start+count-1];"
                "const range=document.createRange();"
                "range.setStart(pair[0],first.index);"
                "range.setEnd(pair[0],last.index+last[0].length);"
                "const selection=getSelection(); selection.removeAllRanges();"
                "selection.addRange(range); return selection.toString();",
                element,
                word_count,
            ) or ""
            if len(re.findall(r"[A-Za-z]+", selected_text)) == word_count:
                time.sleep(self._gauss(2.5, 0.6, 1.5, 4))
                return selected_text

        logger.warning(f"Could not select one visible {word_count}-word phrase")
        return ""

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
                self.mouse_hover(image)
                self.mouse_click_after_hover(image)
                time.sleep(self._gauss(5, 1, 3, 8))
                image_clicked = True
                actions.append("image")
            elif readable:
                element = random.choice(readable)
                self.mouse_hover(element)
                time.sleep(self._gauss(4, 1, 2, 7))
                actions.append("read")
            else:
                self.move_mouse_around(1)
                actions.append("wander")
        return {"seconds": round(duration), "actions": actions, "picture_clicked": image_clicked}

    # ---------- Internal helpers ----------

    def _idle_pause(self, duration=None):
        time.sleep(duration if duration is not None else self._dynamic_idle_pause())

    def _random_drift(self, delay=None):
        dx, dy = self._gauss(0, 10, -25, 25), self._gauss(0, 10, -25, 25)
        if self.use_native_cursor:
            sx, sy = self._apply_screen_offset(self.current_x + dx, self.current_y + dy)
            self.pyautogui.moveTo(sx, sy, duration=0.1)
        else:
            self.driver.execute_script(
                "document.dispatchEvent(new MouseEvent('mousemove', {bubbles:true}));"
            )
        self.current_x += dx
        self.current_y += dy
        time.sleep(delay if delay is not None else self._dynamic_drift_delay())
