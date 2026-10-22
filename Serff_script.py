"""
=============================================================
SERFF FILING ACCESS AUTOMATION
State: Alabama
Browser: Selenium Chrome with a dedicated profile
=============================================================


"""

import logging
import json
import os
import re
import sys
import time
import shutil

from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait,Select
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    UnexpectedAlertPresentException,
)


# =============================================================
# CONFIGURATION
# =============================================================

BASE_URL = (
    "https://serff-sfa.naic.org/serff/sfa/home/AL"
)

START_DATE = "10/01/26"
END_DATE = "10/14/26"

ELEMENT_TIMEOUT = 30
PAGE_LOAD_TIMEOUT = 60
SEARCH_RESULT_TIMEOUT = 60
VERIFICATION_TIMEOUT = 300

# After clicking Download Zip File, monitor for 20 seconds, then continue
# to the next row even if the browser has not reported a completed file.
ZIP_DOWNLOAD_WAIT = 0
DOWNLOAD_MIN_WAIT = 20
DOWNLOAD_MAX_WAIT = 20
ROWS_PER_PAGE_VALUE = "100"
PROGRESS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serff_progress.json")
TABLE_DATA_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serff_table_data.json")

DOWNLOAD_DIR = os.path.expanduser("~/Downloads")

# Save the filing details page HTML from the same page where the ZIP button exists.
HTML_DOWNLOAD_DIR = os.path.join(BASE_DIR if "BASE_DIR" in globals() else os.path.dirname(os.path.abspath(__file__)), "serff_html_pages")
os.makedirs(HTML_DOWNLOAD_DIR, exist_ok=True)

# Existing Chrome profile.
SOURCE_CHROME_USER_DATA = os.path.expanduser(
    "~/Library/Application Support/Google/Chrome"
)

SOURCE_CHROME_PROFILE = "Default"

# Dedicated Selenium profile.
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

CHROME_USER_DATA = os.path.join(
    BASE_DIR,
    "serff_chrome_user_data"
)

CHROME_PROFILE = "Default"

LOG_FILE = os.path.join(
    BASE_DIR,
    "serff_automation.log"
)

SCREENSHOT_DIR = os.path.join(
    BASE_DIR,
    "serff_screenshots"
)

os.makedirs(
    SCREENSHOT_DIR,
    exist_ok=True
)


# =============================================================
# LOGGING CONFIGURATION
# =============================================================

logger = logging.getLogger("SERFF")

logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)


# =============================================================
# SCREENSHOT
# =============================================================

def save_screenshot(driver, step_name):
    """Save a screenshot for debugging."""

    if driver is None:
        return

    try:
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filepath = os.path.join(
            SCREENSHOT_DIR,
            f"{step_name}_{timestamp}.png"
        )

        driver.save_screenshot(filepath)

        logger.info(
            "Screenshot saved: %s",
            filepath
        )

    except Exception:
        logger.exception(
            "Unable to save screenshot."
        )


# =============================================================
# PAGE INFORMATION
# =============================================================

def log_page_information(driver):
    """Log current page URL and title."""

    try:
        logger.info(
            "Current URL: %s",
            driver.current_url
        )

        logger.info(
            "Page title: %s",
            driver.title
        )

    except WebDriverException:
        logger.exception(
            "Unable to read page information."
        )


# =============================================================
# WAIT FOR ELEMENT
# =============================================================

def wait_for_element(
    driver,
    locator,
    description,
    timeout=ELEMENT_TIMEOUT
):
    """Wait until an element is visible."""

    logger.info(
        "Waiting for element: %s",
        description
    )

    try:
        element = WebDriverWait(
            driver,
            timeout
        ).until(
            EC.visibility_of_element_located(locator)
        )

        logger.info(
            "Element visible: %s",
            description
        )

        return element

    except TimeoutException:
        logger.error(
            "Element not visible within %s seconds: %s",
            timeout,
            description
        )

        save_screenshot(
            driver,
            "element_timeout"
        )

        raise


# =============================================================
# CLICK ELEMENT
# =============================================================

def click_element(
    driver,
    locator,
    description,
    timeout=ELEMENT_TIMEOUT
):
    """Wait for an element to become clickable and click it robustly."""

    logger.info(
        "Waiting for clickable element: %s",
        description
    )

    element = WebDriverWait(
        driver,
        timeout
    ).until(
        EC.presence_of_element_located(locator)
    )

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
        element
    )
    time.sleep(0.5)

    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(locator)
        ).click()
        logger.info("Clicked successfully: %s", description)
    except WebDriverException:
        logger.warning(
            "Normal click failed for %s; trying JavaScript click.",
            description
        )
        element = WebDriverWait(
            driver, timeout
        ).until(EC.presence_of_element_located(locator))
        driver.execute_script("arguments[0].click();", element)
        logger.info("JavaScript click completed: %s", description)

    return element


# =============================================================
# CHROME PROFILE
# =============================================================

def prepare_selenium_profile():
    """
    Copy the existing Chrome Default profile to a dedicated
    Selenium profile so the original profile is not opened
    directly by WebDriver.
    """

    source_profile = os.path.join(
        SOURCE_CHROME_USER_DATA,
        SOURCE_CHROME_PROFILE
    )

    target_profile = os.path.join(
        CHROME_USER_DATA,
        CHROME_PROFILE
    )

    if os.path.isdir(target_profile):
        logger.info(
            "Existing Selenium profile will be reused: %s",
            target_profile
        )
        return

    if not os.path.isdir(source_profile):
        raise FileNotFoundError(
            "Chrome Default profile not found: "
            + source_profile
        )

    os.makedirs(
        CHROME_USER_DATA,
        exist_ok=True
    )

    source_local_state = os.path.join(
        SOURCE_CHROME_USER_DATA,
        "Local State"
    )

    target_local_state = os.path.join(
        CHROME_USER_DATA,
        "Local State"
    )

    if (
        os.path.isfile(source_local_state)
        and not os.path.exists(target_local_state)
    ):
        shutil.copy2(
            source_local_state,
            target_local_state
        )

    logger.info(
        "Copying Chrome Default profile. This may take some time."
    )

    shutil.copytree(
        source_profile,
        target_profile,
        ignore=shutil.ignore_patterns(
            "Singleton*",
            "lockfile",
            "LOCK",
            "*.sock",
            "Cache",
            "Code Cache",
            "GPUCache",
            "ShaderCache",
            "GrShaderCache",
            "DawnCache"
        )
    )

    logger.info(
        "Dedicated Selenium profile created."
    )


# =============================================================
# HUMAN VERIFICATION
# =============================================================

def is_verification_page(driver):
    """Detect a possible human-verification page."""

    try:
        title = driver.title.lower()
        url = driver.current_url.lower()
        source = driver.page_source.lower()

        return (
            "human verification" in title
            or (
                "useragreement.xhtml" in url
                and (
                    "let's confirm you are human" in source
                    or "complete the security check" in source
                )
            )
        )

    except WebDriverException:
        logger.exception(
            "Could not inspect verification page."
        )
        return False


def handle_verification(driver):
    """Wait for manual verification if required."""

    if not is_verification_page(driver):
        logger.info(
            "No human-verification page detected."
        )
        return True

    logger.warning(
        "Human verification detected. Complete it manually in Chrome."
    )

    save_screenshot(
        driver,
        "human_verification"
    )

    deadline = (
        time.monotonic()
        + VERIFICATION_TIMEOUT
    )

    while time.monotonic() < deadline:

        input(
            "Complete verification in Chrome, then press ENTER here: "
        )

        time.sleep(2)

        if not is_verification_page(driver):
            logger.info(
                "Verification completed."
            )
            return True

        logger.warning(
            "Verification is still detected."
        )

    logger.error(
        "Human-verification timeout reached."
    )

    return False


# =============================================================
# HANDLE BOOKMARKLET ALERT
# =============================================================

def handle_bookmarklet_alert(driver):
    """Accept a JavaScript confirmation alert if present."""

    try:
        alert = WebDriverWait(
            driver,
            5
        ).until(
            EC.alert_is_present()
        )

        logger.info(
            "JavaScript alert: %s",
            alert.text
        )

        alert.accept()

        logger.info(
            "Alert accepted."
        )

        return True

    except TimeoutException:
        logger.info(
            "No JavaScript alert detected."
        )

        return False



# =============================================================
# AUTOMATIC SEARCH FILTERS
# =============================================================

def apply_search_filters(driver):
    """
    Apply the requested filters directly on the SERFF search form:
    1. Business Type: select the third option (XPath option[3]).
    2. Type of Insurance: select items in order up to and including
       'LTC06 Long Term Care - Other'. Do not select later items.
    """

    # Business Type is a native select hidden behind a PrimeFaces widget.
    business_type_locator = (
        By.XPATH,
        '//select[@id="simpleSearch:businessType_input"]'
    )

    logger.info("FILTER: Selecting Business Type option[3].")
    business_select_element = WebDriverWait(
        driver, ELEMENT_TIMEOUT
    ).until(EC.presence_of_element_located(business_type_locator))

    Select(business_select_element).select_by_index(2)
    driver.execute_script(
        """
        arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """,
        business_select_element
    )
    logger.info(
        "FILTER: Business Type selected: %s",
        business_select_element.find_element(
            By.XPATH, './option[3]'
        ).text.strip()
    )
    time.sleep(3)

    # Open Type of Insurance checkbox menu.
    insurance_widget_locator = (
        By.XPATH,
        '//*[contains(@class,"ui-selectcheckboxmenu") '
        'and .//input[contains(@id,"typeOfInsurance") '
        'or contains(@name,"typeOfInsurance")]]'
    )
    insurance_dropdown_locator = (
        By.XPATH,
        '//*[contains(@class,"ui-selectcheckboxmenu")]'
        '[.//input[contains(@id,"typeOfInsurance") '
        'or contains(@name,"typeOfInsurance")]]'
        '//*[contains(@class,"ui-selectcheckboxmenu-trigger")]'
    )

    logger.info("FILTER: Opening Type of Insurance dropdown.")
    try:
        click_element(
            driver,
            insurance_dropdown_locator,
            "Type of Insurance dropdown",
            timeout=ELEMENT_TIMEOUT
        )
    except TimeoutException:
        # Fallback: locate the widget using its visible label and click it.
        fallback_widget = (
            By.XPATH,
            '//*[normalize-space(.)="Type of Insurance:"]'
            '/following::div[contains(@class,"ui-selectcheckboxmenu")][1]'
        )
        click_element(
            driver,
            fallback_widget,
            "Type of Insurance dropdown (label fallback)",
            timeout=ELEMENT_TIMEOUT
        )

    # Select list entries in displayed order, stopping at the target item.
    items_locator = (
        By.XPATH,
        '//div[contains(@class,"ui-selectcheckboxmenu-items-wrapper")]'
        '/ul/li'
    )
    target_text = "LTC06 Long Term Care - Other"

    WebDriverWait(driver, ELEMENT_TIMEOUT).until(
        EC.visibility_of_element_located(items_locator)
    )

    items = driver.find_elements(*items_locator)
    logger.info("FILTER: Found %s Type of Insurance list items.", len(items))

    target_index = None
    for index, item in enumerate(items):
        item_text = " ".join(item.text.split())
        if target_text.casefold() in item_text.casefold():
            target_index = index
            break

    if target_index is None:
        logger.error(
            "FILTER: Target insurance item '%s' was not found in the dropdown.",
            target_text
        )
        save_screenshot(driver, "insurance_target_not_found")
        raise RuntimeError(
            f"Type of Insurance target not found: {target_text}"
        )

    for index in range(target_index + 1):
        # Re-fetch each time because PrimeFaces may re-render the list.
        current_items = driver.find_elements(*items_locator)
        if index >= len(current_items):
            raise RuntimeError(
                f"Insurance list changed unexpectedly at item index {index}."
            )

        item = current_items[index]
        item_text = " ".join(item.text.split())

        # Scroll within the menu so each target item can be clicked.
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'nearest'});", item
        )
        time.sleep(0.15)

        classes = item.get_attribute("class") or ""
        if "ui-selectcheckboxmenu-checked" not in classes:
            try:
                item.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", item)

        logger.info(
            "FILTER: Selected insurance item %s/%s: %s",
            index + 1,
            target_index + 1,
            item_text
        )

    # Close the menu without changing the selected checkboxes.
    try:
        driver.find_element(By.TAG_NAME, "body").click()
    except WebDriverException:
        pass

    logger.info(
        "FILTER: Completed Type of Insurance selection through '%s'.",
        target_text
    )

# =============================================================
# DOWNLOAD FILE DETECTION
# =============================================================

def completed_download_files(download_dir):
    """
    Return completed files in the download directory.

    Ignore hidden files and common temporary download files.
    """

    folder = Path(download_dir)

    if not folder.is_dir():
        logger.warning(
            "Download directory does not exist: %s",
            download_dir
        )
        return set()

    temporary_suffixes = (
        ".crdownload",
        ".part",
        ".download",
        ".tmp"
    )

    files = set()

    for path in folder.iterdir():

        if not path.is_file():
            continue

        if path.name.startswith("."):
            continue

        if path.name.lower().endswith(
            temporary_suffixes
        ):
            continue

        files.add(
            str(path.resolve())
        )

    return files


# =============================================================
# WAIT FOR ZIP DOWNLOAD (FIXED 20-SECOND WINDOW)
# =============================================================

def wait_for_two_new_downloads(
    driver,
    baseline,
    row_number
):
    """Monitor downloads for 20 seconds, then allow the next row to run.

    The HTML has already been saved before the ZIP button is clicked.
    Do not block the whole automation waiting for two files: normally the
    ZIP action produces one file, and some downloads may take longer.
    """
    started = time.monotonic()
    deadline = started + DOWNLOAD_MAX_WAIT
    last_logged_second = -1

    logger.info(
        "ROW %s: Monitoring ZIP download for %s seconds.",
        row_number,
        DOWNLOAD_MAX_WAIT
    )
    logger.info("Download directory: %s", DOWNLOAD_DIR)

    new_files = []
    while True:
        elapsed = time.monotonic() - started
        current_files = completed_download_files(DOWNLOAD_DIR)
        new_files = sorted(current_files - baseline)
        elapsed_second = int(elapsed)

        # Keep logs readable: report every 5 seconds and at the end.
        if elapsed_second % 5 == 0 and elapsed_second != last_logged_second:
            logger.info(
                "ROW %s: %s/%s seconds elapsed; %s new completed file(s).",
                row_number, elapsed_second, DOWNLOAD_MAX_WAIT, len(new_files)
            )
            last_logged_second = elapsed_second

        if time.monotonic() >= deadline:
            break

        time.sleep(min(1, max(0, deadline - time.monotonic())))

    # Re-check once at the end of the monitoring window.
    new_files = sorted(completed_download_files(DOWNLOAD_DIR) - baseline)
    for filepath in new_files:
        logger.info("ROW %s: New completed download: %s", row_number, filepath)

    if new_files:
        logger.info(
            "ROW %s: Download monitoring finished; continuing after %s seconds.",
            row_number, DOWNLOAD_MAX_WAIT
        )
    else:
        logger.warning(
            "ROW %s: No completed new file detected within %s seconds. "
            "Continuing to the next row as requested; the ZIP may still be downloading.",
            row_number, DOWNLOAD_MAX_WAIT
        )

    return bool(new_files)


# =============================================================
# SEARCH RESULTS TABLE
# =============================================================

def result_rows_locator():
    """XPath for the SERFF results table rows."""

    return (
        By.XPATH,
        '//tbody[contains(concat(" ", normalize-space(@class), " "), '
        '" ui-datatable-data ")]/tr'
    )


def wait_for_search_table(
    driver,
    timeout=ELEMENT_TIMEOUT
):
    """Wait for at least one visible result row."""

    locator = result_rows_locator()

    logger.info(
        "Waiting for search results table rows."
    )

    WebDriverWait(
        driver,
        timeout
    ).until(
        lambda d: any(
            row.is_displayed()
            for row in d.find_elements(*locator)
        )
    )

    rows = [
        row
        for row in driver.find_elements(*locator)
        if row.is_displayed()
    ]

    logger.info(
        "Search results table contains %s visible row(s).",
        len(rows)
    )

    return rows


# =============================================================
# NEXT PAGE BUTTON
# =============================================================

def find_next_results_page_button(driver):
    """Find an enabled PrimeFaces next-page control."""

    xpath = (
        '//*[contains(@class,"ui-paginator-next") '
        'or contains(@class,"ui-icon-seek-next")]'
    )

    elements = driver.find_elements(
        By.XPATH,
        xpath
    )

    for element in elements:

        try:
            classes = (
                element.get_attribute("class") or ""
            )

            if (
                element.is_displayed()
                and element.is_enabled()
                and "ui-state-disabled" not in classes
            ):
                return element

        except WebDriverException:
            continue

    return None


# =============================================================
# PROCESS SEARCH RESULT ROWS
# =============================================================

def save_json_atomic(filepath, payload):
    """Write JSON safely using a temporary file then replace."""
    temp_path = filepath + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
    os.replace(temp_path, filepath)
    logger.info("JSON saved: %s", filepath)


def load_progress():
    """Load completed data-rk identifiers to support restart/resume."""
    if not os.path.isfile(PROGRESS_JSON):
        return {"completed_data_rk": [], "completed_count": 0, "updated_at": None}
    try:
        with open(PROGRESS_JSON, "r", encoding="utf-8") as file:
            data = json.load(file)
        data.setdefault("completed_data_rk", [])
        data.setdefault("completed_count", len(data["completed_data_rk"]))
        return data
    except (OSError, json.JSONDecodeError):
        logger.exception("Progress JSON could not be read; starting with a new progress state.")
        return {"completed_data_rk": [], "completed_count": 0, "updated_at": None}


def mark_completed(progress, data_rk, row_text, page_label):
    """Persist completion immediately after a row's workflow succeeds."""
    completed = set(progress.get("completed_data_rk", []))
    if data_rk not in completed:
        progress.setdefault("completed_data_rk", []).append(data_rk)
    progress["completed_count"] = len(progress["completed_data_rk"])
    progress["last_completed_data_rk"] = data_rk
    progress["last_completed_row_text"] = row_text
    progress["last_completed_page"] = page_label
    progress["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_json_atomic(PROGRESS_JSON, progress)


def select_100_rows_per_page(driver):
    """Select 100 in the SERFF 'Show' rows-per-page dropdown."""
    locator = (
        By.XPATH,
        '//select[@id="j_idt25:filingTable:j_id2"]'
    )
    logger.info("Selecting %s rows per page.", ROWS_PER_PAGE_VALUE)
    select_element = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
        EC.presence_of_element_located(locator)
    )
    driver.execute_script(
        "arguments[0].value = arguments[1];"
        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
        select_element, ROWS_PER_PAGE_VALUE
    )
    # PrimeFaces normally refreshes the table via AJAX after change.
    time.sleep(2)
    WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
        lambda d: d.find_elements(*result_rows_locator())
    )
    logger.info("Rows-per-page dropdown is now: %s", select_element.get_attribute("value"))


def get_page_label(driver):
    """Read the paginator text such as '(1 of 5)' when available."""
    candidates = driver.find_elements(
        By.XPATH,
        '//*[contains(@class,"ui-paginator-current") or contains(@class,"ui-paginator-pages")]'
    )
    for element in candidates:
        try:
            text = " ".join(element.text.split())
            if text and ("of" in text.lower() or text.isdigit()):
                if "of" in text.lower():
                    return text.strip("() ")
        except WebDriverException:
            pass

    # Fallback: inspect visible page text for the common paginator label.
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        match = re.search(r'\((\d+\s+of\s+\d+)\)', body_text, re.IGNORECASE)
        if match:
            return match.group(1)
    except WebDriverException:
        logger.exception("Could not read paginator label.")
    return "unknown"


def snapshot_current_table_page(driver, page_label, table_data):
    """
    Save all visible table rows before clicking any filing.
    Each record includes data-rk, page, row number and cell values.
    """
    rows = wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)
    page_key = page_label if page_label != "unknown" else f"page_{len(table_data) + 1}"
    page_records = []
    for index, row in enumerate(rows, start=1):
        cells = row.find_elements(By.XPATH, "./td")
        values = [" ".join(cell.text.split()) for cell in cells]
        page_records.append({
            "page": page_key,
            "row_number": index,
            "data_rk": row.get_attribute("data-rk"),
            "cells": values,
            "company_name": values[0] if len(values) > 0 else "",
            "naic_company_code": values[1] if len(values) > 1 else "",
            "insurance_product_name": values[2] if len(values) > 2 else "",
            "sub_type_of_insurance": values[3] if len(values) > 3 else "",
            "filing_type": values[4] if len(values) > 4 else "",
            "filing_status": values[5] if len(values) > 5 else "",
            "serff_tracking_number": values[6] if len(values) > 6 else "",
            "row_text": " | ".join(values),
        })

    table_data[page_key] = page_records
    save_json_atomic(TABLE_DATA_JSON, table_data)
    logger.info("Saved %s row(s) from table %s to JSON.", len(page_records), page_key)
    return page_records


def load_table_data():
    if not os.path.isfile(TABLE_DATA_JSON):
        return {}
    try:
        with open(TABLE_DATA_JSON, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        logger.exception("Table-data JSON could not be read; starting a new snapshot.")
        return {}



def save_current_page_html(driver, data_rk, row_number, page_label):
    """Save the current filing-details page HTML before clicking ZIP download."""
    try:
        os.makedirs(HTML_DOWNLOAD_DIR, exist_ok=True)

        # Use safe filename fragments so company/row text cannot break the path.
        safe_data_rk = re.sub(r"[^A-Za-z0-9_-]+", "_", str(data_rk or "unknown"))
        safe_page = re.sub(r"[^A-Za-z0-9_-]+", "_", str(page_label or "unknown"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"filing_page_{safe_page}_row_{row_number}_data-rk_{safe_data_rk}_{timestamp}.html"
        filepath = os.path.join(HTML_DOWNLOAD_DIR, filename)

        # Capture the page currently open in Selenium (the same page as the ZIP button).
        html_source = driver.page_source
        with open(filepath, "w", encoding="utf-8") as html_file:
            html_file.write(html_source)

        logger.info("ROW %s: Current filing page HTML saved: %s", row_number, filepath)
        logger.info("ROW %s: Saved HTML size: %s bytes", row_number, len(html_source.encode("utf-8")))
        return filepath

    except Exception:
        logger.exception("ROW %s: Failed to save current filing page HTML.", row_number)
        save_screenshot(driver, f"html_save_error_row_{row_number}")
        return None


def process_all_search_result_rows(driver):
    """
    Select 100 rows/page, snapshot each page to JSON, then process each
    unique data-rk. Resume safely using serff_progress.json. After a
    manual verification, refresh the current page and retry the same row.
    """
    rows_locator = result_rows_locator()
    return_locator = (By.XPATH, '//button[@id="j_idt20:j_idt24"]')
    download_zip_locator = (By.XPATH, '//button[@id="summaryForm:downloadLink"]')

    progress = load_progress()
    completed_keys = set(progress.get("completed_data_rk", []))
    table_data = load_table_data()
    processed_this_run = 0
    table_page = 1

    logger.info("=" * 70)
    logger.info("STARTING PAGINATED ROW-BY-ROW ZIP DOWNLOAD WORKFLOW")
    logger.info("Previously completed rows loaded from checkpoint: %s", len(completed_keys))
    logger.info("Filing details HTML output directory: %s", HTML_DOWNLOAD_DIR)
    logger.info("=" * 70)

    try:
        select_100_rows_per_page(driver)
    except Exception:
        logger.exception("Could not select 100 rows per page; continuing with current page size.")
        save_screenshot(driver, "rows_per_page_selection_error")

    while True:
        if not handle_verification(driver):
            logger.error("Verification was not completed; stopping with checkpoint saved.")
            return False

        rows = wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)
        page_label = get_page_label(driver)
        logger.info("CURRENT PAGINATOR LABEL: %s", page_label)
        page_records = snapshot_current_table_page(driver, page_label, table_data)

        # Rebuild the row list by data-rk for each attempt, as the table may re-render.
        for record in page_records:
            data_rk = record.get("data_rk")
            if not data_rk:
                logger.warning("Skipping row without data-rk: %s", record.get("row_text", ""))
                continue
            if data_rk in completed_keys:
                logger.info("Skipping already completed data-rk=%s", data_rk)
                continue

            row_number = progress.get("completed_count", 0) + 1
            row_text = record.get("row_text", "")
            retry_count = 0
            row_done = False

            while not row_done and retry_count < 3:
                retry_count += 1
                logger.info("=" * 70)
                logger.info("ROW %s | PAGE %s | data-rk=%s | attempt %s/3",
                            row_number, page_label, data_rk, retry_count)
                logger.info("ROW DATA: %s", row_text)

                try:
                    # Verification can appear between any two actions.
                    if is_verification_page(driver):
                        if not handle_verification(driver):
                            return False
                        driver.refresh()
                        wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)

                    row_locator = (
                        By.XPATH,
                        f'//tbody[@id="j_idt25:filingTable_data"]/tr[@data-rk="{data_rk}"]'
                    )
                    row = WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                        EC.presence_of_element_located(row_locator)
                    )
                    search_url = driver.current_url
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", row
                    )
                    time.sleep(0.5)
                    cells = row.find_elements(By.XPATH, "./td")

                    logger.info("Clicking table row data-rk=%s", data_rk)
                    try:
                        row.click()
                    except WebDriverException:
                        if not cells:
                            raise
                        driver.execute_script("arguments[0].click();", cells[0])

                    WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                        lambda d: d.current_url != search_url or bool(d.find_elements(*return_locator))
                    )
                    WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                        EC.presence_of_element_located(return_locator)
                    )
                    WebDriverWait(driver, ELEMENT_TIMEOUT).until(
                        EC.presence_of_element_located(download_zip_locator)
                    )
                    time.sleep(2)
                    log_page_information(driver)

                    # Save HTML from this exact filing-details page before clicking ZIP.
                    save_current_page_html(driver, data_rk, row_number, page_label)

                    baseline = completed_download_files(DOWNLOAD_DIR)
                    click_element(driver, download_zip_locator, "Download Zip File button")
                    # Monitor for 20 seconds total (no extra 30-second sleep).
                    # Then continue to the next row even if a completed file is not detected.
                    wait_for_two_new_downloads(driver, baseline, row_number)

                    driver.execute_script("window.scrollTo({top:0, behavior:'instant'});")
                    time.sleep(0.5)
                    click_element(driver, return_locator, "Return to Search Results button")
                    WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                        lambda d: "filingSearchResults.xhtml" in d.current_url
                    )
                    wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)

                    mark_completed(progress, data_rk, row_text, page_label)
                    completed_keys.add(data_rk)
                    processed_this_run += 1
                    row_done = True
                    logger.info("ROW COMPLETE. Total completed overall: %s; this run: %s",
                                len(completed_keys), processed_this_run)

                except Exception as exc:
                    logger.exception("Row failed for data-rk=%s", data_rk)
                    save_screenshot(driver, f"row_{data_rk}_error")

                    if is_verification_page(driver):
                        logger.warning("Verification detected after an error; waiting for manual completion.")
                        if not handle_verification(driver):
                            return False
                        try:
                            driver.refresh()
                            wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)
                            logger.info("Refreshed after verification; will retry same data-rk.")
                            continue
                        except Exception:
                            logger.exception("Could not recover after verification refresh.")

                    # If we landed on details, return to results before retrying.
                    if "filingSearchResults.xhtml" not in driver.current_url:
                        try:
                            driver.execute_script("window.scrollTo(0,0);")
                            click_element(driver, return_locator, "Return to Search Results button")
                            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                                lambda d: "filingSearchResults.xhtml" in d.current_url
                            )
                            wait_for_search_table(driver, timeout=PAGE_LOAD_TIMEOUT)
                        except Exception:
                            logger.exception("Could not return to results after row failure.")
                            if retry_count >= 3:
                                return False

                    if retry_count < 3:
                        logger.warning("Retrying same data-rk=%s after short wait.", data_rk)
                        time.sleep(3)
                    else:
                        logger.error("Row data-rk=%s failed 3 times; stopping to preserve resume position.", data_rk)
                        progress["stopped_at_data_rk"] = data_rk
                        progress["stopped_at_row_text"] = row_text
                        progress["updated_at"] = datetime.now().isoformat(timespec="seconds")
                        save_json_atomic(PROGRESS_JSON, progress)
                        return False

        # Find and click the enabled next-page button.
        page_before = get_page_label(driver)
        next_button = find_next_results_page_button(driver)
        if next_button is None:
            logger.info("No enabled next-page button. Last page reached (%s).", page_before)
            break

        first_row_before = ""
        current_rows = driver.find_elements(*rows_locator)
        if current_rows:
            first_row_before = current_rows[0].get_attribute("data-rk") or current_rows[0].text

        logger.info("Moving from table page %s to next page.", page_before)
        driver.execute_script("arguments[0].click();", next_button)

        try:
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                lambda d: get_page_label(d) != page_before
                or (
                    bool(d.find_elements(*rows_locator))
                    and (
                        (d.find_elements(*rows_locator)[0].get_attribute("data-rk")
                         or d.find_elements(*rows_locator)[0].text) != first_row_before
                    )
                )
            )
        except TimeoutException:
            logger.warning("Page transition was not detected; saving state and stopping safely.")
            save_screenshot(driver, "next_page_timeout")
            return False

        table_page += 1
        time.sleep(1)
        logger.info("Now on page label: %s", get_page_label(driver))

    logger.info("=" * 70)
    logger.info("ROW PROCESSING FINISHED. Newly processed: %s; completed overall: %s",
                processed_this_run, len(completed_keys))
    logger.info("Table snapshots: %s", TABLE_DATA_JSON)
    logger.info("Resume checkpoint: %s", PROGRESS_JSON)
    logger.info("=" * 70)
    return True
# MAIN AUTOMATION
# =============================================================

def run_automation():

    driver = None

    try:

        logger.info("=" * 70)
        logger.info(
            "SERFF AUTOMATION STARTED"
        )
        logger.info("=" * 70)

        # -----------------------------------------------------
        # STEP 1: PREPARE CHROME PROFILE
        # -----------------------------------------------------

        prepare_selenium_profile()

        options = webdriver.ChromeOptions()

        options.add_argument(
            f"--user-data-dir={CHROME_USER_DATA}"
        )

        options.add_argument(
            f"--profile-directory={CHROME_PROFILE}"
        )

        options.add_argument(
            "--start-maximized"
        )

        options.add_argument(
            "--no-first-run"
        )

        options.add_argument(
            "--no-default-browser-check"
        )

        logger.info(
            "STEP 1: Starting Chrome WebDriver."
        )

        driver = webdriver.Chrome(
            options=options
        )

        driver.set_page_load_timeout(
            PAGE_LOAD_TIMEOUT
        )

        logger.info(
            "Chrome WebDriver started successfully."
        )

        # -----------------------------------------------------
        # STEP 2: OPEN SERFF WEBSITE
        # -----------------------------------------------------

        logger.info(
            "STEP 2: Opening SERFF website."
        )

        try:
            driver.get(BASE_URL)

        except TimeoutException:
            logger.warning(
                "Initial navigation timed out. Checking current page."
            )

        time.sleep(2)

        log_page_information(driver)

        if not handle_verification(driver):
            logger.error(
                "Verification was not completed."
            )
            return

        # -----------------------------------------------------
        # STEP 3: BEGIN SEARCH
        # -----------------------------------------------------

        logger.info(
            "STEP 3: Clicking BEGIN SEARCH."
        )

        begin_locator = (
            By.XPATH,
            '//a[contains(concat(" ", normalize-space(@class), " "), '
            '" btn-success ")]'
        )

        begin_element = wait_for_element(
            driver,
            begin_locator,
            "BEGIN SEARCH link"
        )

        old_url = driver.current_url

        begin_element.click()

        try:
            WebDriverWait(
                driver,
                ELEMENT_TIMEOUT
            ).until(
                lambda d: d.current_url != old_url
            )

        except TimeoutException:
            logger.warning(
                "URL did not change after BEGIN SEARCH."
            )

        time.sleep(2)

        log_page_information(driver)

        if not handle_verification(driver):
            logger.error(
                "Verification was not completed after BEGIN SEARCH."
            )
            return

        # -----------------------------------------------------
        # STEP 4: ACCEPT
        # -----------------------------------------------------

        logger.info(
            "STEP 4: Clicking ACCEPT."
        )

        accept_locator = (
            By.XPATH,
            '//button[@id="j_idt18:j_idt20"]'
        )

        click_element(
            driver,
            accept_locator,
            "ACCEPT button"
        )

        if not handle_verification(driver):
            logger.error(
                "Verification was not completed after ACCEPT."
            )
            return

        # Wait for the search form.
        start_date_locator = (
            By.XPATH,
            '//input[@id="simpleSearch:submissionStartDate_input"]'
        )

        wait_for_element(
            driver,
            start_date_locator,
            "Start Submission Date input"
        )

        # -----------------------------------------------------

        # STEP 5: APPLY SEARCH FILTERS AUTOMATICALLY

        # -----------------------------------------------------

        logger.info(

            "STEP 5: Applying Business Type and Type of Insurance filters."

        )

        apply_search_filters(driver)

        # -----------------------------------------------------
        # STEP 6: START DATE
        # -----------------------------------------------------

        logger.info(
            "STEP 6: Entering start date %s.",
            START_DATE
        )

        start_input = wait_for_element(
            driver,
            start_date_locator,
            "Start Submission Date input"
        )

        start_input.clear()

        start_input.send_keys(
            START_DATE
        )

        actual_start = start_input.get_attribute(
            "value"
        )

        logger.info(
            "Start date field value: %s",
            actual_start
        )

        if actual_start != START_DATE:
            logger.error(
                "Start date validation failed."
            )

            save_screenshot(
                driver,
                "start_date_validation"
            )

            return

        # -----------------------------------------------------
        # STEP 7: END DATE
        # -----------------------------------------------------

        logger.info(
            "STEP 7: Entering end date %s.",
            END_DATE
        )

        end_date_locator = (
            By.XPATH,
            '//input[@id="simpleSearch:submissionEndDate_input"]'
        )

        end_input = wait_for_element(
            driver,
            end_date_locator,
            "End Submission Date input"
        )

        end_input.clear()

        end_input.send_keys(
            END_DATE
        )

        actual_end = end_input.get_attribute(
            "value"
        )

        logger.info(
            "End date field value: %s",
            actual_end
        )

        if actual_end != END_DATE:
            logger.error(
                "End date validation failed."
            )

            save_screenshot(
                driver,
                "end_date_validation"
            )

            return

        # -----------------------------------------------------
        # STEP 8: CLICK SEARCH
        # -----------------------------------------------------

        logger.info(
            "STEP 8: Clicking Search."
        )

        search_locator = (
            By.XPATH,
            '//button[@id="simpleSearch:saveBtn"]'
        )

        click_element(
            driver,
            search_locator,
            "Search button"
        )

        logger.info(
            "Search button clicked successfully."
        )

        # -----------------------------------------------------
        # STEP 9: WAIT, SCROLL, DETECT TABLE
        # -----------------------------------------------------

        logger.info(
            "STEP 9: Waiting for Search Results page to open."
        )

        try:
            WebDriverWait(
                driver,
                PAGE_LOAD_TIMEOUT
            ).until(
                lambda d: (
                    "filingSearchResults.xhtml"
                    in d.current_url
                )
            )

            logger.info(
                "STEP 9: Search Results page opened: %s",
                driver.current_url
            )

        except TimeoutException:
            logger.warning(
                "Results URL was not detected within %s seconds. "
                "Current URL: %s",
                PAGE_LOAD_TIMEOUT,
                driver.current_url
            )

        # The results page needs time to render.
        logger.info(
            "STEP 9: Waiting 5 seconds for page rendering."
        )

        time.sleep(5)

        log_page_information(driver)

        # Scroll to the bottom before looking for table rows.
        logger.info(
            "STEP 9: Scrolling down to reveal the results table."
        )

        driver.execute_script(
            """
            window.scrollTo(
                0,
                Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight
                )
            );
            """
        )

        logger.info(
            "STEP 9: Waiting 2 seconds after scrolling."
        )

        time.sleep(2)

        try:

            wait_for_search_table(
                driver,
                timeout=SEARCH_RESULT_TIMEOUT
            )

            logger.info(
                "STEP 9: Search results table detected."
            )

            rows = wait_for_search_table(
                driver,
                timeout=SEARCH_RESULT_TIMEOUT
            )

            if rows:

                logger.info(
                    "STEP 9: Scrolling first result row into view."
                )

                driver.execute_script(
                    """
                    arguments[0].scrollIntoView({
                        block: 'center',
                        behavior: 'instant'
                    });
                    """,
                    rows[0]
                )

                time.sleep(1)

            log_page_information(driver)

            save_screenshot(
                driver,
                "search_results_success"
            )

            logger.info(
                "STEP 9 COMPLETED: Table ready for row processing."
            )

        except TimeoutException:

            logger.error(
                "STEP 9: Search results table was not detected."
            )

            log_page_information(driver)

            try:

                logger.info(
                    "Visible tbody count: %s",
                    len(
                        driver.find_elements(
                            By.XPATH,
                            "//tbody"
                        )
                    )
                )

                logger.info(
                    "Page text preview: %s",
                    " ".join(
                        driver.find_element(
                            By.TAG_NAME,
                            "body"
                        ).text.split()
                    )[:1500]
                )

            except WebDriverException:

                logger.exception(
                    "Could not collect page diagnostics."
                )

            save_screenshot(
                driver,
                "search_results_timeout"
            )

            input(
                "Search table was not detected. Inspect Chrome and the "
                "saved screenshot. If the table is visible, press ENTER "
                "to retry detection; otherwise press CTRL+C to stop: "
            )

            # Retry detection after another scroll.
            driver.execute_script(
                """
                window.scrollTo(
                    0,
                    Math.max(
                        document.body.scrollHeight,
                        document.documentElement.scrollHeight
                    )
                );
                """
            )

            time.sleep(2)

            wait_for_search_table(
                driver,
                timeout=SEARCH_RESULT_TIMEOUT
            )

            logger.info(
                "STEP 9: Search results table detected on retry."
            )

            save_screenshot(
                driver,
                "search_results_retry_success"
            )

        # -----------------------------------------------------
        # STEP 10: PROCESS ALL RESULT ROWS
        # -----------------------------------------------------

        logger.info(
            "STEP 10: Starting row-by-row download workflow."
        )

        completed = process_all_search_result_rows(
            driver
        )

        if completed:
            logger.info(
                "All result rows processed."
            )

        else:
            logger.warning(
                "Workflow stopped before all rows were processed."
            )

        input(
            "\nPress ENTER to close the browser: "
        )

    except KeyboardInterrupt:

        logger.warning(
            "Automation interrupted by the user."
        )

    except UnexpectedAlertPresentException:

        logger.exception(
            "Unexpected JavaScript alert interrupted automation."
        )

        save_screenshot(
            driver,
            "unexpected_alert"
        )

    except Exception:

        logger.exception(
            "Automation failed."
        )

        save_screenshot(
            driver,
            "automation_failure"
        )

    finally:

        if driver:

            logger.info(
                "Closing Selenium browser."
            )

            try:
                driver.quit()

                logger.info(
                    "Browser closed successfully."
                )

            except WebDriverException:
                logger.exception(
                    "Error while closing browser."
                )


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    run_automation()