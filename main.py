# main.py
import csv
import time
import random
import json
import re
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.desired_capabilities import DesiredCapabilities  # ←不要

# 画像サイズを 400x400 に寄せる
def to_400(url: str) -> str:
    if not url:
        return url
    url = re.sub(r'_(normal|200x200|bigger)', '_400x400', url)
    return url

def extract_from_ldjson(html: str):
    try:
        blocks = re.findall(
            r'<script type="application/ld\+json".*?>(\{.*?\})</script>',
            html, re.DOTALL
        )
        for raw in blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None

            if isinstance(data, dict):
                try:
                    url = data["author"]["image"]["contentUrl"]
                    if url:
                        return to_400(url)
                except Exception:
                    pass
                try:
                    url = data["mainEntity"]["image"]["contentUrl"]
                    if url:
                        return to_400(url)
                except Exception:
                    pass

            m = re.search(
                r'"contentUrl"\s*:\s*"(https://pbs\.twimg\.com/profile_images/[^"]+?\.(?:jpg|png))"',
                raw
            )
            if m:
                return to_400(m.group(1))
    except Exception:
        pass
    return None

def extract_from_img_tag(html: str):
    m = re.search(
        r'<img[^>]+src="(https://pbs\.twimg\.com/profile_images/[^"]+?_400x400\.(?:jpg|png))"',
        html
    )
    if m:
        return m.group(1)

    m2 = re.search(
        r'<img[^>]+src="(https://pbs\.twimg\.com/profile_images/[^"]+?\.(?:jpg|png))"',
        html
    )
    if m2:
        return to_400(m2.group(1))
    return None

def extract_from_network_logs(driver):
    try:
        logs = driver.get_log("performance")
    except Exception:
        return None
    candidates = []
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method", "")
            params = msg.get("params", {})
            url = None
            if method == "Network.responseReceived":
                url = params.get("response", {}).get("url")
            elif method == "Network.requestWillBeSent":
                url = params.get("request", {}).get("url")
            if url and "https://pbs.twimg.com/profile_images/" in url:
                candidates.append(url)
        except Exception:
            continue
    for url in candidates:
        if "_400x400" in url:
            return url
    for url in candidates:
        fixed = to_400(url)
        if fixed:
            return fixed
    return None

def get_html_content(account_id):
    options = Options()
    # CI向け（ヘッドレス & 実行環境のChromeを使用）
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=800,600")
    options.add_argument("--window-position=-10000,-10000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("accept-language=ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")

    # GitHub Actions で browser-actions/setup-chrome が出すパスに対応
    chrome_path = os.environ.get("CHROME_PATH") or os.environ.get("GOOGLE_CHROME_SHIM")
    if chrome_path:
        options.binary_location = chrome_path

    # network log 有効化
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
        })
        driver.execute_cdp_cmd("Network.enable", {})

        url = f"https://x.com/{account_id}"
        driver.get(url)

        time.sleep(random.uniform(3.5, 6.5))
        for _ in range(2):
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(random.uniform(0.5, 1.0))

        html = driver.page_source
        return driver, html
    except Exception as e:
        print(f"Error fetching HTML for {account_id}: {e}")
        try:
            driver.quit()
        except Exception:
            pass
        return None, None

def resolve_profile_image_url(account_id):
    driver, html = get_html_content(account_id)
    if not driver:
        return None
    try:
        url = extract_from_ldjson(html)
        if url:
            return url
        url = extract_from_img_tag(html)
        if url:
            return url
        url = extract_from_network_logs(driver)
        if url:
            return url
        return None
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def process_csv(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader]

    for row in rows:
        account_id = row[0].strip()
        print(f"\nProcessing {account_id} ...")
        url = resolve_profile_image_url(account_id)
        if url:
            print(f" -> {url}")
            row.append(url)
        else:
            print(" -> Failed to fetch URL")
            row.append("Failed to fetch URL")

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header + ["Profile Image URL"])
        writer.writerows(rows)

if __name__ == "__main__":
    csv_file_path = "accounts.csv"
    process_csv(csv_file_path)
