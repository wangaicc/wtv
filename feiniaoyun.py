import base64
import glob
import json
import os
import re
import time
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("APP_EMAIL", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
KEY = os.environ.get("APP_KEY", "") or PASSWORD or "default_key"

README_SOURCES = [
    "https://raw.githubusercontent.com/feiniaoyun/feiniaoyun/refs/heads/main/README.md",
    "https://raw.githubusercontent.com/feiniaoyun/feiniaoyun/main/README.md",
    "https://cdn.jsdelivr.net/gh/feiniaoyun/feiniaoyun@main/README.md",
    "https://ghproxy.net/https://raw.githubusercontent.com/feiniaoyun/feiniaoyun/main/README.md",
    "https://gh-proxy.com/https://raw.githubusercontent.com/feiniaoyun/feiniaoyun/main/README.md",
]
README_TIMEOUT = 15
LINK_RE = re.compile(r"https?://[^\s\)\]\>\"'，。、）】]+")
SKIP_HOST_MARKS = ("t.me", "github.com", "githubusercontent.com")

OUTPUT_DIR = "feiniaoyun"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

EMAIL_CSS = ", ".join([
    'input[type="email"]',
    'input[name="email"]',
    'input[placeholder*="邮箱"]',
    'input[placeholder*="email"]',
    '.form-group:nth-child(2) > .form-control',
    'form input:not([type="password"])',
])
PASSWORD_CSS = ", ".join([
    'input[type="password"]',
    'input[name="password"]',
    'input[placeholder*="密码"]',
    '.form-group:nth-child(3) > .form-control',
])
LOGIN_CSS = ", ".join([
    ".ant-avatar",
    ".user-info",
    ".v2board-shortcuts-item",
    "[class*='subscri']",
])
FAIL_CSS = ", ".join([
    ".ant-message-error",
    ".ant-alert-error",
    ".ant-form-item-explain-error",
    ".error-message",
])
SHORTCUT_CSS = ", ".join([
    ".v2board-shortcuts-item:nth-child(2) > div:nth-child(1)",
    ".v2board-shortcuts-item:nth-child(2)",
    ".v2board-shortcuts-item",
])
SUBSCRIBE_CSS = ", ".join([
    ".subsrcibe-for-link > div:nth-child(2)",
    ".subscribe-for-link > div:nth-child(2)",
    "[class*='subscri']",
])


def fetch_readme():
    for url in README_SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=README_TIMEOUT) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"[WARN] README 源不可用 {url} -> {type(exc).__name__}: {exc}")
            continue
        if "飞鸟云" not in text:
            print(f"[WARN] README 内容校验不通过: {url}")
            continue
        print(f"[INFO] README 来源: {url}")
        return text
    return None


def parse_domains(text):
    free_urls = []
    permanent_urls = []
    section = "free"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "永久" in line:
            section = "permanent"
        elif "免翻" in line:
            section = "free"
        for match in LINK_RE.finditer(line):
            link = match.group(0).rstrip(".,;:!?")
            host = urlparse(link).netloc.lower()
            if not host:
                continue
            if any(mark in host for mark in SKIP_HOST_MARKS):
                continue
            bucket = permanent_urls if section == "permanent" else free_urls
            if link not in bucket:
                bucket.append(link)
    return free_urls, permanent_urls


def build_candidates():
    text = fetch_readme()
    if not text:
        print("[ERROR] README 全部源均抓取失败，无可用域名")
        return [], "抓取失败"
    free_urls, permanent_urls = parse_domains(text)
    print(f"[INFO] 当日域名: 免翻 {len(free_urls)} 个 / 永久 {len(permanent_urls)} 个")
    for item in free_urls:
        print(f"  [免翻] {item}")
    for item in permanent_urls:
        print(f"  [永久] {item}")
    candidates = free_urls + permanent_urls
    if not candidates:
        print("[ERROR] README 未解析出任何可用域名")
        return [], "解析为空"
    return candidates, "当日 README"


def encrypt_text(text, key):
    key_bytes = key.encode("utf-8") or b"default_key"
    text_bytes = text.encode("utf-8")
    xor_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes)])
    return base64.b64encode(xor_bytes).decode("utf-8")


def dump_page(page, tag):
    try:
        print(f"[DEBUG {tag}] url={page.url}")
        print(f"[DEBUG {tag}] title={page.title()!r}")
        body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        print(f"[DEBUG {tag}] body_len={len(body)}")
        print(f"[DEBUG {tag}] body_preview={body[:200]!r}")
    except Exception as exc:
        print(f"[DEBUG {tag}] 读取页面信息失败: {exc}")


def looks_like_cloudflare(page):
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    for token in ("just a moment", "attention required", "cloudflare"):
        if token in title:
            return True
    try:
        html = page.content() or ""
    except Exception:
        html = ""
    for token in ("cf-browser-verification", "challenge-platform", "cf_chl_opt", "cf-challenge"):
        if token in html:
            return True
    return False


def fill_field(page, css, value, label):
    locator = page.locator(css).first
    try:
        locator.wait_for(state="visible", timeout=20000)
    except PlaywrightTimeoutError:
        raise RuntimeError(f"未找到{label}输入框")
    try:
        locator.fill(value, timeout=8000)
    except Exception:
        locator.click(timeout=8000)
        page.keyboard.type(value, delay=20)
    print(f"[INFO] {label}已输入")


def do_login(page, base_url):
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        raise RuntimeError("页面加载超时(30s)")
    except Exception as exc:
        raise RuntimeError(f"页面加载失败: {type(exc).__name__}: {str(exc)[:100]}")

    page.wait_for_timeout(2500)
    dump_page(page, "登录页")

    title = ""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    if "404" in page.url.lower() or "not found" in title.lower() or "页面不存在" in title:
        raise RuntimeError("域名指向 404 页面")

    if looks_like_cloudflare(page):
        print("[WARN] 检测到 Cloudflare 验证页，等待自动放行…")
        for _ in range(3):
            page.wait_for_timeout(4000)
            if not looks_like_cloudflare(page):
                break
        if looks_like_cloudflare(page):
            raise RuntimeError("Cloudflare 验证页未通过，跳过该域名")
        print("[INFO] Cloudflare 验证已通过")

    fill_field(page, EMAIL_CSS, EMAIL, "邮箱")
    fill_field(page, PASSWORD_CSS, PASSWORD, "密码")

    submit = page.locator("button[type='submit'], .btn-primary").first
    try:
        if submit.count() > 0 and submit.is_visible():
            submit.click(timeout=8000)
        else:
            page.keyboard.press("Enter")
    except Exception:
        page.keyboard.press("Enter")
    print("[INFO] 已提交登录")

    try:
        page.locator(LOGIN_CSS).first.wait_for(state="visible", timeout=25000)
        print(f"[INFO] 登录后 URL: {page.url}")
    except PlaywrightTimeoutError:
        dump_page(page, "登录后")
        if page.locator(FAIL_CSS).count() > 0:
            raise RuntimeError("登录失败：页面出现错误提示")
        raise RuntimeError("登录疑似失败：未出现用户元素")


def extract_from_payload(data):
    if not isinstance(data, dict):
        return ""
    payload = data.get("data")
    if isinstance(payload, dict):
        return payload.get("subscribe_url") or payload.get("url") or payload.get("link") or ""
    if isinstance(payload, str) and payload.startswith("http"):
        return payload
    return ""


def grab_subscribe(page):
    try:
        close_btn = page.locator(".ant-modal-close-x, .modal-close").first
        if close_btn.count() > 0:
            close_btn.click(timeout=5000)
            page.wait_for_timeout(800)
    except Exception:
        pass

    shortcut = page.locator(SHORTCUT_CSS).first
    try:
        shortcut.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        raise RuntimeError("未找到快捷面板入口")
    shortcut.click()
    page.wait_for_timeout(2000)

    try:
        modal = page.locator(".ant-modal-centered").first
        if modal.count() > 0:
            modal.click(timeout=5000)
            page.wait_for_timeout(2000)
    except Exception:
        pass

    subscribe = page.locator(SUBSCRIBE_CSS).first
    try:
        subscribe.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        raise RuntimeError("未找到订阅按钮")

    copied_text = ""
    try:
        with page.expect_response(
            lambda r: ("subscribe" in r.url.lower()) or ("user/info" in r.url.lower()),
            timeout=15000,
        ) as resp_info:
            subscribe.click()
        response = resp_info.value
        try:
            data = response.json()
        except Exception:
            data = {}
        copied_text = extract_from_payload(data)
        if copied_text:
            print("[INFO] 从网络响应抓到订阅链接")
    except PlaywrightTimeoutError:
        print("[WARN] 未捕获订阅接口响应，尝试页面兜底提取")

    if not copied_text:
        try:
            copied_text = page.evaluate(
                """() => {
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const t = el.getAttribute('data-clipboard-text');
                        if (t && t.indexOf('http') === 0) return t;
                    }
                    return window.subscribe_url || '';
                }"""
            ) or ""
        except Exception:
            copied_text = ""

    if not copied_text or not str(copied_text).startswith("http"):
        dump_page(page, "抓取失败")
        raise RuntimeError(f"未能获取订阅链接，当前值: {str(copied_text)!r}")

    print("[INFO] 订阅链接获取成功")
    return str(copied_text)


def save_result(encrypted_text):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for old_file in glob.glob(f"{OUTPUT_DIR}/*.txt"):
        if os.path.basename(old_file) != "dy.txt":
            try:
                os.remove(old_file)
                print(f"已删除旧记录文件: {old_file}")
            except Exception as e:
                print(f"删除文件 {old_file} 失败: {e}")

    datetime_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    datetime_file_path = f"{OUTPUT_DIR}/{datetime_str}.txt"
    open(datetime_file_path, "w", encoding="utf-8").close()
    print(f"已创建空记录文件: {datetime_file_path}")

    dy_file_path = f"{OUTPUT_DIR}/dy.txt"
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


def main():
    if not EMAIL or not PASSWORD:
        print("[ERROR] 未设置 APP_EMAIL / APP_PASSWORD 环境变量，无法登录")
        return 2

    candidates, source = build_candidates()
    print(f"[INFO] 候选域名 {len(candidates)} 个，来源: {source}")
    if not candidates:
        print("[ERROR] 无可用域名，任务终止")
        return 1

    subscribe_url = ""
    used_url = ""
    failures = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--lang=zh-CN",
            ],
        )
        try:
            for index, base_url in enumerate(candidates, 1):
                print(f"\n[TRY {index}/{len(candidates)}] {base_url}")
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                    user_agent=USER_AGENT,
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.set_default_timeout(15000)
                page.set_default_navigation_timeout(30000)
                try:
                    do_login(page, base_url)
                    subscribe_url = grab_subscribe(page)
                    used_url = base_url
                    print(f"[SUCCESS] {base_url} 全流程成功，停止轮询")
                    break
                except Exception as exc:
                    failures.append((base_url, f"{type(exc).__name__}: {exc}"))
                    print(f"[FAIL] {base_url} -> {type(exc).__name__}: {exc}")
                    try:
                        page.screenshot(path=f"error_{index}.png", full_page=False)
                    except Exception:
                        pass
                    continue
                finally:
                    try:
                        context.close()
                    except Exception:
                        pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

    if not subscribe_url:
        print("\n[ERROR] 全部域名均失败：")
        for url, reason in failures:
            print(f"  - {url}: {reason}")
        raise RuntimeError(f"{len(candidates)} 个域名全部登录/抓取失败")

    encrypted_text = encrypt_text(subscribe_url, KEY)
    save_result(encrypted_text)
    print(f"[DONE] 使用域名: {used_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
