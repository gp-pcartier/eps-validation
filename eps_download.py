"""
EPS Download — Cloud-compatible USPS CSV downloader
Uses Playwright headless Chromium to log into USPS and download the mailing report CSV.
Designed to run in a cloud sandbox (no display, no system Chrome).
"""

import os
import sys
import datetime
import time


def download_csv(username, password, output_dir="/tmp/eps-download"):
    """Log into USPS EPS, generate report, download CSV. Returns path to downloaded file."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    today = datetime.date.today()
    start_date = today.replace(day=1).strftime("%m/%d/%Y")
    end_date = today.strftime("%m/%d/%Y")

    print(f"Date range: {start_date} to {end_date}")

    csv_path = None

    with sync_playwright() as p:
        # Launch headless Chromium (cloud-compatible, no display needed)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # ── Navigate to report page (will redirect to login) ──────────
            print("Navigating to USPS...")
            report_url = "https://epay.usps.com/paymod/reports/mailing-shipping-details/product-details"
            page.goto(report_url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            print(f"  Redirected to: {page.url}")

            # ── Login ─────────────────────────────────────────────────────
            if "paymod/reports" not in page.url:
                print("Logging in...")

                # Click "Sign in to the BCG" if on gateway page
                try:
                    bcg_btn = page.locator("input[value='Sign in to the BCG']").first
                    bcg_btn.wait_for(state="visible", timeout=10000)
                    bcg_btn.click()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    print(f"  After BCG click: {page.url}")
                except Exception:
                    pass

                # Fill credentials (callback_1 = username, callback_2 = password)
                try:
                    user_field = None
                    for sel in ["input[name='callback_1']", "input[name='username']", "input[type='text']:visible"]:
                        try:
                            f = page.locator(sel).first
                            f.wait_for(state="visible", timeout=3000)
                            user_field = f
                            break
                        except Exception:
                            pass

                    if user_field:
                        user_field.clear()
                        user_field.fill(username)

                        for sel in ["input[name='callback_2']", "input[name='password']", "input[type='password']:visible"]:
                            try:
                                f = page.locator(sel).first
                                f.wait_for(state="visible", timeout=3000)
                                f.clear()
                                f.fill(password)
                                f.press("Enter")
                                break
                            except Exception:
                                pass

                        # Wait for login redirect chain to complete
                        try:
                            page.wait_for_url("**/gateway.usps.com/**", timeout=30000)
                        except Exception:
                            pass
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                        time.sleep(3)
                        print(f"  Post-login URL: {page.url}")
                    else:
                        print("  ERROR: Could not find login form")
                        return None
                except Exception as e:
                    print(f"  ERROR: Login failed: {e}")
                    return None

                # Navigate to report page after login
                page.goto(report_url, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                print(f"  Report page URL: {page.url}")

                if "paymod/reports" not in page.url:
                    print("  ERROR: Could not reach report page after login")
                    return None

            # ── Set date range ────────────────────────────────────────────
            print("Setting date range...")
            page.wait_for_timeout(3000)

            for start_sel in [
                "input[aria-label*='Start']", "input[placeholder*='start']",
                "input[id*='start']", "input[name*='start']"
            ]:
                try:
                    f = page.locator(start_sel).first
                    if f.is_visible():
                        f.click(click_count=3)
                        f.fill(start_date)
                        break
                except Exception:
                    pass
            else:
                inputs = page.locator("input[type='text']:visible").all()
                if len(inputs) >= 1:
                    inputs[0].click(click_count=3)
                    inputs[0].fill(start_date)
                if len(inputs) >= 2:
                    inputs[1].click(click_count=3)
                    inputs[1].fill(end_date)

            for end_sel in [
                "input[aria-label*='End']", "input[placeholder*='end']",
                "input[id*='end']", "input[name*='end']"
            ]:
                try:
                    f = page.locator(end_sel).first
                    if f.is_visible():
                        f.click(click_count=3)
                        f.fill(end_date)
                        break
                except Exception:
                    pass
            print(f"  Dates: {start_date} to {end_date}")

            # ── Generate report ───────────────────────────────────────────
            print("Generating report...")
            page.wait_for_timeout(2000)
            box = page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.textContent.trim().toLowerCase().includes('generate')) {
                        const rect = b.getBoundingClientRect();
                        return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
                return null;
            }""")
            if box:
                page.mouse.click(box['x'], box['y'])
                page.wait_for_timeout(5000)
                try:
                    page.wait_for_load_state("networkidle", timeout=60000)
                except Exception:
                    pass
                print("  Report generated")
            else:
                print("  ERROR: Could not find Generate button")
                return None

            # ── Download CSV ──────────────────────────────────────────────
            print("Downloading CSV...")
            page.wait_for_timeout(3000)

            # Try expect_download with mouse click
            box = page.evaluate("""() => {
                let btn = document.querySelector('[data-testing-id="csv-export-btn"]');
                if (!btn) {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.textContent.trim() === 'CSV') { btn = b; break; }
                    }
                }
                if (btn) {
                    const rect = btn.getBoundingClientRect();
                    return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
                return null;
            }""")

            if box:
                try:
                    with page.expect_download(timeout=30000) as dl_info:
                        page.mouse.click(box['x'], box['y'])
                    download = dl_info.value
                    filename = download.suggested_filename or f"Mailing_Report_{today}.csv"
                    csv_path = os.path.join(output_dir, filename)
                    download.save_as(csv_path)
                    print(f"  Downloaded: {filename}")
                except Exception:
                    print("  expect_download failed, trying direct click...")
                    page.mouse.click(box['x'], box['y'])
                    time.sleep(5)
                    # Check output_dir for any new CSV
                    csvs = [f for f in os.listdir(output_dir) if f.endswith('.csv')]
                    if csvs:
                        csv_path = os.path.join(output_dir, csvs[0])
                        print(f"  Found: {csvs[0]}")
            else:
                print("  ERROR: Could not find CSV button")

        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            context.close()
            browser.close()

    return csv_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download USPS EPS mailing report CSV")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output-dir", default="/tmp/eps-download")
    args = parser.parse_args()

    result = download_csv(args.username, args.password, args.output_dir)
    if result:
        print(f"\nCSV saved to: {result}")
    else:
        print("\nDownload failed.")
        sys.exit(1)
