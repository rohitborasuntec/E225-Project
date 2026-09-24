import random
import time
import math
import re
import numpy as np
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from src.logging import logger


# Defaults for chunked scrolling (can be overridden per call)
CHUNK_THRESHOLD_VIEWPORTS = 1.5
MAX_CHUNKS = 5


class HumanSimulator:
    def __init__(self, driver, use_native_cursor=True, verbose=False):
        """
        use_native_cursor: if True, drives the REAL OS mouse cursor via
        pyautogui (visible on screen). Requires pyautogui + a working
        display (X11 / macOS Accessibility / Windows). Falls back to
        Selenium's synthetic in-browser pointer events if unavailable.

        Call calibrate_screen_offset() right after construction to compute
        the correct viewport→screen coordinate mapping for your browser.
        """
        self.driver = driver
        self.current_x = 0
        self.current_y = 0
        self.use_native_cursor = False
        self.pyautogui = None
        self.verbose = verbose
        self._recent_signatures = []
        self._current_category = None
        # Overwritten by calibrate_screen_offset(). 85 is a rough default
        # for a typical Chrome on a 1080p display.
        self._toolbar_offset = 85

        if use_native_cursor:
            try:
                import pyautogui
                pyautogui.FAILSAFE = False  # don't abort on corner hits
                pyautogui.PAUSE = 0         # we handle our own delays
                screen_w, screen_h = pyautogui.size()
                if verbose:
                    print(
                        f"[HumanSimulator] pyautogui OK. "
                        f"Screen={screen_w}x{screen_h}"
                    )
                self.pyautogui = pyautogui
                self.use_native_cursor = True
            except Exception as e:
                print(
                    f"[HumanSimulator] Native cursor unavailable "
                    f"({type(e).__name__}: {e}). Falling back to ActionChains."
                )
        if verbose:
            mode = "native OS cursor" if self.use_native_cursor else "Selenium synthetic cursor"
            print(f"[HumanSimulator] Input mode: {mode}")

    # ==================================================================
    # CALIBRATION — compute the viewport→screen offset once
    # ==================================================================
    def calibrate_screen_offset(self, force_window_geometry=True):
        """
        Pin the browser to a known screen position and compute the offset
        between viewport coordinates (what Selenium returns) and absolute
        screen coordinates (what pyautogui needs).
        """
        if not self.use_native_cursor:
            return

        if force_window_geometry:
            try:
                self.driver.set_window_position(0, 0)
                self.driver.set_window_size(1280, 900)
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Window repositioning failed: {e}")

        try:
            win_pos = self.driver.get_window_position()
            chrome_height = self.driver.execute_script(
                "return window.outerHeight - window.innerHeight;"
            ) or 0
        except Exception as e:
            logger.warning(f"Calibration read failed: {e}")
            return

        # _toolbar_offset = top of the viewport in screen coords
        self._toolbar_offset = win_pos["y"] + chrome_height

        logger.info(
            f"[HumanSimulator] Calibrated: window_pos={win_pos}, "
            f"chrome_height={chrome_height}, "
            f"toolbar_offset={self._toolbar_offset}"
        )

        # Quick visual confirmation — cursor lands near viewport top-left
        try:
            self.pyautogui.moveTo(
                win_pos["x"] + 20,
                self._toolbar_offset + 20,
                duration=0.15,
            )
            time.sleep(0.1)
        except Exception:
            pass

    # ==================================================================
    # EXISTING HELPERS
    # ==================================================================
    def _gauss(self, mean, stdev, min_val=None, max_val=None):
        val = random.gauss(mean, stdev)
        if min_val is not None:
            val = max(val, min_val)
        if max_val is not None:
            val = min(val, max_val)
        return val

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

    def _dynamic_move_delay(self, distance, steps):
        total_duration = self._gauss(
            0.15 + distance * 0.0006, 0.05, 0.1, 1.5
        )
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

    # ---------- Mouse movement: viewport → screen mapping ----------
    def _apply_screen_offset(self, browser_x, browser_y):
        """
        Convert viewport (browser_x, browser_y) to absolute screen coords.
        _toolbar_offset already includes the window Y position, so we must
        NOT add win_pos['y'] again.
        """
        win_pos = self.driver.get_window_position()
        return (
            win_pos["x"] + browser_x,
            self._toolbar_offset + browser_y,
        )

    def _scroll_element_into_view(self, element, settle_checks=3, settle_delay=0.05):
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center', "
            "behavior: 'instant'});",
            element,
        )
        last_scroll = None
        stable_count = 0
        for _ in range(20):
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
        return self.driver.execute_script(
            "var r = arguments[0].getBoundingClientRect();"
            "return {x: r.x, y: r.y, width: r.width, height: r.height};",
            element,
        )

    def _verify_pointer_target(self, x, y, expected_element):
        try:
            is_match = self.driver.execute_script(
                "var el = document.elementFromPoint(arguments[0], arguments[1]);"
                "return el === arguments[2] || arguments[2].contains(el);",
                x, y, expected_element,
            )
            return bool(is_match)
        except Exception:
            return False

    # ==================================================================
    # PRIMARY MOUSE MOVE
    # ==================================================================
    def move_to_element_like_human(
        self, element, steps=None, step_delay=None, verify=True
    ):
        # Scroll element into view + wait for scroll to settle
        self._scroll_element_into_view(element)

        # Use viewport-relative coords for both modes
        rect = self._get_viewport_rect(element)
        end_x = rect["x"] + rect["width"] / 2 + self._gauss(0, 2, -5, 5)
        end_y = rect["y"] + rect["height"] / 2 + self._gauss(0, 2, -5, 5)

        start = (self.current_x, self.current_y)
        end = (end_x, end_y)
        distance = math.hypot(end_x - start[0], end_y - start[1])

        steps = steps if steps is not None else int(self._gauss(30, 6, 15, 60))
        control_points = int(self._gauss(2, 0.7, 1, 3))
        path = self._bezier_curve(
            start, end, control_points=control_points, steps=steps
        )

        if step_delay is None:
            delay_mean, delay_stdev = self._dynamic_move_delay(distance, steps)
        else:
            delay_mean, delay_stdev = step_delay, step_delay * 0.3

        if self.use_native_cursor:
            # ---------- NATIVE (visible) cursor path ----------
            win_pos = self.driver.get_window_position()
            for i, (x, y) in enumerate(path):
                t = self._ease_in_out(i / max(len(path) - 1, 1))
                jitter_x = self._gauss(0, 0.6, -2, 2)
                jitter_y = self._gauss(0, 0.6, -2, 2)
                sx = win_pos["x"] + x + jitter_x
                sy = self._toolbar_offset + y + jitter_y
                try:
                    self.pyautogui.moveTo(sx, sy, duration=0)
                except Exception as e:
                    logger.warning(
                        f"[HumanSimulator] Native cursor move unavailable: {e}. "
                        "Switching to ActionChains/DOM interaction."
                    )
                    self.use_native_cursor = False
                    self.pyautogui = None
                    break
                step_time = delay_mean * (1.5 - abs(0.5 - t))
                time.sleep(self._gauss(step_time, delay_stdev, 0.001, None))
            self.current_x, self.current_y = path[-1]
        else:
            # ---------- SYNTHETIC (invisible) path ----------
            self.driver.execute_script(
                "for (const type of ['mousemove','mouseover','mouseenter']) "
                "arguments[0].dispatchEvent(new MouseEvent(type, {bubbles:true}));",
                element,
            )
            time.sleep(self._gauss(0.18, 0.05, 0.08, 0.3))
            self.current_x, self.current_y = end

        # Pointer-target verification (only meaningful in synthetic mode)
        if verify and not self.use_native_cursor:
            if not self._verify_pointer_target(
                self.current_x, self.current_y, element
            ):
                rect = self._get_viewport_rect(element)
                corrected_x = rect["x"] + rect["width"] / 2
                corrected_y = rect["y"] + rect["height"] / 2
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('mousemove', "
                    "{bubbles:true}));",
                    element,
                )
                self.current_x, self.current_y = corrected_x, corrected_y

    # ==================================================================
    # PUBLIC METHODS
    # ==================================================================
    def simulate_human_behavior(self, num_actions=None):
        num_actions = (
            num_actions if num_actions is not None
            else int(self._gauss(2, 0.8, 1, 4))
        )
        for _ in range(num_actions):
            action = random.choice(
                [self.scroll_page, self._idle_pause, self._random_drift]
            )
            action()

    def input_search_query(
        self,
        query,
        char_delay=None,
        think_pause=None,
        pre_submit_pause=None,
        suggestion=True,
    ):
        # FIX: define input_query up front so click_suggestion_box can see it
        input_query = query

        def click_suggestion_box(search_box):
            try:
                # Google may autocorrect a deliberately mistyped query.
                # Requiring every original misspelled token to exist in the
                # suggestion makes the suggestion path fail unnecessarily.
                original_words = [
                    w.lower() for w in re.findall(r"[A-Za-z]+", input_query)
                ]
                suggestions = []
                deadline = time.monotonic() + 3

                while time.monotonic() < deadline and not suggestions:
                    candidates = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        'ul[role="listbox"] li, [role="option"]'
                    )

                    visible = []
                    for candidate in candidates:
                        try:
                            if candidate.is_displayed() and candidate.text.strip():
                                visible.append(candidate)
                        except Exception:
                            continue

                    # Prefer suggestions containing most of the original
                    # query words, but allow Google's corrected spelling.
                    scored = []
                    for candidate in visible:
                        candidate_text = candidate.text.strip().lower()
                        candidate_words = set(
                            re.findall(r"[A-Za-z]+", candidate_text)
                        )
                        score = sum(
                            1 for word in original_words
                            if word in candidate_words
                            or any(
                                len(word) >= 5
                                and (
                                    word[:4] == other[:4]
                                    or word[-4:] == other[-4:]
                                )
                                for other in candidate_words
                            )
                        )
                        scored.append((score, candidate))

                    if scored:
                        max_score = max(score for score, _ in scored)
                        suggestions = [
                            candidate for score, candidate in scored
                            if score == max_score
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
                self.mouse_click_after_hover(suggestion)
                logger.info(f"Clicked")
                
                # Google sometimes fills without submitting
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
        logger.info(f"Query Used {input_query}")

        typo_positions = set()
        words = list(re.finditer(r"[A-Za-z]+", input_query))
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
                search_box.send_keys(
                    wrong_char.upper() if char.isupper() else wrong_char
                )
            else:
                search_box.send_keys(char)
            delay = (
                char_delay
                if char_delay is not None
                else self._gauss(
                    0.24 if char not in (" ", ",", ".", "!", "?") else 0.38,
                    0.07, 0.12, 0.5,
                )
            )
            time.sleep(delay)
            if random.random() < 0.03:
                pause = (
                    think_pause
                    if think_pause is not None
                    else self._dynamic_think_pause()
                )
                time.sleep(pause)

        if suggestion:
            query_used = click_suggestion_box(search_box)
            if query_used:
                return query_used

        # No usable suggestion — retype exact query and submit
        final_pause = (
            pre_submit_pause
            if pre_submit_pause is not None
            else self._gauss(0.6, 0.2, 0.2, 1.5)
        )
        time.sleep(final_pause)
        search_box.clear()
        for char in input_query:
            search_box.send_keys(char)
            time.sleep(self._gauss(0.18, 0.05, 0.09, 0.35))
        self.mouse_click(search_box)
        search_box.submit()
        return input_query

    def mouse_click(self, element, click_delay=None):
        """Move the cursor onto element, then click."""
        self.move_to_element_like_human(element)
        delay = (
            click_delay
            if click_delay is not None
            else self._dynamic_click_delay()
        )
        time.sleep(delay)

        if self.use_native_cursor:
            try:
                self.pyautogui.click()
                return
            except Exception as e:
                logger.debug(f"pyautogui.click failed: {e}; falling back to element.click()")

        element.click()

    def mouse_hover(self, element, hover_time=None):
        self.move_to_element_like_human(element)
        duration = (
            hover_time
            if hover_time is not None
            else self._dynamic_hover_time(element)
        )
        time.sleep(duration)

    def scroll_page(self, total_scroll=None, step_delay=None, direction=None):
        total_scroll = (
            total_scroll if total_scroll is not None
            else int(self._gauss(700, 200, 200, 1400))
        )

        current_direction = direction or random.choice(["down", "down", "up"])
        scrolled = 0

        # Cache the viewport center for the native-cursor branch
        if self.use_native_cursor:
            win = self.driver.get_window_rect()
            cx = win["x"] + win["width"] // 2
            cy = self._toolbar_offset + (win["height"] // 2)

        while scrolled < total_scroll:
            can_down = self._can_scroll_down()
            can_up = self._can_scroll_up()

            if not can_down and not can_up:
                break

            # Direction arbitration
            if current_direction == "down" and not can_down:
                current_direction = "up"
            elif current_direction == "up" and not can_up:
                current_direction = "down"
            elif random.random() < 0.08:
                flip_to = "up" if current_direction == "down" else "down"
                if (flip_to == "up" and can_up) or (
                    flip_to == "down" and can_down
                ):
                    current_direction = flip_to

            step = self._dynamic_scroll_amount(total_scroll - scrolled)
            signed_step = step if current_direction == "down" else -step

            if self.use_native_cursor:
                try:
                    # pyautogui: + = up, - = down.  signed_step: + = down.
                    self.pyautogui.moveTo(cx, cy, duration=0.1)
                    self.pyautogui.scroll(-signed_step)
                except Exception as e:
                    logger.debug(f"pyautogui.scroll failed: {e}")
                    self.driver.execute_script(
                        "window.scrollBy({top: arguments[0], left: 0, "
                        "behavior: 'smooth'});",
                        signed_step,
                    )
            else:
                self.driver.execute_script(
                    "window.scrollBy({top: arguments[0], left: 0, "
                    "behavior: 'smooth'});",
                    signed_step,
                )

            scrolled += step
            delay = (
                step_delay
                if step_delay is not None
                else self._dynamic_scroll_step_delay()
            )
            time.sleep(delay)

    # ==================================================================
    # PAGE EXPLORATION HELPERS
    # ==================================================================
    def bring_element_into_view_with_wheel(self, element):
        """Scroll element into view (JS scrollIntoView is fine here)."""
        self._scroll_element_into_view(element)

    def mouse_click_after_hover(self, element):
        """Click an element that was already hovered. Uses native click
        when available."""
        time.sleep(self._gauss(0.4, 0.12, 0.2, 0.7))
        if self.use_native_cursor:
            try:
                self.pyautogui.click()
                return
            except Exception as e:
                logger.debug(
                    f"pyautogui.click failed: {e}; falling back to element.click()"
                )
        element.click()

    def move_mouse_around(self, moves=3):
        """
        Move the cursor through a few random viewport positions.
        Uses the real OS cursor in native mode.
        """
        width, height = self.driver.execute_script(
            "return [window.innerWidth, window.innerHeight];"
        )
        win_pos = self.driver.get_window_position()

        for _ in range(moves):
            x = random.randint(round(width * 0.25), round(width * 0.75))
            y = random.randint(round(height * 0.25), round(height * 0.75))

            if self.use_native_cursor:
                # Animate with intermediate points for a natural sweep
                cur_x, cur_y = self.current_x, self.current_y
                steps = random.randint(8, 16)
                for i in range(1, steps + 1):
                    t = i / steps
                    ex = cur_x + (x - cur_x) * t + random.uniform(-3, 3)
                    ey = cur_y + (y - cur_y) * t + random.uniform(-3, 3)
                    try:
                        self.pyautogui.moveTo(
                            win_pos["x"] + ex,
                            self._toolbar_offset + ey,
                            duration=0,
                        )
                    except Exception:
                        break
                    time.sleep(random.uniform(0.008, 0.02))
                try:
                    self.pyautogui.moveTo(
                        win_pos["x"] + x,
                        self._toolbar_offset + y,
                        duration=0,
                    )
                except Exception:
                    pass
            else:
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
            "#details p, .content-card p, article p, body p, "
            "body h1, body h2, body h3",
        )
        return self.driver.execute_script(
            "return arguments[0].filter(e => { const r=e.getBoundingClientRect(); "
            "const s=getComputedStyle(e); return r.width>0 && r.height>0 "
            "&& r.bottom>100 && r.top<innerHeight-30 "
            "&& s.display!=='none' && s.visibility!=='hidden'; });",
            elements,
        ) or []

    def select_random_words(self, count, already_selected=None):
        """Select distinct visible words with the mouse (hover + JS Range)."""
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

            element, word = random.choice(candidates)
            self.mouse_hover(element)
            value = self.driver.execute_script(
                "const root=arguments[0], wanted=arguments[1];"
                "const walker=document.createTreeWalker(root, "
                "NodeFilter.SHOW_TEXT);"
                "let node; while(node=walker.nextNode()){"
                "const i=node.data.toLowerCase()"
                ".indexOf(wanted.toLowerCase());"
                "if(i>=0){const r=document.createRange(); r.setStart(node,i);"
                "r.setEnd(node,i+wanted.length); const s=getSelection();"
                "s.removeAllRanges(); s.addRange(r); return s.toString();}} "
                "return '';",
                element,
                word,
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
        """Select one visible phrase containing 4 or 10–20 words."""
        word_count = random.choice([4, random.randint(10, 20)])
        elements = self._visible_reading_elements()
        random.shuffle(elements)

        for element in elements:
            if len(re.findall(r"[A-Za-z]+", element.text)) < word_count:
                continue
            self.mouse_hover(element)
            selected_text = self.driver.execute_script(
                "const root=arguments[0], count=arguments[1];"
                "const walker=document.createTreeWalker(root, "
                "NodeFilter.SHOW_TEXT);"
                "const candidates=[]; let node;"
                "while(node=walker.nextNode()){"
                "const matches=[...node.data.matchAll(/[A-Za-z]+/g)];"
                "if(matches.length>=count) candidates.push([node,matches]);}"
                "if(!candidates.length) return '';"
                "const pair=candidates["
                "Math.floor(Math.random()*candidates.length)];"
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

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================
    def _idle_pause(self, duration=None):
        time.sleep(
            duration if duration is not None else self._dynamic_idle_pause()
        )

    def _random_drift(self, delay=None):
        dx = self._gauss(0, 10, -25, 25)
        dy = self._gauss(0, 10, -25, 25)

        if self.use_native_cursor:
            sx, sy = self._apply_screen_offset(
                self.current_x + dx, self.current_y + dy
            )
            try:
                self.pyautogui.moveTo(sx, sy, duration=0.1)
            except Exception:
                pass
        else:
            self.driver.execute_script(
                "document.dispatchEvent(new MouseEvent('mousemove', "
                "{bubbles:true}));"
            )

        self.current_x += dx
        self.current_y += dy
        time.sleep(
            delay if delay is not None else self._dynamic_drift_delay()
        )

    # ==================================================================
    # RANDOM XPATH BROWSING — POOL-BASED
    # ==================================================================
    def _viewport_state(self):
        try:
            return self.driver.execute_script(
                "return [window.pageYOffset, window.innerHeight, "
                "document.body.scrollHeight];"
            )
        except Exception:
            return 0, 800, 0

    def _element_rect(self, element):
        try:
            return self.driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return [r.top, r.bottom, r.height];",
                element,
            )
        except Exception:
            return None

    def is_element_fully_visible(self, element, margin=40):
        rect = self._element_rect(element)
        if not rect:
            return False
        top, bottom, _ = rect
        _, vh, _ = self._viewport_state()
        return top >= margin and bottom <= (vh - margin)

    def _element_signature(self, element):
        try:
            return self.driver.execute_script(
                """
                const el = arguments[0];
                const r = el.getBoundingClientRect();
                return (el.tagName + "|" + (el.className || "") + "|"
                        + Math.round(r.top) + "|"
                        + (el.innerText || "").slice(0, 40));
                """,
                element,
            )
        except Exception:
            return None

    def _remember_signature(self, signature, max_keep=25):
        if not signature:
            return
        self._recent_signatures.append(signature)
        if len(self._recent_signatures) > max_keep:
            self._recent_signatures.pop(0)

    def _is_recent_signature(self, signature):
        return signature in self._recent_signatures if signature else False

    def resolve_random_element(self, xpath_pool, category_weights=None):
        """
        xpath_pool: {category: [xpath, xpath, ...]}
        category_weights: {category: weight}
        Returns (category, element) or (None, None).
        """
        if not isinstance(xpath_pool, dict):
            logger.warning(
                "resolve_random_element: xpath_pool must be a dict; "
                f"got {type(xpath_pool).__name__}"
            )
            return None, None

        categories = [
            c for c in xpath_pool.keys()
            if isinstance(c, (str, int, float, tuple))
        ]
        if not categories:
            return None, None

        if not isinstance(category_weights, dict):
            category_weights = {}

        # random.choices() requires finite, non-negative numeric weights.
        weights = []
        for category in categories:
            weight = category_weights.get(category, 1)
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = 1.0
            weights.append(max(0.0, weight))

        # random.choices() rejects an all-zero weight vector.
        if not any(weights):
            weights = [1.0] * len(categories)

        attempts = []
        for _ in range(4):
            attempts.append(
                random.choices(categories, weights=weights, k=1)[0]
            )
        shuffled = categories[:]
        random.shuffle(shuffled)
        attempts.extend(shuffled)

        seen = set()
        for category in attempts:
            if category in seen:
                continue
            seen.add(category)

            xpaths = xpath_pool[category][:]
            random.shuffle(xpaths)

            for xpath in xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                except Exception:
                    continue

                visible = []
                for el in elements:
                    try:
                        if not el.is_displayed():
                            continue
                    except Exception:
                        continue
                    sig = self._element_signature(el)
                    if self._is_recent_signature(sig):
                        continue
                    visible.append((el, sig))

                if visible:
                    el, sig = random.choice(visible)
                    self._remember_signature(sig)
                    return category, el

        return None, None

    def scroll_to_element_human(
        self,
        element,
        align="center",
        chunk_threshold_viewports=CHUNK_THRESHOLD_VIEWPORTS,
        max_chunks=MAX_CHUNKS,
    ):
        rect = self._element_rect(element)
        if not rect:
            return False

        top, bottom, height = rect
        scroll_y, vh, page_h = self._viewport_state()

        if self.is_element_fully_visible(element, margin=60):
            return True

        if align == "start":
            target_vp_offset = random.uniform(0.15, 0.25) * vh
        elif align == "end":
            target_vp_offset = random.uniform(0.70, 0.85) * vh
        else:
            target_vp_offset = random.uniform(0.40, 0.55) * vh

        delta = top - target_vp_offset
        max_scroll = max(0, page_h - vh)
        new_y = max(0, min(scroll_y + delta, max_scroll))
        delta = new_y - scroll_y

        if abs(delta) < 20:
            return True

        chunk_threshold = chunk_threshold_viewports * vh
        if abs(delta) > chunk_threshold:
            self._chunked_scroll_human(delta, vh, max_chunks)
        else:
            direction = "down" if delta > 0 else "up"
            self.scroll_page(
                total_scroll=abs(int(delta)), direction=direction
            )

        return True

    def _chunked_scroll_human(
        self, total_delta, viewport_height, max_chunks=MAX_CHUNKS
    ):
        direction = "down" if total_delta > 0 else "up"
        remaining = abs(total_delta)

        chunk_size_base = viewport_height * random.uniform(0.85, 1.15)
        num_chunks = min(
            max_chunks,
            max(2, int(remaining / chunk_size_base) + 1),
        )

        logger.debug(
            f"Chunked human scroll: total={int(total_delta)}px, "
            f"chunks={num_chunks}, dir={direction}"
        )

        for i in range(num_chunks):
            if remaining <= 0:
                break

            if i == num_chunks - 1:
                chunk = remaining
            else:
                chunk = min(
                    remaining, viewport_height * random.uniform(0.8, 1.2)
                )

            self.scroll_page(total_scroll=int(chunk), direction=direction)
            remaining -= chunk

            if remaining <= 0:
                break

            time.sleep(random.uniform(0.35, 0.9))

            if random.random() < 0.6:
                jitter = int(abs(random.gauss(45, 25)))
                self.scroll_page(total_scroll=jitter, direction=direction)

            if random.random() < 0.25:
                backtrack = int(abs(random.gauss(70, 30)))
                flip = "up" if direction == "down" else "down"
                self.scroll_page(total_scroll=backtrack, direction=flip)

    def random_glance_scroll(self):
        direction = random.choice(["up", "down"])
        distance = int(abs(random.gauss(180, 70)))
        scroll_y, vh, page_h = self._viewport_state()
        max_scroll = max(0, page_h - vh)

        if direction == "down":
            if scroll_y >= max_scroll - 10:
                return False
            distance = min(distance, max_scroll - scroll_y)
        else:
            if scroll_y <= 10:
                return False
            distance = min(distance, scroll_y)

        if distance < 40:
            return False

        self.scroll_page(total_scroll=distance, direction=direction)
        return True

    def hover_element_human(self, element):
        try:
            self.mouse_hover(element)
            return True
        except Exception as error:
            logger.debug(f"Human hover failed: {error}")
            try:
                self.driver.execute_script(
                    "for (const t of ['mouseover','mouseenter','mousemove']) "
                    "arguments[0].dispatchEvent("
                    "new MouseEvent(t, {bubbles:true}));",
                    element,
                )
                return True
            except Exception:
                return False

    def hover_jitter(self):
        try:
            self._random_drift()
        except Exception:
            pass

    def select_text_in_element(self, element, max_chars=180):
        """Select a random sub-range inside element (JS Range)."""
        try:
            ok = self.driver.execute_script(
                """
                const el = arguments[0];
                const walker = document.createTreeWalker(
                    el, NodeFilter.SHOW_TEXT, null
                );
                const nodes = [];
                let node;
                while ((node = walker.nextNode())) {
                    if (node.nodeValue && node.nodeValue.trim().length > 0) {
                        nodes.push(node);
                    }
                }
                if (nodes.length === 0) return false;

                const pick = nodes[Math.floor(Math.random() * nodes.length)];
                const len = pick.nodeValue.length;
                const start = Math.floor(
                    Math.random() * Math.max(1, len - 10)
                );
                const end = Math.min(
                    len, start + Math.min(arguments[1], len - start)
                );

                const range = document.createRange();
                range.setStart(pick, start);
                range.setEnd(pick, end);

                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                return true;
                """,
                element,
                max_chars,
            )
            if not ok:
                return False
            time.sleep(random.uniform(0.3, 0.8))
            self.clear_selection()
            return True
        except Exception:
            return False

    def clear_selection(self):
        try:
            self.driver.execute_script(
                "const s = window.getSelection(); if (s) s.removeAllRanges();"
            )
        except Exception:
            pass

    def safe_click(self, element):
        try:
            try:
                self.mouse_click(element)
            except Exception:
                self.driver.execute_script(
                    "arguments[0].click();", element
                )
            time.sleep(random.uniform(0.5, 1.2))
            return True
        except Exception as error:
            logger.debug(f"Click failed: {error}")
            return False

    def dwell_on_element(
        self, element, category, dwell_config=None, default_dwell=None
    ):
        cfg = dwell_config or {}
        default = default_dwell or (2.5, 5.0)
        value = cfg.get(category, default) if isinstance(cfg, dict) else default
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 2
        ):
            value = default

        try:
            min_d, max_d = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            min_d, max_d = default

        if min_d > max_d:
            min_d, max_d = max_d, min_d

        dwell = random.uniform(min_d, max_d)

        logger.debug(f"Dwell [{category}] {round(dwell, 2)}s")

        dwell_start = time.time()
        next_jitter = dwell_start + random.uniform(0.6, 1.2)

        while (time.time() - dwell_start) < dwell:
            now = time.time()

            if now >= next_jitter:
                self.hover_jitter()
                next_jitter = now + random.uniform(0.7, 1.5)

            if random.random() < 0.08:
                nudge = int(abs(random.gauss(40, 20)))
                direction = random.choice(["up", "down"])
                self.scroll_page(
                    total_scroll=nudge, direction=direction
                )

            if random.random() < 0.05:
                self.select_text_in_element(element)

            time.sleep(random.uniform(0.15, 0.35))

    def browse_page_randomly(
        self,
        duration=60,
        pool=None,
        chunk_threshold_viewports=CHUNK_THRESHOLD_VIEWPORTS,
        max_chunks=MAX_CHUNKS,
    ):
        """
        Full random browsing flow driven by a pool dict:
            pool = {
                "xpaths":   {category: [xpath,...]},
                "weights":  {category: int},
                "safe_click": {category,...},
                "dwell":    {category: (min,max)},
                "default_dwell": (min,max),
            }
        Returns an action_log dict.
        """
        if not pool or not pool.get("xpaths"):
            logger.warning("browse_page_randomly: empty pool; skipping.")
            return {"empty": 1}

        xpath_pool = pool["xpaths"]
        weights = pool.get("weights") or {}
        # Normalize optional pool configuration.  A few callers pass lists/tuples
        # here; converting them to sets/dicts prevents "list as a dict key"
        # failures later in the browsing loop.
        raw_safe_clicks = pool.get("safe_click") or ()
        if isinstance(raw_safe_clicks, dict):
            safe_clicks = set(raw_safe_clicks.keys())
        elif isinstance(raw_safe_clicks, (list, tuple, set, frozenset)):
            safe_clicks = set(
                item for item in raw_safe_clicks
                if isinstance(item, (str, int, float, tuple))
            )
        elif isinstance(raw_safe_clicks, str):
            safe_clicks = {raw_safe_clicks}
        else:
            safe_clicks = set()

        raw_dwell = pool.get("dwell") or {}
        if isinstance(raw_dwell, dict):
            dwell_cfg = {
                key: value for key, value in raw_dwell.items()
                if isinstance(key, (str, int, float, tuple))
            }
        else:
            dwell_cfg = {}

        default_d = pool.get("default_dwell") or (2.5, 5.0)
        if (
            not isinstance(default_d, (list, tuple))
            or len(default_d) != 2
        ):
            default_d = (2.5, 5.0)

        logger.info(f"Random XPath browsing for {duration}s...")
        start_time = time.time()

        def remaining():
            return max(0, duration - (time.time() - start_time))

        def time_available(seconds=1):
            return remaining() > seconds

        action_log = {
            "jump": 0, "chunked": 0, "hover": 0, "click": 0,
            "glance": 0, "select": 0, "no_scroll": 0,
            "empty": 0, "dwell": 0,
        }

        while time_available(2.0):
            category, element = self.resolve_random_element(
                xpath_pool, weights
            )

            if element is None:
                if self.random_glance_scroll():
                    action_log["glance"] += 1
                action_log["empty"] += 1
                time.sleep(random.uniform(0.3, 0.7))
                continue

            was_visible = self.is_element_fully_visible(
                element, margin=60
            )
            rect = self._element_rect(element)
            _, vh, _ = self._viewport_state()
            will_chunk = False
            if rect and not was_visible:
                est_delta = abs(rect[0] - (vh * 0.5))
                if est_delta > chunk_threshold_viewports * vh:
                    will_chunk = True

            align = random.choice(["start", "center", "center", "end"])
            if not self.scroll_to_element_human(
                element,
                align=align,
                chunk_threshold_viewports=chunk_threshold_viewports,
                max_chunks=max_chunks,
            ):
                continue

            if was_visible:
                action_log["no_scroll"] += 1
            elif will_chunk:
                action_log["chunked"] += 1
            else:
                action_log["jump"] += 1

            if not time_available(1.5):
                break

            if self.hover_element_human(element):
                action_log["hover"] += 1
                logger.debug(f"Hovered [{category}]")

            if not time_available(1.0):
                break

            roll = random.random()
            try:
                if category in safe_clicks and roll < 0.7:
                    if self.safe_click(element):
                        action_log["click"] += 1

                elif category in (
                    "review_cards", "review_body"
                ) and roll < 0.55:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1

                elif category == "ratings" and roll < 0.4:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1

                elif category == "reviewer_names" and roll < 0.35:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1

                elif category == "review_titles" and roll < 0.4:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1

                elif category == "headings" and roll < 0.3:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1

                elif category == "images" and roll < 0.25:
                    self.hover_element_human(element)
                    action_log["hover"] += 1

                elif category == "helpful_votes" and roll < 0.3:
                    if self.select_text_in_element(element):
                        action_log["select"] += 1
            except Exception as error:
                logger.debug(f"Interaction skipped: {error}")

            min_dwell = dwell_cfg.get(category, default_d)[0]
            if time_available(min_dwell + 0.5):
                self.dwell_on_element(
                    element, category, dwell_cfg, default_d
                )
                action_log["dwell"] += 1

            if random.random() < 0.22 and time_available(2):
                if self.random_glance_scroll():
                    action_log["glance"] += 1

            time.sleep(min(random.uniform(0.4, 1.0), remaining()))

        self.clear_selection()
        elapsed = time.time() - start_time
        logger.info(
            f"Browsing completed in {round(elapsed, 2)}s. "
            f"Summary: {action_log}"
        )
        return action_log