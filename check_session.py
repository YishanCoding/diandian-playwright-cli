"""
Cookie/Session 有效性快速检测（v2）
用法: python3 check_cookies.py
返回码: 0=有效  1=无效/不存在

支持两种 session 文件格式：
  /tmp/diandian_session.json  (v2 格式，含 localStorage，优先使用)
  /tmp/diandian_cookies.json  (v1 格式，仅 Cookies)
"""
import json, os, sys, re, subprocess, time
from playwright.sync_api import sync_playwright

SESSION_PATH = '/tmp/diandian_session.json'
COOKIES_PATH = '/tmp/diandian_cookies.json'

# 使用一个真正需要登录的 API 来验证（不认证返回 401 或跳转）
CHECK_API = 'https://api.diandian.com/pc/app/v2/top/list'
CHECK_APP_URL = 'https://app.diandian.com/aso/keyword-research'  # 登录后才可访问的功能页


def setup_system_proxy():
    try:
        out = subprocess.check_output(['scutil', '--proxy'], text=True)
        if re.search(r'HTTPEnable\s*:\s*1', out):
            host = re.search(r'HTTPProxy\s*:\s*(\S+)', out)
            port = re.search(r'HTTPPort\s*:\s*(\d+)', out)
            if host and port:
                proxy_url = f'http://{host.group(1)}:{port.group(1)}'
                os.environ['HTTP_PROXY'] = proxy_url
                os.environ['HTTPS_PROXY'] = proxy_url
    except Exception:
        pass


def load_session(context, page):
    """加载 session（优先 v2 格式，含 localStorage）"""
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH) as f:
            session = json.load(f)
        context.add_cookies(session.get('cookies', []))
        local_storage = session.get('localStorage', {})
        if local_storage:
            origin = session.get('origin', 'https://app.diandian.com')
            # 先导航到 origin 才能设置 localStorage
            page.goto(origin, timeout=15000)
            page.evaluate(
                '(data) => { for (const [k, v] of Object.entries(data)) { localStorage.setItem(k, v); } }',
                local_storage
            )
        return 'v2', len(session.get('cookies', [])), len(local_storage)
    elif os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH) as f:
            context.add_cookies(json.load(f))
        return 'v1', 0, 0
    else:
        return None, 0, 0


def check():
    if not os.path.exists(SESSION_PATH) and not os.path.exists(COOKIES_PATH):
        print('❌ Session 文件不存在，请先运行 references/login-script-v2.py')
        return False

    api_status = []

    with sync_playwright() as p:
        setup_system_proxy()
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        fmt, n_cookies, n_ls = load_session(context, page)
        if fmt is None:
            print('❌ Session 文件不存在')
            return False

        # 拦截 API 请求来检测认证状态
        def on_response(response):
            if 'api.diandian.com' in response.url and response.status in (200, 401, 403):
                api_status.append((response.status, response.url))

        page.on('response', on_response)

        try:
            # 访问需要登录的 SERP 页面（SPA，不用 networkidle）
            page.goto('https://app.diandian.com/search/ios-1-5-5-24-0-funko%20pop', timeout=20000)
            time.sleep(8)  # SPA 必须等待渲染

            if '/login' in page.url:
                print('❌ Session 已失效（跳转到登录页）')
                return False

            body = page.inner_text('body')
            # 未登录时显示 "Login & Sign up" 和 "Example Image"
            if 'Login & Sign up' in body and 'Example Image' in body:
                print('❌ Session 已失效（页面显示未登录状态）')
                return False
            if '登录' in body and '密码' in body:
                print('❌ Session 已失效（中文登录表单）')
                return False

            print(f'✅ Session 有效 (格式: {fmt}, cookies: {n_cookies}, localStorage: {n_ls} 项)')
            return True

        except Exception as e:
            print(f'❌ 检测失败: {e}')
            return False
        finally:
            browser.close()


if __name__ == '__main__':
    sys.exit(0 if check() else 1)
