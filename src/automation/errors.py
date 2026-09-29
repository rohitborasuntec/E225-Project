"""
src/automation/errors.py
------------------------
Shared exception types used to signal that a retry-with-new-VPN is required.
"""


class AccessDeniedError(RuntimeError):
    """
    Raised when a page returns a block / Access Denied / captcha wall.

    The top-level runner catches this, closes the browser, disconnects the
    VPN, blacklists the current location, and retries the SAME
    (product, comparing_product) pair with a fresh VPN connection.
    """