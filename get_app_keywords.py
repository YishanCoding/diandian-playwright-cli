"""
获取单个 App 的完整关键词列表（API 拦截）
用法: python3 get_app_keywords.py <internal_id> [app_name]
输出: JSON 到 stdout，或保存到文件

示例:
  python3 get_app_keywords.py np2ugugw6pd0kf7 "Customuse"
  python3 get_app_keywords.py 53u5u6xw9779mt7 "JuJuBit" --output /tmp/jujubit_keywords.json

筛选默认值: P≥6, SI≥1, rank≤50（可通过参数覆盖）
"""
import json, time, re, os, sys, argparse
from playwright.sync_api import sync_playwright

SESSION_PATH = '/tmp/diandian_session.json'
COOKIES_PATH = '/tmp/diandian_cookies.json'  # v1 backward compat


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
        print('❌ Session 文件不存在，请先运行 references/login-script-v2.py', file=sys.stderr)
        sys.exit(1)


def restore_local_storage(page, local_storage, origin):
    if not local_storage:
        return
    page.goto(origin, timeout=15000)
    page.evaluate(
        '(data) => { for (const [k, v] of Object.entries(data)) { localStorage.setItem(k, v); } }',
        local_storage
    )

def get_keywords(internal_id, app_name='', min_popularity=6, min_si=1, max_rank=50):
    keyword_list = []
    aso_url = f'https://app.diandian.com/app/{internal_id}/ios-aso?market=1&country=24&system=4'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        local_storage, origin = load_session(context)

        page = context.new_page()
        restore_local_storage(page, local_storage, origin)

        def handler(response):
            if 'api.diandian.com' in response.url and 'word/analysi/detail' in response.url:
                try:
                    body = response.json()
                    data = body.get('data', {})
                    if data and 'list' in data:
                        keyword_list.extend(data['list'])
                        print(f'  API 拦截到 {len(data["list"])} 条关键词', file=sys.stderr)
                except Exception:
                    pass

        page.on('response', handler)
        print(f'  访问 ASO 页: {aso_url}', file=sys.stderr)
        page.goto(aso_url, timeout=30000)
        time.sleep(10)

        # 若 API 未自动触发，点击「关键词明细」标签
        if not keyword_list:
            print('  API 未自动触发，尝试点击关键词明细...', file=sys.stderr)
            for tab in page.query_selector_all('text=关键词明细'):
                tab.click()
                time.sleep(5)
                break

        browser.close()

    # 筛选
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
        and isinstance(e[7], (int, float)) and e[7] >= min_popularity
        and isinstance(e[3], (int, float)) and e[3] >= min_si
    ]
    filtered.sort(key=lambda x: x['rank'])

    result = {
        'app_name': app_name or internal_id,
        'internal_id': internal_id,
        'country': 'US',
        'country_id': 24,
        'filter': {'min_popularity': min_popularity, 'min_si': min_si, 'max_rank': max_rank},
        'total_filtered': len(filtered),
        'total_raw': len(keyword_list),
        'keywords': filtered,
    }
    return result

def main():
    parser = argparse.ArgumentParser(description='获取 App 关键词列表')
    parser.add_argument('internal_id', help='App 的 internal_id')
    parser.add_argument('app_name', nargs='?', default='', help='App 名称（可选）')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径（默认输出到 stdout）')
    parser.add_argument('--min-p', type=float, default=6, help='最低流行度（默认 6）')
    parser.add_argument('--min-si', type=float, default=1, help='最低搜索指数（默认 1）')
    parser.add_argument('--max-rank', type=int, default=50, help='最高排名（默认 50）')
    args = parser.parse_args()

    result = get_keywords(
        args.internal_id, args.app_name,
        min_popularity=args.min_p,
        min_si=args.min_si,
        max_rank=args.max_rank,
    )

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f'✅ 已保存到 {args.output}（{result["total_filtered"]} 个关键词）', file=sys.stderr)
    else:
        print(output_json)

if __name__ == '__main__':
    main()
