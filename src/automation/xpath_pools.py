"""
Central repository for all XPath pools used by human-like browsing.

Each pool is a self-contained bundle with:
    - xpaths:    {category: [xpath_fallbacks...]}
    - weights:   {category: int}          (optional, defaults to 1)
    - safe_click: set of categories where a click is allowed
    - dwell:     {category: (min_sec, max_sec)} (optional)
    - default_dwell: (min_sec, max_sec)

To use:
    from src.automation.xpath_pools import G2_COMPARISON_POOL
    human_simulator.browse_page_randomly(duration=60, pool=G2_COMPARISON_POOL)
"""

# ======================================================================
# G2 COMPARISON PAGE
# ======================================================================
G2_COMPARISON_POOL = {
    "xpaths": {
        "review_cards": [
            '//div[contains(@class,"review-card")]',
            '//div[@itemprop="review"]',
            '//div[contains(@class,"paper--white")]',
            '//div[contains(@class,"review")]',
        ],
        "ratings": [
            '//div[contains(@class,"rating")]',
            '//span[contains(@class,"stars")]',
            '//*[@itemprop="ratingValue"]',
            '//*[contains(@class,"star")]',
        ],
        "reviewer_names": [
            '//a[contains(@class,"reviewer")]',
            '//div[contains(@class,"user-name")]',
            '//span[@itemprop="author"]',
            '//div[contains(@class,"reviewer")]//a',
        ],
        "review_titles": [
            '//div[contains(@class,"review")]//h3',
            '//div[contains(@class,"review")]//h4',
            '//*[@itemprop="name"]',
        ],
        "review_body": [
            '//div[contains(@class,"review-content")]',
            '//div[contains(@class,"pros")]',
            '//div[contains(@class,"cons")]',
            '//*[@itemprop="reviewBody"]',
        ],
        "show_more_links": [
            '//a[contains(@class,"js-truncate") and contains(., "Show more")]',
            '//a[contains(text(),"Show more")]',
            '//a[contains(., "Show more")]',
        ],
        "show_less_links": [
            '//a[contains(@class,"js-truncate") and contains(., "Show less")]',
            '//a[contains(text(),"Show less")]',
            '//a[contains(., "Show less")]',
        ],
        "helpful_votes": [
            '//*[contains(., "Helpful")]',
            '//*[contains(@class,"helpful")]',
        ],
        "images": [
            '//div[contains(@class,"review")]//img',
            '//img[contains(@class,"avatar")]',
        ],
        "headings": [
            '//h2',
            '//h3',
            '//h4',
        ],
    },
    "weights": {
        "review_cards":    6,
        "ratings":         3,
        "reviewer_names":  3,
        "review_titles":   3,
        "review_body":     4,
        "show_more_links": 3,
        "show_less_links": 1,
        "helpful_votes":   1,
        "images":          2,
        "headings":        2,
    },
    "safe_click": {"show_more_links", "show_less_links"},
    "dwell": {
        "images":          (4.5, 8.0),
        "review_cards":    (3.0, 6.0),
        "review_body":     (3.0, 6.0),
        "review_titles":   (2.0, 4.0),
        "reviewer_names":  (1.5, 3.5),
        "ratings":         (1.5, 3.5),
        "helpful_votes":   (1.5, 3.0),
        "headings":        (1.5, 3.0),
        "show_more_links": (1.0, 2.5),
        "show_less_links": (1.0, 2.5),
    },
    "default_dwell": (2.5, 5.0),
}


# ======================================================================
# G2 SAUCELABS / PRODUCT PAGE (used by G2_page.py)
# ======================================================================
G2_PRODUCT_POOL = {
    "xpaths": {
        "review_cards": [
            '//div[contains(@class,"review-card")]',
            '//div[@itemprop="review"]',
            '//div[contains(@class,"paper--white")]',
        ],
        "ratings": [
            '//div[contains(@class,"rating")]',
            '//*[@itemprop="ratingValue"]',
            '//*[contains(@class,"star")]',
        ],
        "reviewer_names": [
            '//a[contains(@class,"reviewer")]',
            '//span[@itemprop="author"]',
        ],
        "review_titles": [
            '//div[contains(@class,"review")]//h3',
            '//div[contains(@class,"review")]//h4',
        ],
        "review_body": [
            '//div[contains(@class,"review-content")]',
            '//div[contains(@class,"pros")]',
            '//div[contains(@class,"cons")]',
        ],
        "product_headings": [
            '//*[@id="details"]//h1',
            '//*[@id="details"]//h2',
            '//*[@id="details"]//h3',
        ],
        "feature_cards": [
            '//div[contains(@class,"feature")]',
            '//div[contains(@class,"card")]',
        ],
        "images": [
            '//main//img',
            '//*[@id="details"]//img',
        ],
        "headings": [
            '//h2',
            '//h3',
        ],
    },
    "weights": {
        "review_cards":   6,
        "ratings":        3,
        "reviewer_names": 3,
        "review_titles":  3,
        "review_body":    4,
        "product_headings": 4,
        "feature_cards":  3,
        "images":         2,
        "headings":       2,
    },
    "safe_click": set(),  # no clicks on the product page — avoid navigation
    "dwell": {
        "images":          (4.5, 8.0),
        "review_cards":    (3.0, 6.0),
        "review_body":     (3.0, 6.0),
        "review_titles":   (2.0, 4.0),
        "reviewer_names":  (1.5, 3.5),
        "ratings":         (1.5, 3.5),
        "product_headings": (2.0, 4.0),
        "feature_cards":   (2.5, 5.0),
        "headings":        (1.5, 3.0),
    },
    "default_dwell": (2.5, 5.0),
}


# ======================================================================
# G2 BROWSERSTACK PAGE (managed by G2_page.py)
# ======================================================================
# Keep the page-specific locators here so changes to G2's markup can be
# maintained without searching through the interaction code.
G2_BROWSERSTACK_XPATHS = {
    "product_details": '//*[@id="details"]/div/div[2]/div/div[1]/div[1]/div',
    "product_details_show_more": (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[1]/div/'
        'div[2]/div/div/button/div/span/span'
    ),
    "integrations_section": '//*[@id="details"]/div/div[2]/div/div[2]/div',
    "media_section": '//*[@id="details"]/div/div[2]/div/div[3]',
    "official_downloads_section": (
        '//*[@id="details"]/div/div[2]/div/div[3]/div[2]/div'
    ),
    "official_downloads_show_more": (
        '//*[@id="details"]/div/div[2]/div/div[3]/div[2]/div/'
        'div[2]/div[2]/div'
    ),
    "show_more_descendant": (
        './/button[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), "show more")]'
        ' | .//a[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), "show more")]'
    ),
    "reviews_heading": '//*[@id="reviews-and-filters"]/div/div[1]/div[1]',
    "reviews_text": (
        '//*[@id="reviews-and-filters"]/div/div[1]/div[1]/div[2]/div/div[2]'
    ),
    "target_review": '//*[@id="browserstack-review-10504282"]',
    "reviews_scroll_area": '//*[@id="reviews-and-filters"]/div/div[3]/div',
    "review_read_more": (
        './/*[self::button or self::a or @role="button"]'
        '[contains(translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), '
        '"read more")]'
    ),
    "reviews_pagination": (
        '//*[@id="reviews-and-filters"]/div/div[3]/div/div/ul'
    ),
    "top_rated_alternatives": (
        '//*[@id="additional_information"]/div/div[3]/div[1]/div[1]'
    ),
    "ancestor_button": "./ancestor::button[1]",
    "ancestor_link": "./ancestor::a[1]",
}


# ======================================================================
# SHARED G2 / SAUCE LABS PAGE LOCATORS (used by G2_page.py)
# ======================================================================
G2_PAGE_XPATHS = {
    "top_rated_section": (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]'
    ),
    "alternative_link": (
        '//*[@id="details"]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div[2]/a/div/span'
    ),
    "breadcrumb": '//*[@id="breadcrumbs"]/li[5]/a/span',
    "login_modal_close": '//*[@id="login-modal"]/div[2]/div/div[2]/button',
    "google_result_ancestor_link": "./ancestor::a[1]",
    "show_more_buttons": (
        '//button[.//*[@data-elv--accordion--show-more-controller-target="triggerText" '
        'and normalize-space()="Show More"]]'
    ),
    "show_more_controller": (
        './ancestor::*[contains(@data-controller, '
        '"elv--accordion--show-more-controller")][1]'
    ),
    "top_rated_heading": (
        '//*[@id="details"]//*[normalize-space(.)="Top-Rated Alternatives"]'
    ),
}


# ======================================================================
# GOOGLE SEARCH RESULTS (used by G2Automation.random_words / test_keywords_search)
# ======================================================================
GOOGLE_RESULTS_POOL = {
    "xpaths": {
        "result_headings": [
            '//a[@href]//h3',
            '//div[@id="search"]//h3',
        ],
        "result_snippets": [
            '//div[@id="search"]//div[contains(@class,"VwiC3b")]',
            '//div[@id="search"]//span[contains(@class,"aCOpRe")]',
        ],
        "result_links": [
            '//div[@id="search"]//a[@href]',
        ],
        "people_also_ask": [
            '//div[contains(@class,"related-question-pair")]',
        ],
        "images": [
            '//div[@id="search"]//img',
        ],
        "headings": [
            '//h2',
            '//h3',
        ],
    },
    "weights": {
        "result_headings":  5,
        "result_snippets":  4,
        "result_links":     3,
        "people_also_ask":  2,
        "images":           2,
        "headings":         2,
    },
    # Never click — could navigate away from Google result page
    "safe_click": set(),
    "dwell": {
        "images":          (3.0, 6.0),
        "result_headings": (2.0, 4.0),
        "result_snippets": (3.0, 6.0),
        "result_links":    (1.5, 3.5),
        "people_also_ask": (2.5, 5.0),
        "headings":        (1.5, 3.0),
    },
    "default_dwell": (2.0, 4.5),
}


# Registry — handy if you want to look up by name
ALL_POOLS = {
    "g2_comparison": G2_COMPARISON_POOL,
    "g2_product":    G2_PRODUCT_POOL,
    "google_results": GOOGLE_RESULTS_POOL,
}
