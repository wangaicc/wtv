import base64
import glob
import json
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

EMAIL = os.environ.get("APP_EMAIL", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
KEY = os.environ.get("APP_KEY", "") or PASSWORD or "default_key"

BASE_URL = "https://feiniaoyun.top/"


def encrypt_text(text: str, key: str) -> str:
    key_bytes = key.encode("utf-8") or b"default_key"
    text_bytes = text.encode("utf-8")
    xor_bytes = bytes(
        [b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes)]
    )
    return base64.b64encode(xor_bytes).decode("utf-8")


def build_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--screen-info={0,0 1920x1080}")
    chrome_options.add_argument("--lang=zh-CN")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option(
        "excludeSwitches", ["enable-automation"]
    )
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )
    # 抹掉 navigator.webdriver 特征
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined})"
        },
    )
    driver.set_window_size(1920, 1080)
    return driver


def find_first(driver, selectors, timeout=15, clickable=False):
    """在多个候选选择器里找到第一个可用元素。"""
    end = time.time() + timeout
    cond = (
        EC.element_to_be_clickable
        if clickable
        else EC.presence_of_element_located
    )
    last_err = None
    while time.time() < end:
        for css in selectors:
            try:
                el = WebDriverWait(driver, 2).until(
                    cond((By.CSS_SELECTOR, css))
                )
                return el
            except Exception as e:
                last_err = e
        time.sleep(0.3)
    raise TimeoutException(
        f"未找到任一选择器: {selectors}; 最后错误: {last_err}"
    )


def dump_debug(driver, tag: str) -> None:
    """打印页面关键信息，便于排查。"""
    try:
        print(f"[DEBUG {tag}] url={driver.current_url}")
        print(f"[DEBUG {tag}] title={driver.title!r}")
        print(
            f"[DEBUG {tag}] body_len="
            f"{len(driver.find_element(By.TAG_NAME, 'body').text or '')}"
        )
        print(
            f"[DEBUG {tag}] inputs="
            f"{len(driver.find_elements(By.TAG_NAME, 'input'))}"
        )
    except Exception as e:
        print(f"[DEBUG {tag}] 读取页面信息失败: {e}")


driver = build_driver()
try:
    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 15)

    # 等页面 readyState 完成
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState")
            == "complete"
        )
    except Exception:
        pass

    time.sleep(2)
    dump_debug(driver, "登录页")

    # ===== 登录：邮箱 =====
    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[placeholder*="邮箱"]',
        'input[placeholder*="email"]',
        ".form-group:nth-child(2) > .form-control",
        'form input:not([type="password"])',
    ]
    email_input = find_first(
        driver, email_selectors, timeout=20, clickable=True
    )
    email_input.clear()
    email_input.send_keys(EMAIL)
    print("[INFO] 邮箱已输入")

    # ===== 登录：密码 =====
    password_selectors = [
        'input[type="password"]',
        'input[name="password"]',
        'input[placeholder*="密码"]',
        ".form-group:nth-child(3) > .form-control",
    ]
    password_input = find_first(
        driver, password_selectors, timeout=10, clickable=True
    )
    password_input.clear()
    password_input.send_keys(PASSWORD)
    print("[INFO] 密码已输入")

    # ===== 提交 =====
    try:
        login_btn = driver.find_element(
            By.CSS_SELECTOR, "button[type='submit'], .btn-primary"
        )
        login_btn.click()
    except Exception:
        password_input.send_keys(Keys.RETURN)
    print("[INFO] 已提交登录")

    # 等登录成功：URL 变化 或 出现登出/用户元素
    try:
        WebDriverWait(driver, 20).until(
            lambda d: "/login" not in d.current_url.lower()
            or len(d.find_elements(By.CSS_SELECTOR, ".ant-avatar, .user-info"))
            > 0
        )
        print(f"[INFO] 登录后 URL: {driver.current_url}")
    except Exception:
        dump_debug(driver, "登录后")
        raise RuntimeError("登录疑似失败：URL 未变化且无用户元素")

    time.sleep(2)

    # ===== 关闭可能的弹窗 =====
    try:
        close_btn = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".ant-modal-close-x, .modal-close")
            )
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except Exception:
        pass

    # ===== 打开订阅快捷面板 =====
    shortcut_selectors = [
        ".v2board-shortcuts-item:nth-child(2) > div:nth-child(1)",
        ".v2board-shortcuts-item:nth-child(2)",
        ".v2board-shortcuts-item",
    ]
    shortcut_item = find_first(
        driver, shortcut_selectors, timeout=15, clickable=True
    )
    driver.execute_script("arguments[0].click();", shortcut_item)
    time.sleep(2)

    # ===== 关闭居中的 modal（点击遮罩） =====
    try:
        modal_centered = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ant-modal-centered"))
        )
        driver.execute_script("arguments[0].click();", modal_centered)
        time.sleep(2)
    except Exception:
        pass

    # ===== 点击“订阅链接” =====
    subscribe_selectors = [
        ".subsrcibe-for-link > div:nth-child(2)",
        ".subscribe-for-link > div:nth-child(2)",
        "[class*='subscri']",
    ]
    subscribe_element = find_first(
        driver, subscribe_selectors, timeout=15, clickable=True
    )

    # 点击前先清空性能日志，避免错过请求
    try:
        driver.get_log("performance")
    except Exception:
        pass

    driver.execute_script("arguments[0].click();", subscribe_element)
    print("[INFO] 已点击订阅按钮，开始抓包…")

    # ===== 轮询性能日志，抓订阅链接 =====
    copied_text = ""
    deadline = time.time() + 15
    while time.time() < deadline and not copied_text:
        try:
            logs = driver.get_log("performance")
        except Exception:
            logs = []

        for log in logs:
            try:
                message = json.loads(log["message"])["message"]
                if message["method"] != "Network.responseReceived":
                    continue
                url = message["params"]["response"]["url"]
                if not any(
                    k in url
                    for k in ("subscribe", "user/getSubscribe", "user/info")
                ):
                    continue
                request_id = message["params"]["requestId"]
                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    )
                    data = json.loads(body["body"])
                except Exception:
                    continue

                if isinstance(data, dict):
                    payload = data.get("data", {})
                    if isinstance(payload, dict):
                        copied_text = (
                            payload.get("subscribe_url")
                            or payload.get("url")
                            or payload.get("link")
                            or ""
                        )
                    elif isinstance(payload, str) and payload.startswith(
                        "http"
                    ):
                        copied_text = payload
                if copied_text:
                    print(f"[INFO] 从网络响应抓到订阅链接")
                    break
            except Exception:
                continue

        if not copied_text:
            time.sleep(0.5)

    # ===== 兜底：DOM 中找 data-clipboard-text / window 变量 =====
    if not copied_text:
        try:
            copied_text = driver.execute_script(
                """
                var els = document.querySelectorAll('*');
                for (var i = 0; i < els.length; i++) {
                    var t = els[i].getAttribute('data-clipboard-text');
                    if (t && t.indexOf('http') === 0) return t;
                }
                return window.subscribe_url || '';
                """
            )
        except Exception:
            copied_text = ""

    if not copied_text or not str(copied_text).startswith("http"):
        dump_debug(driver, "抓取失败")
        raise RuntimeError(f"未能获取订阅链接，当前值: {copied_text!r}")

    print("[INFO] 订阅链接获取成功")

    # ===== 加密 =====
    encrypted_text = encrypt_text(str(copied_text), KEY)

    # ===== 目录处理 =====
    os.makedirs("feiniaoyun", exist_ok=True)

    for old_file in glob.glob("feiniaoyun/*.txt"):
        if os.path.basename(old_file) != "dy.txt":
            try:
                os.remove(old_file)
                print(f"已删除旧记录文件: {old_file}")
            except Exception as e:
                print(f"删除文件 {old_file} 失败: {e}")

    datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    datetime_file_path = f"feiniaoyun/{datetime_str}.txt"
    open(datetime_file_path, "w", encoding="utf-8").close()
    print(f"已创建空记录文件: {datetime_file_path}")

    dy_file_path = "feiniaoyun/dy.txt"
    old_content = ""
    if os.path.exists(dy_file_path):
        with open(dy_file_path, "r", encoding="utf-8") as f:
            old_content = f.read().strip()

    if old_content == encrypted_text:
        print("订阅内容未发生变化，保持 feiniaoyun/dy.txt 不变。")
    else:
        with open(dy_file_path, "w", encoding="utf-8") as f:
            f.write(encrypted_text)
        print("订阅内容已更新，成功写入 feiniaoyun/dy.txt！")

except Exception as e:
    print(f"执行出现错误: {e}")
    try:
        driver.save_screenshot("error.png")
        print("[INFO] 已保存 error.png")
    except Exception as shot_err:
        print(f"保存截图失败: {shot_err}")
    raise e

finally:
    driver.quit()
