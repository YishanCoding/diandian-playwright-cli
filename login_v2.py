"""
点点数据登录脚本 v2 - 同时保存 Cookies + localStorage（认证 token）
用法: python3 login-script-v2.py
保存到: /tmp/diandian_session.json

背景：diandian 的认证 token 存储在 localStorage（JWT），
      旧版 login-script.py 只保存 Cookies 会导致后续自动化无法认证。
"""
import sys
from playwright.sync_api import sync_playwright
import json, time

SESSION_PATH = '/tmp/diandian_session.json'

print('启动浏览器...', flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # 拦截登录成功的 API 响应
    login_detected = []
    def on_response(response):
        url = response.url
        # 捕获任何返回 token 的 API 响应
        if 'api.diandian.com' in url and response.status == 200:
            try:
                body = response.json()
                # 通常登录成功的 API 返回 token 或 user 信息
                if isinstance(body, dict) and body.get('code') == 0:
                    data = body.get('data', {})
                    if isinstance(data, dict) and ('token' in str(data) or 'user' in str(data).lower()):
                        login_detected.append(url)
                        print(f'  检测到登录 API: {url}', flush=True)
            except Exception:
                pass

    page.on('response', on_response)
    page.goto('https://app.diandian.com/login')

    print('请在浏览器中手动登录（支持扫码/账密），登录完成后按回车键保存...', flush=True)
    print('（也可以等待自动检测，最多 5 分钟）', flush=True)

    import threading
    enter_pressed = [False]
    def wait_for_enter():
        input()
        enter_pressed[0] = True
    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()

    saved_ls = {}  # 在检测到时立即保存，避免页面跳转后丢失

    for i in range(150):
        time.sleep(2)

        # 方式 1: 用户按了回车
        if enter_pressed[0]:
            print('收到回车，立即保存...', flush=True)
            break

        # 方式 2: URL 跳出了 /login
        if '/login' not in page.url and 'diandian.com' in page.url:
            print(f'检测到跳转: {page.url}', flush=True)
            time.sleep(3)
            break

        # 方式 3: localStorage 已有认证信息
        try:
            ls = page.evaluate("() => Object.assign({}, window.localStorage)")
            if ls and any(k for k in ls if 'token' in k.lower() or 'user' in k.lower() or 'auth' in k.lower()):
                print(f'检测到 localStorage 认证数据: {list(ls.keys())}', flush=True)
                saved_ls = ls  # 立即保存值，页面跳转后仍可用
                time.sleep(2)
                break
        except Exception:
            pass

        if i % 5 == 0:
            print(f'  等待中... {i*2}s / 300s  当前 URL: {page.url}', flush=True)
    else:
        print('超时 5 分钟，尝试强制保存当前状态...', flush=True)

    # 无论如何都保存
    try:
        cookies = context.cookies()
        # 优先使用检测时已保存的值，否则再尝试从当前页面读取
        if saved_ls:
            local_storage = saved_ls
        else:
            try:
                local_storage = page.evaluate("() => Object.assign({}, window.localStorage)")
            except Exception as e:
                print(f'  localStorage 获取失败: {e}', flush=True)
                local_storage = {}

        session = {
            'cookies': cookies,
            'localStorage': local_storage,
            'origin': 'https://app.diandian.com',
            'saved_url': page.url,
        }

        with open(SESSION_PATH, 'w') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        print(f'\n✅ 已保存到 {SESSION_PATH}', flush=True)
        print(f'   Cookies: {len(cookies)} 个', flush=True)
        print(f'   localStorage: {len(local_storage)} 项', flush=True)
        if local_storage:
            print(f'   localStorage 键: {list(local_storage.keys())}', flush=True)
        else:
            print('   ⚠️  localStorage 为空，可能需要等待页面完全加载后再按回车', flush=True)

    except Exception as e:
        print(f'❌ 保存失败: {e}', flush=True)
        sys.exit(1)

    browser.close()
    print('完成。', flush=True)
