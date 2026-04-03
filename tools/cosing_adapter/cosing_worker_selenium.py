from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from selenium import webdriver  # type: ignore
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, WebDriverException  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.common.keys import Keys  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
from webdriver_manager.microsoft import EdgeChromiumDriverManager  # type: ignore

from .parser import parse_cosing_detail_page, parse_cosing_results_table
from .schemas import ChemicalLookupOutput, QueryType, vietnam_now_iso


COSING_URL = "https://ec.europa.eu/growth/tools-databases/cosing/advanced"


@dataclass
class WorkerConfig:
    cosing_url: str = COSING_URL
    headless: bool = True
    browser: str = "chrome"  # chrome|edge
    timeout_seconds: int = 30
    retries: int = 3
    backoff_seconds: int = 2
    artifacts_dir: Path = Path("data/artifacts/cosing")
    circuit_breaker_trip_failures: int = 3
    circuit_breaker_cooldown_seconds: int = 300


class CosingSeleniumWorker:
    def __init__(self, config: Optional[WorkerConfig] = None) -> None:
        self.config = config or WorkerConfig()
        self.config.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("cosing_worker")
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _build_driver(self) -> webdriver.Remote:
        browser = (self.config.browser or "chrome").lower().strip()
        headless = bool(self.config.headless)

        if browser == "edge":
            service = webdriver.edge.service.Service(EdgeChromiumDriverManager().install())
            options = webdriver.EdgeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            driver = webdriver.Edge(service=service, options=options)
            return driver

        # default: chrome
        service = webdriver.chrome.service.Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    def _wait_for_input(self, driver: webdriver.Remote) -> Any:
        """
        Heuristic input finder:
        - try an input field near label containing 'Substance'
        - fallback: any input[type=text] in the main panel
        """
        wait = WebDriverWait(driver, self.config.timeout_seconds)

        # Try label-based input: label text contains "Substance"
        try:
            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//label[contains(translate(., 'SUBSTANCE', 'substance'), 'substance')]//following::input[1]")
                )
            )
            el = driver.find_element(
                By.XPATH,
                "//label[contains(translate(., 'SUBSTANCE', 'substance'), 'substance')]//following::input[1]",
            )
            return el
        except Exception:
            self.logger.debug("label-based input not found; fallback to generic input[type=text]")
            pass

        # Fallback: pick first visible text input
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
        candidates = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
        for c in candidates:
            if c.is_displayed():
                return c

        raise TimeoutException("Khong tim thay input substance tren trang CoSIng.")

    def _wait_for_results(self, driver: webdriver.Remote) -> Any:
        wait = WebDriverWait(driver, self.config.timeout_seconds)
        # Wait until a results table appears
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        # CoSIng có thể vẫn render table với header khi không có kết quả.
        # Theo spec adapter, trường hợp không có substance cần trả substances=[] (không nên coi là lỗi).
        # Vì vậy không ép điều kiện table phải có >1 dòng.
        # Thêm delay nhỏ để giảm rủi ro parse quá sớm.
        time.sleep(1)
        # return first table
        return driver.find_element(By.CSS_SELECTOR, "table")

    def _click_first_result(self, driver: webdriver.Remote, query: str) -> None:
        """
        Click vào dòng đầu tiên trong bảng kết quả để mở trang chi tiết.
        Dùng heuristic: ưu tiên anchor <a>.
        Trên CoSIng có thể có nhiều link trong một dòng (INCI name vs Substance name),
        nên ưu tiên link mà text không trùng query (giảm khả năng mở nhầm trang Ingredient).
        """
        table_el = driver.find_element(By.CSS_SELECTOR, "table")
        rows = table_el.find_elements(By.CSS_SELECTOR, "tbody tr")
        if not rows:
            all_tr = table_el.find_elements(By.CSS_SELECTOR, "tr")
            rows = all_tr[1:] if len(all_tr) > 1 else []

        if not rows:
            raise TimeoutException("Khong tim thay dong ket qua (tbody tr) de click.")

        row = rows[0]

        # Prefer an <a> target inside the row.
        needle = (query or "").strip().upper()
        anchors = row.find_elements(By.CSS_SELECTOR, "a")
        # Prefer links whose visible text doesn't match the query
        if anchors:
            non_matching = []
            matching = []
            for a in anchors:
                try:
                    txt = (a.text or "").strip().upper()
                except Exception:
                    txt = ""
                if not txt:
                    continue
                if needle and needle in txt:
                    matching.append(a)
                else:
                    non_matching.append(a)

            target = non_matching[0] if non_matching else (matching[0] if matching else anchors[0])
        else:
            target = None

        if target is None:
            for sel in ("button", "input[type='button']", "input[type='submit']"):
                try:
                    target = row.find_element(By.CSS_SELECTOR, sel)
                    break
                except Exception:
                    continue

        try:
            if target is not None:
                target.click()
            else:
                row.click()
        except Exception:
            if target is not None:
                driver.execute_script("arguments[0].click();", target)
            else:
                driver.execute_script("arguments[0].click();", row)

    def _wait_for_detail_page(self, driver: webdriver.Remote) -> None:
        """
        Chờ trang chi tiết load xong bằng dấu hiệu label 'INCI Name'.
        """
        wait = WebDriverWait(driver, self.config.timeout_seconds)
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(),'INCI Name')]")))

    def _wait_for_casing_detail_loaded(self, driver: webdriver.Remote) -> None:
        """
        Chờ trang detail tải xong theo dấu hiệu 'CAS #' (áp dụng cho cả bảng condense và bảng chi tiết).
        """
        wait = WebDriverWait(driver, self.config.timeout_seconds)
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(),'CAS #')]")))

    def _wait_for_sccs_opinions_loaded(self, driver: webdriver.Remote) -> None:
        """
        Chờ danh sách SCCS opinions (li) được render.
        Một số field load bất đồng bộ nên snapshot quá sớm sẽ ra danh sách rỗng.
        """
        wait = WebDriverWait(driver, self.config.timeout_seconds)

        def has_li(d: webdriver.Remote) -> bool:
            try:
                # Scroll to SCCS opinions section to trigger lazy loading (if any).
                try:
                    label_el = d.find_element(
                        By.XPATH,
                        "//td[contains(normalize-space(),'SCCS opinions')]",
                    )
                    d.execute_script("arguments[0].scrollIntoView({block:'center'});", label_el)
                    time.sleep(0.5)
                except Exception:
                    pass

                els = d.find_elements(
                    By.XPATH,
                    "//td[contains(normalize-space(),'SCCS opinions')]/ancestor::tr//li[normalize-space()]",
                )
                return len(els) > 0
            except Exception:
                return False

        wait.until(has_li)

    def _click_first_identified_ingredient_link(self, driver: webdriver.Remote) -> bool:
        """
        Trên trang detail có danh sách 'Identified INGREDIENTS or substances ...',
        bấm vào link đầu tiên để mở trang detail con (nơi SCCS opinions thường đầy đủ hơn).
        """
        try:
            # The ingredient page contains at least one link to /details/<id>.
            links = driver.find_elements(
                By.XPATH,
                "//td[contains(normalize-space(),'Identified INGREDIENTS')]/following-sibling::td//a[contains(@href,'/growth/tools-databases/cosing/details/')]",
            )
            if not links:
                # Fallback: any /details/<id> link.
                links = driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href,'/growth/tools-databases/cosing/details/')]",
                )
                if not links:
                    return False

            href = links[0].get_attribute("href") or ""
            if not href:
                return False

            target_url = urljoin("https://ec.europa.eu", href)
            driver.get(target_url)
            # Không phụ thuộc vào chuỗi header cụ thể ("Substance:" đôi khi không ổn định theo DOM).
            # SCCS opinions sẽ được chờ và parse ở tầng fetch_detail.
            time.sleep(1.5)
            return True
        except Exception:
            return False

    def _dismiss_cookie_banner(self, driver: webdriver.Remote) -> None:
        """
        CoSIng/EU site thường hiển thị cookie consent banner (overlay cố định).
        Nếu không dismiss, thao tác submit có thể bị che => ElementClickIntercepted.
        """
        try:
            wait = WebDriverWait(driver, 10)
            banner = wait.until(EC.presence_of_element_located((By.ID, "cookie-consent-banner")))

            # Prefer accept all cookies.
            accept = None
            try:
                accept = banner.find_element(By.CSS_SELECTOR, "a[href='#accept']")
            except Exception:
                accept = None

            if accept is None:
                try:
                    accept = banner.find_element(By.CSS_SELECTOR, "a[href='#refuse']")
                except Exception:
                    accept = None

            if accept is None:
                return

            try:
                accept.click()
            except Exception:
                driver.execute_script("arguments[0].click();", accept)

            # Wait banner to disappear (or at least no longer overlay-interactive).
            try:
                WebDriverWait(driver, 10).until(
                    EC.invisibility_of_element_located((By.ID, "cookie-consent-banner"))
                )
            except Exception:
                # Not critical; continue.
                pass
        except TimeoutException:
            # No banner appeared in time.
            return

    def _snapshot_artifacts(
        self,
        request_id: str,
        driver: webdriver.Remote,
        suffix: str,
    ) -> None:
        ts = int(time.time())
        artifacts = self.config.artifacts_dir / request_id
        artifacts.mkdir(parents=True, exist_ok=True)

        screenshot_path = artifacts / f"{suffix}_{ts}.png"
        html_path = artifacts / f"{suffix}_{ts}.html"

        try:
            driver.save_screenshot(str(screenshot_path))
        except Exception:
            pass
        try:
            html_path.write_text(driver.page_source, encoding="utf-8")
        except Exception:
            pass

    def fetch(self, query: str, query_type: QueryType, request_id: str) -> ChemicalLookupOutput:
        now = time.time()
        if now < self._circuit_open_until:
            out = ChemicalLookupOutput(request_id=request_id, substances=[], status="ERROR")
            out.rejection_reason = (
                f"circuit_breaker_open until={int(self._circuit_open_until)}; "
                f"consecutive_failures={self._consecutive_failures}"
            )
            return out

        attempt = 0
        last_err: Optional[str] = None

        while attempt < self.config.retries:
            attempt += 1
            driver: Optional[webdriver.Remote] = None
            try:
                driver = self._build_driver()
                driver.set_page_load_timeout(self.config.timeout_seconds)
                driver.get(self.config.cosing_url)

                # Dismiss cookie banner overlay first.
                self._dismiss_cookie_banner(driver)

                # Wait for body/page ready by waiting for an input to show up
                input_el = self._wait_for_input(driver)
                input_el.clear()
                input_el.send_keys(query)

                # Submit using ENTER on input first (avoid click intercepted by overlays).
                try:
                    input_el.send_keys(Keys.ENTER)
                except Exception:
                    try:
                        input_el.submit()
                    except Exception:
                        pass

                # Wait results table (hoac trang thai khong co ket qua).
                try:
                    table_el = self._wait_for_results(driver)
                    table_html = table_el.get_attribute("outerHTML")

                    substances = parse_cosing_results_table(
                        table_html,
                        reference_url=self.config.cosing_url,
                    )

                    # If we got a results table but parsed 0 substances, assume DOM changed or parse heuristic failed.
                    if not substances:
                        table_text = (table_el.text or "").strip().lower()
                        is_no_results = any(
                            marker in table_text
                            for marker in (
                                "no result",
                                "no results",
                                "no data",
                                "no substance",
                                "0 results",
                                "no matching results found",
                            )
                        )
                        if not is_no_results:
                            self.logger.warning(
                                "parse returned empty substances; capturing artifacts. attempt=%s",
                                attempt,
                            )
                            self._snapshot_artifacts(request_id, driver, suffix=f"parse_empty_attempt{attempt}")
                except TimeoutException:
                    # When there are no results, CosIng can render an info message and no results table.
                    page = (driver.page_source or "").lower()
                    if "no matching results found" in page:
                        substances = []
                    else:
                        raise

                output = ChemicalLookupOutput(request_id=request_id, substances=substances, status="OK")
                # Fill fetched_at + reference_url per substance
                fetched_at = vietnam_now_iso()
                for s in output.substances:
                    s.reference_url = self.config.cosing_url
                    s.fetched_at = fetched_at
                self._consecutive_failures = 0
                return output

            except (TimeoutException, WebDriverException, Exception) as e:
                last_err = str(e)
                self._consecutive_failures += 1
                if driver is not None:
                    self._snapshot_artifacts(request_id, driver, suffix=f"attempt{attempt}_fail")
                if attempt < self.config.retries:
                    self.logger.warning("worker attempt failed; retrying. attempt=%s err=%s", attempt, last_err)
                    time.sleep(self.config.backoff_seconds * attempt)
                    continue
                break
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        # open circuit if repeated failures
        if self._consecutive_failures >= self.config.circuit_breaker_trip_failures:
            self._circuit_open_until = time.time() + self.config.circuit_breaker_cooldown_seconds

        output = ChemicalLookupOutput(request_id=request_id, substances=[], status="ERROR")
        output.rejection_reason = f"Worker failed after {self.config.retries} attempts. last_error={last_err}"
        return output

    def fetch_detail(self, query: str, query_type: QueryType, request_id: str) -> dict:
        """
        Mở trang chi tiết của kết quả đầu tiên và trích xuất các field nổi bật.
        """
        attempt = 0
        last_err: Optional[str] = None

        while attempt < self.config.retries:
            attempt += 1
            driver: Optional[webdriver.Remote] = None
            try:
                now = time.time()
                if now < self._circuit_open_until:
                    return {
                        "request_id": request_id,
                        "status": "ERROR",
                        "rejection_reason": f"circuit_breaker_open until={int(self._circuit_open_until)}",
                    }

                driver = self._build_driver()
                driver.set_page_load_timeout(self.config.timeout_seconds)
                driver.get(self.config.cosing_url)

                self._dismiss_cookie_banner(driver)

                input_el = self._wait_for_input(driver)
                input_el.clear()

                input_el.send_keys(query)

                # Submit bằng Enter (tránh click bị che bởi overlay).
                try:
                    input_el.send_keys(Keys.ENTER)
                except Exception:
                    try:
                        input_el.submit()
                    except Exception:
                        pass

                # Bảng kết quả -> click dòng đầu tiên.
                self._wait_for_results(driver)
                # Debug: lưu snapshot trang kết quả trước khi click (để xác định đúng link).
                self._snapshot_artifacts(request_id, driver, suffix="results_before_click")
                self._click_first_result(driver, query)
                # Trang detail con trong video thường cần click thêm link "Identified INGREDIENTS ..."
                try:
                    self._wait_for_detail_page(driver)
                except Exception:
                    # Một số layout có thể không có label INCI Name.
                    pass

                # Parse trang Ingredient trước khi click "Identified ..." để lấy các field
                # như `inci_name` và `functions` (trang Substance không luôn có row Functions).
                ingredient_detail: Optional[dict[str, str]] = None
                try:
                    ingredient_detail = parse_cosing_detail_page(
                        driver.page_source,
                        reference_url=self.config.cosing_url,
                    )
                except Exception:
                    ingredient_detail = None

                # Chờ danh sách "Identified INGREDIENTS or substances ..." có link details/<id>
                # để tránh chạy helper quá sớm.
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//td[contains(normalize-space(),'Identified INGREDIENTS')]/following-sibling::td//a[contains(@href,'/growth/tools-databases/cosing/details/')]",
                            )
                        )
                    )
                except Exception:
                    pass

                # Nếu có link identified ingredient, mở trang con rồi parse (SCCS opinions hay nằm ở trang con).
                clicked = self._click_first_identified_ingredient_link(driver)
                if clicked:
                    self._snapshot_artifacts(request_id, driver, suffix="after_identified_nav")
                    self._wait_for_casing_detail_loaded(driver)

                try:
                    self._wait_for_sccs_opinions_loaded(driver)
                except Exception:
                    pass

                detail = parse_cosing_detail_page(driver.page_source, reference_url=self.config.cosing_url)

                # Merge: lấy `inci_name`/`functions` từ trang Ingredient, còn `sccs_opinions`/`annex_ref` từ trang Substance.
                if ingredient_detail:
                    if detail.get("inci_name") is None or not detail.get("inci_name"):
                        detail["inci_name"] = ingredient_detail.get("inci_name", "")
                    if detail.get("functions") is None or not detail.get("functions"):
                        detail["functions"] = ingredient_detail.get("functions", "")
                # Save snapshot for debugging of parsing heuristics.
                self._snapshot_artifacts(request_id, driver, suffix="detail_success")
                detail["request_id"] = request_id
                detail["status"] = "OK"
                detail["fetched_at"] = vietnam_now_iso()
                self._consecutive_failures = 0
                return detail

            except (TimeoutException, WebDriverException, Exception) as e:
                last_err = str(e)
                self._consecutive_failures += 1
                if driver is not None:
                    self._snapshot_artifacts(request_id, driver, suffix=f"detail_attempt{attempt}_fail")

                if attempt < self.config.retries:
                    self.logger.warning(
                        "detail worker attempt failed; retrying. attempt=%s err=%s",
                        attempt,
                        last_err,
                    )
                    time.sleep(self.config.backoff_seconds * attempt)
                    continue
                break

            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        if self._consecutive_failures >= self.config.circuit_breaker_trip_failures:
            self._circuit_open_until = time.time() + self.config.circuit_breaker_cooldown_seconds

        return {
            "request_id": request_id,
            "status": "ERROR",
            "rejection_reason": f"Detail fetch failed after {self.config.retries} attempts. last_error={last_err}",
        }

