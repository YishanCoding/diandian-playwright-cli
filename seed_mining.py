"""
种子词竞品挖掘主流程
用法: python3 seed_mining.py --seeds "funko pop,warhammer,imvu,anime" --output /tmp/seed_results

流程:
  1. 验证 Cookie
  2. 对每个种子词，搜索 App Store 搜索结果页（SERP），提取 TOP10 App
  3. 查看每个 App 的关键词覆盖量
  4. 选择覆盖量最大的 top_n 个 App（可配置）
  5. API 拦截获取完整关键词列表
  6. 筛选（P≥min_p, SI≥min_si, rank≤max_rank）
  7. 保存结果到 output 目录

输出文件:
  <output>/<seed>_serp.json     # SERP + 覆盖量
  <output>/<seed>_keywords.json # 竞品关键词
  <output>/summary.json         # 全部结果汇总
"""
import json, time, re, os, sys, argparse, subprocess
from playwright.sync_api import sync_playwright
from urllib.parse import quote


def setup_system_proxy():
    """从 macOS 系统代理设置中读取 HTTP 代理，通过环境变量注入（Playwright headless 兼容方式）"""
    try:
        out = subprocess.check_output(['scutil', '--proxy'], text=True)
        if re.search(r'HTTPEnable\s*:\s*1', out):
            host = re.search(r'HTTPProxy\s*:\s*(\S+)', out)
            port = re.search(r'HTTPPort\s*:\s*(\d+)', out)
            if host and port:
                proxy_url = f'http://{host.group(1)}:{port.group(1)}'
                os.environ['HTTP_PROXY'] = proxy_url
                os.environ['HTTPS_PROXY'] = proxy_url
                print(f'  系统代理: {proxy_url}')
                return proxy_url
    except Exception:
        pass
    return None

SESSION_PATH = '/tmp/diandian_session.json'
COOKIES_PATH = '/tmp/diandian_cookies.json'  # v1 backward compat

# ─── Session 加载 ──────────────────────────────────────────────────────────

def load_session(context):
    """加载 session（优先 v2 格式含 localStorage，兼容旧版 Cookies 格式）"""
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH) as f:
            session = json.load(f)
        context.add_cookies(session.get('cookies', []))
        return session.get('localStorage', {}), session.get('origin', 'https://app.diandian.com')
    elif os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH) as f:
            context.add_cookies(json.load(f))
        return {}, 'https://app.diandian.com'
    else:
        print('❌ Session 文件不存在，请先运行 references/login-script-v2.py')
        sys.exit(1)


def restore_local_storage(page, local_storage, origin):
    """在页面 origin 上恢复 localStorage"""
    if not local_storage:
        return
    page.goto(origin, timeout=15000)
    page.evaluate(
        '(data) => { for (const [k, v] of Object.entries(data)) { localStorage.setItem(k, v); } }',
        local_storage
    )


def load_and_validate_session(context):
    local_storage, origin = load_session(context)
    page = context.new_page()
    try:
        restore_local_storage(page, local_storage, origin)
        page.goto('https://app.diandian.com/search/ios-1-5-5-24-0-funko%20pop', timeout=20000)
        time.sleep(8)
        if '/login' in page.url:
            print('❌ Session 已失效，请重新运行 references/login-script-v2.py')
            sys.exit(1)
        body = page.inner_text('body')
        if 'Login & Sign up' in body and 'Example Image' in body:
            print('❌ Session 已失效（未登录状态），请重新运行 references/login-script-v2.py')
            sys.exit(1)
        if '登录' in body and '密码' in body:
            print('❌ Session 已失效（中文登录表单），请重新运行 references/login-script-v2.py')
            sys.exit(1)
        ls_note = f'（含 {len(local_storage)} 个 localStorage 项）' if local_storage else '（仅 Cookies）'
        print(f'✅ Session 有效 {ls_note}')
        return page  # 返回已验证的 page，供后续复用
    except SystemExit:
        raise
    except Exception as e:
        print(f'❌ Session 验证失败: {e}')
        sys.exit(1)

# ─── Step 1: SERP → TOP10 ───────────────────────────────────────────────────

def get_serp_top10(page, keyword):
    url = f'https://app.diandian.com/search/ios-1-5-5-24-0-{quote(keyword)}'
    print(f'\n  [SERP] {url}')

    for attempt in range(2):
        try:
            page.goto(url, timeout=30000)
            time.sleep(8)
            break
        except Exception as e:
            if attempt == 1:
                print(f'  SERP 加载失败: {e}')
                return []
            print(f'  重试...')
            time.sleep(5)

    links = page.eval_on_selector_all('a[href*="/app/"]', '''
        els => els.map(e => ({text: e.innerText.trim().substring(0, 100), href: e.href}))
            .filter(e => e.text.length > 2 && e.text.length < 80)
    ''')

    seen = set()
    top10 = []
    for link in links:
        match = re.search(r'/app/([^/]+)/', link['href'])
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            top10.append({'name': link['text'], 'internal_id': match.group(1), 'coverage': 0, 'rank': len(top10) + 1})
        if len(top10) >= 10:
            break

    print(f'  找到 {len(top10)} 个 App')
    return top10

# ─── Step 2: 覆盖量 ──────────────────────────────────────────────────────────

def get_coverage(page, app):
    aso_url = f'https://app.diandian.com/app/{app["internal_id"]}/ios-aso?market=1&country=24&system=4'
    for attempt in range(2):
        try:
            page.goto(aso_url, timeout=30000)
            time.sleep(8)
            body = page.inner_text('body')
            if len(body.strip()) < 100:
                time.sleep(5)
                body = page.inner_text('body')
            total_match = re.search(r'共：(\d+)', body)
            return int(total_match.group(1)) if total_match else 0
        except Exception as e:
            if attempt == 1:
                print(f'    覆盖量获取失败: {e}')
                return 0
            time.sleep(5)
    return 0

# ─── Step 3: API 拦截关键词 ──────────────────────────────────────────────────

def get_keywords_via_api(page, app, min_p, min_si, max_rank):
    keyword_list = []
    aso_url = f'https://app.diandian.com/app/{app["internal_id"]}/ios-aso?market=1&country=24&system=4'

    def handler(response):
        if 'api.diandian.com' in response.url and 'word/analysi/detail' in response.url:
            try:
                body = response.json()
                data = body.get('data', {})
                if data and 'list' in data:
                    keyword_list.extend(data['list'])
            except Exception:
                pass

    page.on('response', handler)
    print(f'    访问关键词页: {aso_url}')
    page.goto(aso_url, timeout=30000)
    time.sleep(10)

    if not keyword_list:
        print('    API 未自动触发，尝试点击关键词明细...')
        for tab in page.query_selector_all('text=关键词明细'):
            tab.click()
            time.sleep(5)
            break

    page.remove_listener('response', handler)

    filtered = [
        {
            'keyword': e[0],
            'rank': e[1],
            'rank_change': e[2],
            'search_index': e[3],
            'search_results': e[4],
            'popularity': e[7],
            'search_traffic': e[8] if len(e) > 8 else None,
            'exposure': e[9] if len(e) > 9 else None,
            'installs': e[10] if len(e) > 10 else None,
            'corrected_ref': e[13] if len(e) > 13 else None,
        }
        for e in keyword_list
        if isinstance(e, list) and len(e) >= 8
        and isinstance(e[1], int) and e[1] <= max_rank
        and isinstance(e[7], (int, float)) and e[7] >= min_p
        and isinstance(e[3], (int, float)) and e[3] >= min_si
    ]
    filtered.sort(key=lambda x: x['rank'])
    print(f'    拦截 {len(keyword_list)} 条 → 筛选后 {len(filtered)} 条')
    return filtered

# ─── 主流程 ──────────────────────────────────────────────────────────────────

def run_seed_mining(seeds, output_dir, top_n=3, min_p=6, min_si=1, max_rank=50, headless=True):
    os.makedirs(output_dir, exist_ok=True)
    summary = {}

    with sync_playwright() as p:
        setup_system_proxy()
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = load_and_validate_session(context)  # 返回已验证的 page（含 localStorage）

        for keyword in seeds:
            keyword = keyword.strip()
            safe_name = keyword.replace(' ', '_')
            print(f'\n{"="*60}')
            print(f'种子词: {keyword}')
            print('='*60)

            # Step 1: SERP
            top10 = get_serp_top10(page, keyword)
            if not top10:
                print(f'  跳过（无搜索结果）')
                continue

            # Step 2: 覆盖量
            print(f'\n  查询覆盖量...')
            for i, app in enumerate(top10):
                app['coverage'] = get_coverage(page, app)
                print(f'  [{i+1:2d}] {app["name"][:40]:40s}  覆盖量: {app["coverage"]}')
                time.sleep(2)

            # 保存 SERP 结果
            serp_path = os.path.join(output_dir, f'{safe_name}_serp.json')
            with open(serp_path, 'w', encoding='utf-8') as f:
                json.dump({'keyword': keyword, 'apps': top10}, f, ensure_ascii=False, indent=2)

            # Step 3: 选 top_n 覆盖量最高的 App 获取关键词
            # 覆盖量全为 0 时（「共：N」失效），按 SERP 排名取 TOP
            if all(app['coverage'] == 0 for app in top10):
                print(f'  ⚠️  覆盖量全为 0（「共：N」失效），改为按 SERP 排名取 TOP{top_n}')
                candidates = top10[:top_n]
            else:
                candidates = sorted(top10, key=lambda x: x['coverage'], reverse=True)[:top_n]
            print(f'\n  选择覆盖量 TOP{top_n} 竞品获取关键词:')
            for c in candidates:
                print(f'    - {c["name"]} (覆盖量: {c["coverage"]})')

            seed_result = {
                'keyword': keyword,
                'top10': top10,
                'selected_competitors': [],
            }

            for app in candidates:
                print(f'\n  抓取关键词: {app["name"]}')
                kws = get_keywords_via_api(page, app, min_p, min_si, max_rank)
                app_result = {
                    'name': app['name'],
                    'internal_id': app['internal_id'],
                    'coverage': app['coverage'],
                    'serp_rank': app['rank'],
                    'keywords': kws,
                }
                seed_result['selected_competitors'].append(app_result)

                # 每个竞品间隔 3 秒
                time.sleep(3)

            # 保存关键词结果
            kw_path = os.path.join(output_dir, f'{safe_name}_keywords.json')
            with open(kw_path, 'w', encoding='utf-8') as f:
                json.dump(seed_result, f, ensure_ascii=False, indent=2)

            summary[keyword] = seed_result
            print(f'\n  ✅ {keyword} 完成')
            time.sleep(3)

        browser.close()

    # 汇总
    summary_path = os.path.join(output_dir, 'summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f'\n\n{"="*60}')
    print(f'✅ 全部完成，结果保存到: {output_dir}')
    print('='*60)

    # 打印汇总
    for kw, data in summary.items():
        total_kws = sum(len(c['keywords']) for c in data['selected_competitors'])
        print(f'\n【{kw}】→ {len(data["selected_competitors"])} 个竞品，合计 {total_kws} 个关键词')
        for c in data['selected_competitors']:
            print(f'  {c["name"][:40]:40s}  {len(c["keywords"])} 个词')

    return summary


def main():
    parser = argparse.ArgumentParser(description='种子词竞品挖掘')
    parser.add_argument('--seeds', required=True, help='逗号分隔的种子词列表，如 "funko pop,warhammer"')
    parser.add_argument('--output', default='/tmp/seed_mining_results', help='输出目录（默认 /tmp/seed_mining_results）')
    parser.add_argument('--top-n', type=int, default=3, help='每个种子词选取覆盖量最高的前N个竞品（默认3）')
    parser.add_argument('--min-p', type=float, default=6, help='最低流行度筛选（默认6）')
    parser.add_argument('--min-si', type=float, default=1, help='最低搜索指数（默认1）')
    parser.add_argument('--max-rank', type=int, default=50, help='最高排名筛选（默认50）')
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（调试用，默认无头模式）')
    args = parser.parse_args()

    seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    headless = not args.show_browser
    print(f'种子词: {seeds}')
    print(f'输出目录: {args.output}')
    print(f'每词选 TOP{args.top_n} 竞品  |  筛选: P≥{args.min_p}, SI≥{args.min_si}, rank≤{args.max_rank}')
    print(f'浏览器模式: {"无头" if headless else "可视"}')

    run_seed_mining(seeds, args.output, args.top_n, args.min_p, args.min_si, args.max_rank, headless=headless)


if __name__ == '__main__':
    main()
