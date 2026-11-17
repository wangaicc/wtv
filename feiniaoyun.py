import base64
import glob
import json
import os
import re
import time
import urllib.error
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
HTTP_TIMEOUT = 20
SUBSCRIPTION_PATH = "/api/v1/user/getSubscribe"

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
FAIL_CSS = ", ".join([
    ".ant-message-error",
    ".ant-alert-error",
    ".ant-form-item-explain-error",
    ".error-message",
])
OVERLAY_CSS = """
#crisp-chatbox, .crisp-client, [id^="crisp"], [class*="crisp"],
[id*="kefu"], [class*="kefu"], iframe[src*="crisp"], iframe[src*="gptkefu"],
[id*="gptkefu"], [class*="gptkefu"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
"""


class CredentialRejected(Exception):
    pass


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


def api_call(base, path, method="GET", payload=None, token=None, timeout=HTTP_TIMEOUT):
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Referer": base + "/",
        "Origin": base,
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def extract_from_payload(data):
    if not isinstance(data, dict):
        return ""
    payload = data.get("data")
    if isinstance(payload, dict):
        return payload.get("subscribe_url") or payload.get("url") or payload.get("link") or ""
    if isinstance(payload, str) and payload.startswith("http"):
        return payload
    return ""


def api_login(base):
    status, body = api_call(
        base,
        "/api/v1/passport/auth/login",
        method="POST",
        payload={"email": EMAIL, "password": PASSWORD},
    )
    try:
        data = json.loads(body)
    except Exception:
        raise RuntimeError(f"登录接口返回非 JSON (status={status})")
    if status == 422 and isinstance(data.get("errors"), dict):
        errors = json.dumps(data.get("errors"), ensure_ascii=False)[:120]
        raise CredentialRejected(f"登录参数被拒 (422): {errors}")
    if status != 200:
        message = str(data.get("message") or body[:120])
        lowered = message.lower()
        if "密码" in message or "账号" in message or "credentials" in lowered or "invalid" in lowered:
            raise CredentialRejected(f"登录被拒 (status={status}): {message}")
        raise RuntimeError(f"登录失败 (status={status}): {message}")
    payload = data.get("data") or {}
    auth_values = []
    for key in ("auth_data", "authData", "token"):
        value = payload.get(key)
        if value:
            auth_values.append(str(value))
    if not auth_values:
        raise RuntimeError(f"登录成功但无鉴权字段，字段: {sorted((payload or {}).keys())}")
    print(f"[INFO] HTTP 登录成功，返回字段: {sorted((payload or {}).keys())}")
    return auth_values


def api_subscribe(base, auth_values):
    for value in auth_values:
        for auth in (value, f"Bearer {value}"):
            status, body = api_call(base, SUBSCRIPTION_PATH, token=auth)
            if status != 200:
                print(f"[DEBUG] getSubscribe status={status} auth_len={len(auth)}")
                continue
            try:
                data = json.loads(body)
            except Exception:
                continue
            subscribe_url = extract_from_payload(data)
            if subscribe_url:
                return subscribe_url
    raise RuntimeError("getSubscribe 未返回订阅链接")


def try_http(candidates):
    for base in candidates:
        try:
            auth_values = api_login(base)
            subscribe_url = api_subscribe(base, auth_values)
            print(f"[HTTP OK] {base} 取到订阅链接")
            return base, subscribe_url
        except CredentialRejected:
            raise
        except Exception as exc:
            print(f"[HTTP FAIL] {base} -> {type(exc).__name__}: {exc}")
            continue
    return None, None


def dump_page(page, tag):
    try:
        print(f"[DEBUG {tag}] url={page.url}")
        print(f"[DEBUG {tag}] title={page.title()!r}")
        body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        print(f"[DEBUG {tag}] body_preview={body[:200]!r}")
    except Exception as exc:
        print(f"[DEBUG {tag}] 读取页面信息失败: {exc}")


def hide_overlays(page):
    try:
        page.add_style_tag(content=OVERLAY_CSS)
    except Exception:
        pass


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


def page_fetch_subscribe(page):
    try:
        return page.evaluate(
            """async () => {
                try {
                    const r = await fetch('/api/v1/user/getSubscribe', {credentials: 'include'});
                    if (r.status !== 200) return {status: r.status, url: ''};
                    const j = await r.json();
                    const d = (j && j.data) || {};
                    const url = d.subscribe_url || d.url || d.link || '';
                    return {status: 200, url: url};
                } catch (e) {
                    return {status: 0, url: '', err: String(e).slice(0, 80)};
                }
            }"""
        )
    except Exception as exc:
        return {"status": 0, "url": "", "err": str(exc)[:80]}


def browser_flow(page, base_url):
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        raise RuntimeError("页面加载超时(30s)")
    except Exception as exc:
        raise RuntimeError(f"页面加载失败: {type(exc).__name__}: {str(exc)[:100]}")

    hide_overlays(page)
    page.wait_for_timeout(2500)
    dump_page(page, "登录页")

    if looks_like_cloudflare(page):
        print("[WARN] 检测到 Cloudflare 验证页，等待自动放行…")
        for _ in range(3):
            page.wait_for_timeout(4000)
            if not looks_like_cloudflare(page):
                break
        if looks_like_cloudflare(page):
            raise RuntimeError("Cloudflare 验证页未通过，跳过该域名")

    hide_overlays(page)
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

    deadline = time.time() + 30
    last_status = 0
    while time.time() < deadline:
        result = page_fetch_subscribe(page)
        last_status = result.get("status", 0)
        if last_status == 200 and result.get("url"):
            print("[INFO] 登录态已建立，getSubscribe 返回订阅链接")
            return result["url"]
        if page.locator(FAIL_CSS).count() > 0:
            dump_page(page, "登录失败")
            raise CredentialRejected("页面出现登录错误提示（账号或密码被拒）")
        page.wait_for_timeout(1000)

    dump_page(page, "取订阅超时")
    raise RuntimeError(f"登录后 getSubscribe 未返回订阅链接 (last_status={last_status})")


def try_browser(pw, candidates):
    failures = []
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
            print(f"\n[BROWSER TRY {index}/{len(candidates)}] {base_url}")
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
                subscribe_url = browser_flow(page, base_url)
                print(f"[BROWSER OK] {base_url} 取到订阅链接")
                return base_url, subscribe_url
            except CredentialRejected:
                try:
                    page.screenshot(path=f"error_{index}.png")
                except Exception:
                    pass
                raise
            except Exception as exc:
                failures.append((base_url, f"{type(exc).__name__}: {exc}"))
                print(f"[BROWSER FAIL] {base_url} -> {type(exc).__name__}: {exc}")
                try:
                    page.screenshot(path=f"error_{index}.png")
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
    print("\n[ERROR] Playwright 通道全部域名失败：")
    for url, reason in failures:
        print(f"  - {url}: {reason}")
    return None, None


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

    used_url = ""
    subscribe_url = ""

    try:
        print("[STAGE 1] HTTP 直连接口通道")
        used_url, subscribe_url = try_http(candidates)
    except CredentialRejected as exc:
        print(f"[FATAL] {exc}")
        return 3

    if not subscribe_url:
        print("[STAGE 2] Playwright 通道")
        try:
            with sync_playwright() as pw:
                used_url, subscribe_url = try_browser(pw, candidates)
        except CredentialRejected as exc:
            print(f"[FATAL] {exc}")
            return 3

    if not subscribe_url:
        raise RuntimeError(f"{len(candidates)} 个域名在 HTTP 与 Playwright 两个通道均失败")

    print(f"[INFO] 订阅链接来源域名: {used_url}")
    save_result(encrypt_text(subscribe_url, KEY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
