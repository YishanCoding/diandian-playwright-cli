"""
点点数据 ASO 数据查询工具 v4.1
使用 Playwright 浏览器自动化，绕过 API 签名验证，直接获取真实数据。
认证：优先读取 v2 session（/tmp/diandian_session.json，含 localStorage），
      兼容旧版 cookie 文件（diandian_cookies.json）。
"""
import asyncio
import json
import argparse
import sys
import os
import re
import subprocess
from typing import Dict, Any, List, Optional, Tuple

SESSION_PATH = '/tmp/diandian_session.json'
COOKIES_PATH = os.path.join(os.path.dirname(__file__), 'diandian_cookies.json')


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
                return proxy_url
    except Exception:
        pass
    return None


def load_session() -> Tuple[List[Dict], Dict]:
    """返回 (cookies, local_storage)。优先 v2 格式，兼容 v1。"""
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH) as f:
            session = json.load(f)
        cookies_raw = session.get('cookies', [])
        local_storage = session.get('localStorage', {})
        # 统一格式：确保每个 cookie 有 name/value
        cookies = [c for c in cookies_raw if c.get('name') and c.get('value')]
        return cookies, local_storage
    elif os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH) as f:
            data = json.load(f)
        if isinstance(data, dict):
            cookies = [{"name": k, "value": v} for k, v in data.items()]
        else:
            cookies = data
        return cookies, {}
    else:
        print(f"❌ Session 文件不存在，请先运行: python3 login_v2.py")
        sys.exit(1)


async def fetch_keyword_data(keyword: str, country: int = 75, debug: bool = False) -> Optional[Dict]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 需要安装 playwright: pip install playwright && playwright install chromium")
        sys.exit(1)

    cookies, local_storage = load_session()
    results = []
    setup_system_proxy()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 注入 Cookies
        for c in cookies:
            name = c.get("name", c.get("key", ""))
            value = c.get("value", "")
            if not name or not value:
                continue
            for domain in [".diandian.com", "app.diandian.com", "api.diandian.com"]:
                try:
                    await context.add_cookies([{
                        "name": name, "value": value,
                        "domain": domain, "path": "/"
                    }])
                except Exception:
                    pass

        # 注入 localStorage（v2 auth，Vue SPA 初始化时需要）
        if local_storage:
            ls_script = 'Object.entries(' + json.dumps(local_storage) + ').forEach(([k,v]) => localStorage.setItem(k,v));'
            await context.add_init_script(ls_script)

        page = await context.new_page()

        async def handle_response(response):
            url = response.url
            # Capture any word/search or search_all API responses
            if "api.diandian.com/pc/app" in url and ("word/search" in url or "search_all" in url):
                try:
                    body = await response.json()
                    if debug:
                        print(f"  [DEBUG] 捕获 API 响应: {url[:120]}", file=sys.stderr)
                    results.append({"url": url, "body": body})
                except Exception:
                    pass

        page.on("response", handle_response)

        page_url = f"https://app.diandian.com/search/ios-1-5-5-{country}-0-{keyword}"
        if debug:
            print(f"  [DEBUG] 加载页面: {page_url}", file=sys.stderr)

        try:
            await page.goto(page_url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            if debug:
                print(f"  [DEBUG] 页面加载状态: {e}", file=sys.stderr)

        # Wait for additional async API calls
        await asyncio.sleep(6)
        await browser.close()

    if results:
        return results[0]["body"]
    return None


def parse_aso_report(data: Dict, keyword: str) -> Dict[str, Any]:
    """Parse API response into a structured ASO report."""
    word_info = data.get("word", {})
    apps_list = data.get("list", [])

    search_traffic = word_info.get("search_traffic", -99999)
    if search_traffic == -99999:
        search_traffic_str = "无数据 (账号权限不足或该词量极小)"
    else:
        search_traffic_str = str(search_traffic)

    popularity = word_info.get("popularity", 0)
    results_count = word_info.get("results_count", 0)

    # Find jujubit or target app in results
    target_rank = None
    target_app = None
    for i, item in enumerate(apps_list):
        app = item.get("app", {})
        app_name = app.get("name", "")
        bundle_id = app.get("bundle_id", "")
        if keyword.lower() in app_name.lower() or keyword.lower() in bundle_id.lower():
            target_rank = i + 1
            target_app = app
            break

    ranked_apps = []
    for i, item in enumerate(apps_list):
        app = item.get("app", {})
        ranked_apps.append({
            "rank": i + 1,
            "name": app.get("name", "-"),
            "app_id": app.get("app_id", "-"),
            "bundle_id": app.get("bundle_id", "-"),
            "developer": app.get("developer", {}).get("name", "-"),
        })

    return {
        "keyword": keyword,
        "search_traffic": search_traffic_str,
        "popularity": popularity,
        "results_count": results_count,
        "target_rank": target_rank,
        "target_app": target_app,
        "ranked_apps": ranked_apps,
    }


def print_report(report: Dict, output_format: str = "table"):
    keyword = report["keyword"]
    print(f"\n{'=' * 65}")
    print(f"🔍 关键词 ASO 报告: {keyword}")
    print(f"{'=' * 65}")
    print(f"  搜索量: {report['search_traffic']}")
    print(f"  热度指数: {report['popularity']}")
    print(f"  搜索结果数: {report['results_count']}")

    if report["target_rank"] is not None:
        app = report["target_app"]
        print(f"\n  ✅ [{keyword}] 在关键词 '{keyword}' 的搜索结果中排名: #{report['target_rank']}")
        print(f"     App 名称: {app.get('name', '-')}")
        print(f"     开发者: {app.get('developer', {}).get('name', '-')}")
    else:
        print(f"\n  ⚠️  未在前 {len(report['ranked_apps'])} 名中找到含 '{keyword}' 的 App")

    if report["ranked_apps"]:
        print(f"\n{'─' * 65}")
        print(f"  搜索结果排名 (前 {min(10, len(report['ranked_apps']))} 名):")
        print(f"{'─' * 65}")
        print(f"  {'排名':<6} {'App 名称':<30} {'App ID':<12}")
        print(f"  {'─'*6} {'─'*30} {'─'*12}")
        for item in report["ranked_apps"][:10]:
            print(f"  {item['rank']:<6} {str(item['name'])[:30]:<30} {str(item['app_id']):<12}")

    print(f"{'=' * 65}")

    if output_format == "json":
        print("\n--- JSON 报告 ---")
        print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="点点数据 ASO 数据查询工具 v4.0 (Playwright)")
    parser.add_argument("keyword", help="目标关键词")
    parser.add_argument("--country", type=int, default=75, help="国家代码 (75=美国, 24=中国)")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    parser.add_argument("--json", action="store_true", help="额外输出 JSON 格式")
    args = parser.parse_args()

    if not args.debug:
        import warnings
        warnings.filterwarnings("ignore")

    print(f"🔍 查询关键词: {args.keyword}  国家代码: {args.country}")

    data = asyncio.run(fetch_keyword_data(args.keyword, args.country, debug=args.debug))

    if data is None:
        print("❌ 未能获取 API 数据。可能原因:")
        print("   1) Cookie 已过期")
        print("   2) 代理 127.0.0.1:1082 不可用")
        print("   3) 该关键词在指定国家无数据")
        sys.exit(1)

    if data.get("code") != 0:
        print(f"❌ API 返回错误: code={data.get('code')} msg={data.get('msg')}")
        sys.exit(1)

    report = parse_aso_report(data.get("data", {}), args.keyword)
    print_report(report, output_format="json" if args.json else "table")


if __name__ == "__main__":
    main()
