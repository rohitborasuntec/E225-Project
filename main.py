import random
import traceback
import sys
from pathlib import Path

# if __package__ in (None, ""):
#     sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.automation.human_simulator import HumanSimulator
from src.automation.driver import Browser
from src.commons import *
from src.automation.vpn.vpn_automation import ExpressVPN
from src.automation.location_manager import LocationManager
from src.logging import logger
from src.automation.google_work import GoogleSearch
from src.automation.G2_comparison import G2Comparison
from src.automation.G2_page import G2Page
from src.automation.errors import AccessDeniedError
from src.excel import Excel


class G2Automation:

    def __init__(self, driver, human_simulator, gs):
        self.driver = driver
        self.human_simulator = human_simulator
        self.gs = gs
        self.items = {}
        self.excel = Excel()

    def set_data(self, product, comparing_product, browser, location, status, link=""):
        self.items["Link"] = link
        self.items["First product"] = product
        self.items["Second product"] = comparing_product
        self.items["Browser Name"] = browser
        self.items["Country Name"] = location
        self.items["Version Number"] = ""
        self.items["Status"] = status

    def run_g2(self, product, comparing_product, browser, location):
        # FIX: status starts as "Unknown", is upgraded step by step.
        status = "Unknown"
        link = ""
        try:
            categories = [
                'word', 'name', 'country', 'movie',
                'music', 'sports', 'technology', 'News',
            ]
            test_keywords = [
                "browser tests", "software testing", "automation tests",
                "ai in test cases", "app android", "android on browser",
            ]
            keywords_combos = [ (random.choices(categories, k=2), True), (random.choices(test_keywords, k=2), False), ]

            try:
                self.gs.search_work(keywords_combos)
            except Exception as e:
                status = f"Failed at Google Search: {e}"
                logger.exception(status)
                raise  # stop this product row; don't pretend G2 succeeded

            # --- G2 product page ---
            try:
                G2Page(
                    self.driver, self.human_simulator, product, comparing_product
                ).run_g2_product()
                link = self.driver.current_url
            except Exception as e:
                status = f"Failed at G2 Page: {e}"
                logger.exception(status)
                raise

            # --- G2 comparison page ---
            try:
                G2Comparison(
                    self.driver, self.human_simulator, comparing_product
                ).run_g2_comparisons()
                status = "Done"
            except Exception as e:
                # Comparison failure should NOT override the main success.
                status = "Failed at G2 Comparison"
                logger.exception(f"G2 comparison failed: {e}")
            # else:
            
        except Exception:
            # status already set above; ensure we never leave it as "Unknown"
            if status == "Unknown":
                status = "Failed (unknown)"
            logger.error(traceback.format_exc())

        finally:
            self.set_data(
                product, comparing_product, browser, location, status, link,
            )
            self.excel.save_excel(row=self.items)


# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Testrail", "Perfecto"],
#     }
#     location_manager = LocationManager()
#     manager = None  # FIX: initialise before try so finally can reference it.
#     vpn = None
#     try:
#         vpn = ExpressVPN()
#         locations = vpn.get_vpn_locations()

#         for product, comparing_products in products.items():
#             location = random.choice(locations)
#             # vpn.connect(location)

#             manager = Browser(headless=False)
#             driver, browser = manager.launch()
#             human_simulator = HumanSimulator(driver)
#             gs = GoogleSearch(driver, human_simulator)
#             gs.get_google()

#             for comparing_product in comparing_products:
#                 g2_project = G2Automation(driver, human_simulator, gs)
#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )

#             logger.info(f"Comparison Process Completed for {product}")
#             manager.quit(browser_name=browser)
#             manager = None  # avoid double-quit
#             # vpn.disconnect()

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         # vpn.disconnect()

# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Testrail", "Perfecto"],
#     }
#     location_manager = LocationManager()
#     manager = None
#     vpn = None
#     try:
#         vpn = ExpressVPN()

#         for product, comparing_products in products.items():
#             # ----- CHANGED: retry until a real ExpressVPN region connects -----
#             MAX_VPN_ATTEMPTS = 20
#             location = None
#             for attempt in range(1, MAX_VPN_ATTEMPTS + 1):
#                 if not location_manager.has_next():
#                     logger.error(
#                         "No VPN locations left — aborting remaining products."
#                     )
#                     break

#                 candidate = location_manager.next()
#                 try:
#                     vpn.connect(candidate)
#                     location = candidate
#                     logger.info(
#                         f"[VPN] Connected to '{candidate}' "
#                         f"on attempt {attempt}/{MAX_VPN_ATTEMPTS}"
#                     )
#                     break  # got a good one — stop retrying
#                 except Exception as e:
#                     logger.warning(
#                         f"[VPN] '{candidate}' rejected ({e}); "
#                         f"blacklisting and picking another."
#                     )
#                     location_manager.mark_failed(candidate)
#                     vpn.disconnect()
#                     continue

#             if location is None:
#                 logger.error(
#                     f"Exhausted {MAX_VPN_ATTEMPTS} attempts for '{product}' — skipping."
#                 )
#                 continue
#             # ------------------------------------------------------------------

#             for comparing_product in comparing_products:
                
#                 if Excel.check_if_present(product,comparing_product):
#                     logger.info(f"Already Done {product} and {comparing_product}")
#                     continue

#                 manager = Browser(headless=False)
#                 driver, browser = manager.launch()
#                 human_simulator = HumanSimulator(driver)
#                 gs = GoogleSearch(driver, human_simulator)
#                 gs.get_google()
#                 g2_project = G2Automation(driver, human_simulator, gs)
#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )

#                 logger.info(f"Comparison Process Completed for {product}")
#                 manager.quit(browser_name=browser)
#                 manager = None

#                 location_manager.mark_success(location)
#                 vpn.disconnect()

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         if vpn is not None:
#             try:
#                 vpn.disconnect()
#             except Exception:
#                 pass

# if __name__ == "__main__":
    # logger.info("Script Has Been Started..............")

    # products = {
    #     "SauceLabs":    ["Ranorex", "Testcomplete"],
    #     "BrowserStack": ["Testrail", "Perfecto"],
    # }
    # location_manager = LocationManager()
    # manager = None  # FIX: initialise before try so finally can reference it.
    # vpn = None
    # try:
    #     vpn = ExpressVPN()

    #     for product, comparing_products in products.items():
    #         # ----- CHANGED: use LocationManager instead of vpn.get_vpn_locations() -----
    #         if not location_manager.has_next():
    #             logger.error(
    #                 "No VPN locations left — aborting remaining products."
    #             )
    #             break
    #         location = location_manager.next()  # tiered, unused, non-blacklisted
    #         # ---------------------------------------------------------------------------

    #         try:
    #             # ----- CHANGED: actually connect the VPN for this location -----
    #             vpn.connect(location)
    #             # ---------------------------------------------------------------
    #         except Exception as e:
    #             logger.error(f"VPN connect failed for '{location}': {e}")
    #             location_manager.mark_failed(location)  # blacklist this endpoint
    #             vpn.disconnect()                        # ensure clean state
    #             continue                                # try next product's location

    #         manager = Browser(headless=False)
    #         driver, browser = manager.launch()
    #         human_simulator = HumanSimulator(driver)
    #         gs = GoogleSearch(driver, human_simulator)
    #         gs.get_google()

    #         for comparing_product in comparing_products:
    #             g2_project = G2Automation(driver, human_simulator, gs)
    #             try:
    #                 g2_project.run_g2(product, comparing_product, browser, location)
    #             except Exception as e:
    #                 logger.error(
    #                     f"run_g2 failed for {product}/{comparing_product}: {e}"
    #                 )

    #         logger.info(f"Comparison Process Completed for {product}")
    #         manager.quit(browser_name=browser)
    #         manager = None  # avoid double-quit

    #         # ----- CHANGED: report success + disconnect the VPN -----
    #         location_manager.mark_success(location)
    #         vpn.disconnect()
    #         # --------------------------------------------------------

    # except Exception:
    #     logger.error(traceback.format_exc())
    # finally:
    #     if manager is not None:
    #         try:
    #             manager.quit()
    #         except Exception:
    #             pass
    #     # ----- CHANGED: actually disconnect the VPN in finally -----
    #     if vpn is not None:
    #         try:
    #             vpn.disconnect()
    #         except Exception:
    #             pass
    #     # -----------------------------------------------------------

# if __name__ == "__main__":
#     logger.info("Script Has Been Started..............")

#     products = {
#         "SauceLabs":    ["Ranorex", "Testcomplete"],
#         "BrowserStack": ["Qase", "accessiBe"],
#     }
#     location_manager = LocationManager()
#     manager = None
#     vpn = None

#     # ----- CHANGED: configurable waits -----
#     VPN_SETTLE_WAIT      = 5   # after connect, before opening browser
#     POST_DISCONNECT_WAIT = 3   # after disconnect, before next connect/browser
#     MAX_VPN_ATTEMPTS     = 20
#     # --------------------------------------

#     try:
#         vpn = ExpressVPN()
        

#         for product, comparing_products in products.items():

#             for comparing_product in comparing_products:

#                 # if Excel().check_if_present(product, comparing_product):
#                 #     logger.info(f"Already Done {product} and {comparing_product}")
#                 #     continue
#                 # # ---------------------------------------------------------------------

#                 # ----- CHANGED: VPN retry loop moved INSIDE comparing_products -----
#                 location = None
#                 for attempt in range(1, MAX_VPN_ATTEMPTS + 1):
#                     if not location_manager.has_next():
#                         logger.error(
#                             "No VPN locations left — aborting remaining work."
#                         )
#                         break

#                     candidate = location_manager.next()
#                     try:
#                         vpn.connect(candidate)
#                         location = candidate
#                         logger.info(
#                             f"[VPN] Connected to '{candidate}' "
#                             f"on attempt {attempt}/{MAX_VPN_ATTEMPTS}"
#                         )
#                         break  # got a good one
#                     except Exception as e:
#                         logger.warning(
#                             f"[VPN] '{candidate}' rejected ({e}); "
#                             f"blacklisting and picking another."
#                         )
#                         location_manager.mark_failed(candidate)
#                         vpn.disconnect()
#                         time.sleep(POST_DISCONNECT_WAIT)  # cool down before retry
#                         continue

#                 if location is None:
#                     logger.error(
#                         f"Exhausted {MAX_VPN_ATTEMPTS} attempts for "
#                         f"'{product}/{comparing_product}' — skipping."
#                     )
#                     continue

#                 # ----- CHANGED: wait for the tunnel to actually stabilize -----
#                 time.sleep(VPN_SETTLE_WAIT)
#                 # ---------------------------------------------------------------

#                 # ----- CHANGED: fresh browser per comparing_product -----
#                 manager = Browser(headless=False)
#                 driver, browser = manager.launch()
#                 human_simulator = HumanSimulator(driver)
#                 gs = GoogleSearch(driver, human_simulator)
#                 gs.get_google()
#                 g2_project = G2Automation(driver, human_simulator, gs)

#                 try:
#                     g2_project.run_g2(product, comparing_product, browser, location)
#                     logger.info(
#                         f"Comparison Process Completed for "
#                         f"{product}/{comparing_product} via '{location}'"
#                     )
#                     location_manager.mark_success(location)
#                 except Exception as e:
#                     logger.error(
#                         f"run_g2 failed for {product}/{comparing_product}: {e}"
#                     )
#                     location_manager.mark_failed(location)  # endpoint may be bad
#                 finally:
#                     # ----- CHANGED: always close browser, then disconnect VPN -----
#                     if manager is not None:
#                         try:
#                             manager.quit(browser_name=browser)
#                         except Exception:
#                             pass
#                         manager = None

#                     try:
#                         vpn.disconnect()
#                     except Exception:
#                         pass

#                     # ----- CHANGED: wait AFTER disconnect, BEFORE next browser -----
#                     time.sleep(POST_DISCONNECT_WAIT)
#                     # -----------------------------------------------------------------
#                 # ------------------------------------------------------------------------

#     except Exception:
#         logger.error(traceback.format_exc())
#     finally:
#         if manager is not None:
#             try:
#                 manager.quit()
#             except Exception:
#                 pass
#         if vpn is not None:
#             try:
#                 vpn.disconnect()
#             except Exception:
#                 pass

if __name__ == "__main__":
    logger.info("Script Has Been Started..............")

    products = {
        "SauceLabs":    ["Ranorex", "TestComplete"],
        "BrowserStack": ["Qase", "accessiBe"],
    }

    location_manager = LocationManager()
    manager = None
    vpn = None

    # ----- configurable waits / attempts -----
    VPN_SETTLE_WAIT      = 5    # after connect, before opening browser
    POST_DISCONNECT_WAIT = 3    # after disconnect, before next connect/browser
    MAX_VPN_ATTEMPTS     = 20   # per (product, comparing_product)
    # -----------------------------------------
    # left_out = [
    #     (product, comparing_product)
    #     for product, comparing_products in products.items()
    #     for comparing_product in comparing_products
    # ]

    # pairs_to_do = [
    # (p, cp)
    # for p, cps in products.items()
    # for cp in cps
    # if not Excel().check_if_completed(p, cp)
    # ]
    # vpn = ExpressVPN()
    
    # for product, comparing_product in pairs_to_do:
    #     logger.info(f"Starting comparison for {product} and {comparing_product}")

    #     pair_succeeded = False
    #     pair_permanently_failed = False

    #     for pair_attempt in range(1, MAX_VPN_ATTEMPTS + 1):
    #         location = None

    #         # --- pick & connect a VPN ---
    #         for _ in range(MAX_VPN_ATTEMPTS):
    #             if not location_manager.has_next():
    #                 logger.error("No VPN locations left — aborting.")
    #                 pair_permanently_failed = True
    #                 break
    #             candidate = location_manager.next()
    #             try:
    #                 vpn.connect(candidate)
    #                 location = candidate
    #                 logger.info(f"[VPN] Connected to '{candidate}'")
    #                 break
    #             except Exception as e:
    #                 logger.warning(f"[VPN] '{candidate}' rejected ({e}); blacklisting.")
    #                 location_manager.mark_failed(candidate)
    #                 try: vpn.disconnect()
    #                 except Exception: pass
    #                 time.sleep(POST_DISCONNECT_WAIT)

    #         if pair_permanently_failed or location is None:
    #             break

    #         time.sleep(VPN_SETTLE_WAIT)
    #         done_browser = Excel().browser_list()

    #         manager = Browser(headless=False, done_browser=done_browser)
    #         driver, browser = manager.launch()
    #         human_simulator = HumanSimulator(driver)
    #         gs = GoogleSearch(driver, human_simulator)
    #         gs.get_google()
    #         g2_project = G2Automation(driver, human_simulator, gs)

    #         try:
    #             g2_project.run_g2(product, comparing_product, browser, location)
    #             logger.info(f"Completed {product}/{comparing_product} via '{location}'")
    #             location_manager.mark_success(location)
    #             pair_succeeded = True

    #         except AccessDeniedError as blocked:
    #             # Network block → retry with a new VPN
    #             logger.warning(
    #                 f"[RETRY {pair_attempt}/{MAX_VPN_ATTEMPTS}] Access denied on "
    #                 f"'{location}' for {product}/{comparing_product}: {blocked}"
    #             )
    #             location_manager.mark_failed(location)
    #             pair_succeeded = False   # will retry

    #         except Exception as e:
    #             # Code/data error → do NOT retry, do NOT blame the VPN
    #             logger.error(
    #                 f"run_g2 failed for {product}/{comparing_product}: {e}",
    #                 exc_info=True,
    #             )
    #             pair_permanently_failed = True
    #             pair_succeeded = False

    #         finally:
    #             try: manager.quit(browser_name=browser)
    #             except Exception: pass
    #             try: vpn.disconnect()
    #             except Exception: pass
    #             time.sleep(POST_DISCONNECT_WAIT)

    #         if pair_succeeded or pair_permanently_failed:
    #             break
    #         # otherwise loop → new VPN for the same pair

    #     if not pair_succeeded:
    #         logger.error(
    #             f"Giving up on {product}/{comparing_product} after "
    #             f"{MAX_VPN_ATTEMPTS} attempts."
    #         )
    
    try:
        vpn = ExpressVPN()
        done_browser = []

        for product, comparing_products in products.items():
            for comparing_product in comparing_products:

                if Excel().check_if_completed(product, comparing_product):
                    # left_out.remove((product, comparing_product))
                    logger.info(f"Already Done {product} and {comparing_product}")
                    continue 
                
                logger.info(f"Starting comparison for {product} and {comparing_product}")
                pair_done = False

                for pair_attempt in range(1, MAX_VPN_ATTEMPTS + 1):

                    # ---- pick + connect a fresh VPN -----------------
                    location = None
                    for vpn_attempt in range(1, MAX_VPN_ATTEMPTS + 1):
                        if not location_manager.has_next():
                            logger.error(
                                "No VPN locations left — aborting remaining work."
                            )
                            break

                        candidate = location_manager.next()
                        try:
                            vpn.connect(candidate)
                            location = candidate
                            logger.info(
                                f"[VPN] Connected to '{candidate}' "
                                f"(pair attempt {pair_attempt}/"
                                f"{MAX_VPN_ATTEMPTS}, "
                                f"connect try {vpn_attempt}/"
                                f"{MAX_VPN_ATTEMPTS})"
                            )
                            break
                        except Exception as e:
                            logger.warning(
                                f"[VPN] '{candidate}' rejected ({e}); "
                                f"blacklisting and picking another."
                            )
                            location_manager.mark_failed(candidate)
                            vpn.disconnect()
                            time.sleep(POST_DISCONNECT_WAIT)
                            continue

                    if location is None:
                        logger.error(
                            f"Exhausted VPN connect attempts for "
                            f"'{product}/{comparing_product}' — skipping."
                        )
                        break   # out of pair_attempt loop, move to next pair

                    # ---- let the tunnel stabilise -------------------
                    time.sleep(VPN_SETTLE_WAIT)
                    done_browser = Excel().browser_list()
                    
                    logger.info(f"Browsers already done: {done_browser}")
                    # ---- fresh browser per attempt ------------------
                    manager = Browser(headless=False,done_browser=done_browser)
                    driver, browser = manager.launch()
                    
                    human_simulator = HumanSimulator(driver)
                    gs = GoogleSearch(driver, human_simulator)
                    gs.get_google()
                    
                    g2_project = G2Automation(driver, human_simulator, gs)

                    retry_needed = False

                    try:
                        g2_project.run_g2(
                            product, comparing_product, browser, location
                        )
                        logger.info(
                            f"Comparison Process Completed for "
                            f"{product}/{comparing_product} via '{location}'"
                        )
                        location_manager.mark_success(location)
                        pair_done = True
                        # left_out.remove((product, comparing_product))

                    except AccessDeniedError as blocked:
                        # ---- CHANGED: restart the WHOLE pair on a new VPN ----
                        logger.warning(
                            f"[RETRY] Access denied for "
                            f"{product}/{comparing_product} on '{location}': "
                            f"{blocked}. Restarting flow with a new VPN."
                        )
                        location_manager.mark_failed(location)
                        retry_needed = True

                    except Exception as e:
                        logger.error(
                            f"run_g2 failed for {product}/{comparing_product}: {e}"
                        )
                        location_manager.mark_failed(location)
                        # Non-AccessDenied failures: do NOT restart the whole
                        # pair with a new VPN — it's most likely a code / data
                        # problem, not a network block.
                        pair_done = True   # give up on this pair this run

                    finally:
                        # Always close the browser, then disconnect the VPN,
                        # then wait before the next attempt/connect.
                        if manager is not None:
                            try:
                                manager.quit(browser_name=browser)
                            except Exception:
                                pass
                            manager = None

                        try:
                            vpn.disconnect()
                        except Exception:
                            pass

                        time.sleep(POST_DISCONNECT_WAIT)

                    if pair_done:
                        break   # done with this pair for this run
                    if retry_needed:
                        continue   # loop back, pick a new VPN, restart pair

                    # ---- end of pair_attempt loop -----------------------

    except Exception:
        logger.error(traceback.format_exc())
    finally:
        if manager is not None:
            try:
                manager.quit()
            except Exception:
                pass
        if vpn is not None:
            try:
                vpn.disconnect()
            except Exception:
                pass
            