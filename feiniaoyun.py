import os
import time
import json
import base64
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

EMAIL = os.environ.get("APP_EMAIL", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
KEY = os.environ.get("APP_KEY", "") or PASSWORD or "default_key"

def encrypt_text(text: str, key: str) -> str:
    key_bytes = key.encode("utf-8")
    if not key_bytes:
        key_bytes = b"default_key"
    text_bytes = text.encode("utf-8")
    xor_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes)])
    return base64.b64encode(xor_bytes).decode("utf-8")

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

try:
    driver.get("https://feiniaoyun.top/")
    wait = WebDriverWait(driver, 15)

    email_input = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".form-group:nth-child(2) > .form-control"))
    )
    email_input.clear()
    email_input.send_keys(EMAIL)

    password_input = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".form-group:nth-child(3) > .form-control"))
    )
    password_input.clear()
    password_input.send_keys(PASSWORD)

    try:
        login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .btn-primary")
        login_btn.click()
    except Exception:
        password_input.send_keys(Keys.RETURN)

    time.sleep(3)

    try:
        close_btn = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ant-modal-close-x, .modal-close"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except Exception:
        pass

    shortcut_item = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".v2board-shortcuts-item:nth-child(2) > div:nth-child(1)"))
    )
    driver.execute_script("arguments[0].click();", shortcut_item)
    time.sleep(2)

    modal_centered = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".ant-modal-centered"))
    )
    driver.execute_script("arguments[0].click();", modal_centered)
    time.sleep(2)

    subscribe_element = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".subsrcibe-for-link > div:nth-child(2)"))
    )
    driver.execute_script("arguments[0].click();", subscribe_element)
    time.sleep(3)

    copied_text = ""
    logs = driver.get_log("performance")

    for log in logs:
        try:
            message = json.loads(log["message"])["message"]
            if message["method"] == "Network.responseReceived":
                url = message["params"]["response"]["url"]
                if "subscribe" in url or "user/getSubscribe" in url or "user/info" in url:
                    request_id = message["params"]["requestId"]
                    try:
                        response_body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                        body_data = json.loads(response_body["body"])
                        
                        if isinstance(body_data, dict):
                            data = body_data.get("data", {})
                            if isinstance(data, dict):
                                copied_text = data.get("subscribe_url") or data.get("url") or data.get("link")
                            elif isinstance(data, str) and data.startswith("http"):
                                copied_text = data
                        
                        if copied_text:
                            break
                    except Exception:
                        continue
        except Exception:
            continue

    if not copied_text:
        copied_text = driver.execute_script("""
            var elements = document.querySelectorAll('*');
            for (var i = 0; i < elements.length; i++) {
                var text = elements[i].getAttribute('data-clipboard-text');
                if (text && text.startsWith('http')) return text;
            }
            return window.subscribe_url || '';
        """)

    encrypted_text = encrypt_text(str(copied_text), KEY)

    os.makedirs("feiniaoyun", exist_ok=True)

    with open("feiniaoyun/dy.txt", "w", encoding="utf-8") as f:
        f.write(encrypted_text)

    print("已成功写入加密文件到 feiniaoyun/dy.txt！")

except Exception as e:
    print(f"执行出现错误: {e}")
    driver.save_screenshot("error.png")
    raise e

finally:
    driver.quit()
