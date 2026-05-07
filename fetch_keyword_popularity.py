"""
批量查询关键词流行度（SERP 页面文本解析）
用法: python3 fetch_keyword_popularity.py keyword1 keyword2 ...
     python3 fetch_keyword_popularity.py --file /tmp/keywords.txt
     python3 fetch_keyword_popularity.py --file /tmp/keywords.txt --output /tmp/results.json

原理：SERP 页面（search/ios-1-5-5-24-0-{keyword}）是 SSR 渲染的，
      流行度、搜索指数、搜索结果数直接嵌在页面文本中，无需等待 API 响应。

数据格式（页面文本）：
  dnd
  Today 18:15 Update
  225 /225
  Search Results
  6384
  Search Index
  53
  Popularity
  1321
  Search Traffic

注意：某些极低量词（如 custom figurine）返回 "- Update / 0 /- / Search Results / - / Search Index / - / Popularity"
      这类词记录为 P=None，表示 US App Store 无实际搜索量。
"""
import json, time, re, os, sys, argparse
from urllib.parse import quote
from playwright.sync_api import sync_playwright

SESSION_PATH = '/tmp/diandian_session.json'


def load_session(context):
    if not os.path.exists(SESSION_PATH):
        print('❌ Session 文件不存在，请先运行: python3 references/login-script-v2.py', file=sys.stderr)
        sys.exit(1)
    with open(SESSION_PATH) as f:
        session = json.load(f)
    context.add_cookies(session.get('cookies', []))
    return session.get('localStorage', {})


def parse_kw_stats(text):
    """
    从 SERP 页面文本中提取关键词统计数据。
    有数据格式：  N /N \nSearch Results\nN \nSearch Index\nN \nPopularity
    无数据格式：  0 /- \nSearch Results\n- \nSearch Index\n- \nPopularity
    混合格式：    N /N \nSearch Results\n- \nSearch Index\nN \nPopularity（SI 无数据但 P 有值）
    """
    # 有数字的完整格式
    m = re.search(
        r'(\d+)\s*/[\d-]+\s*\nSearch Results\n([\d-]+)\s*\nSearch Index\n([\d-]+)\s*\nPopularity(?:\n([\d-]+)\s*\nSearch Traffic)?',
        text
    )
    if not m:
        return None

    def parse_val(s):
        return int(s) if s and s.isdigit() else None

    results_count = parse_val(m.group(1))
    search_index  = parse_val(m.group(2))
    popularity    = parse_val(m.group(3))
    search_traffic = parse_val(m.group(4)) if m.group(4) else None

    # 全为 None 表示无量
    if all(v is None for v in [results_count, search_index, popularity]):
        return None

    return {
        'results_count': results_count,
        'search_index': search_index,
        'popularity': popularity,
        'search_traffic': search_traffic,
    }


def fetch_keyword_stats(keywords, country_id=24, sleep_between=2):
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        local_storage = load_session(ctx)

        # 用 add_init_script 在每个页面加载前注入 localStorage
        # 这确保 Vue.js SPA 在初始化时就能读到认证 token
        if local_storage:
            ls_script = 'Object.entries(' + json.dumps(local_storage) + ').forEach(([k,v]) => localStorage.setItem(k,v));'
            ctx.add_init_script(ls_script)

        pg = ctx.new_page()

        for kw in keywords:
            encoded = quote(kw)
            url = f'https://app.diandian.com/search/ios-1-5-5-{country_id}-0-{encoded}'
            try:
                pg.goto(url, timeout=30000, wait_until='domcontentloaded')
                time.sleep(6)  # SERP 页面 SSR，等待 JS 渲染完成
                text = pg.inner_text('body')
                data = parse_kw_stats(text)
                results[kw] = data
            except Exception as e:
                results[kw] = {'error': str(e)}
            time.sleep(sleep_between)

        browser.close()

    return results


def main():
    parser = argparse.ArgumentParser(description='批量查询关键词流行度')
    parser.add_argument('keywords', nargs='*', help='关键词列表')
    parser.add_argument('--file', help='关键词文件（每行一个）')
    parser.add_argument('--output', '-o', help='输出 JSON 文件路径')
    parser.add_argument('--country', default=24, type=int, help='国家 ID（默认 24=美国）')
    args = parser.parse_args()

    keywords = list(args.keywords)
    if args.file:
        with open(args.file) as f:
            keywords += [line.strip() for line in f if line.strip()]

    if not keywords:
        parser.print_help()
        sys.exit(1)

    print(f'查询 {len(keywords)} 个关键词（country={args.country}）...')
    results = fetch_keyword_stats(keywords, country_id=args.country)

    print(f'\n{"关键词":<30}  {"P":>4}  {"SI":>7}  {"R":>6}')
    print('-' * 55)
    for kw, data in results.items():
        if data is None:
            print(f'{kw:<30}  {"无量":>4}  {"—":>7}  {"—":>6}')
        elif 'error' in data:
            print(f'{kw:<30}  ERROR: {data["error"][:40]}')
        else:
            p   = str(data.get('popularity')  or '—')
            si  = str(data.get('search_index') or '—')
            r   = str(data.get('results_count') or '—')
            print(f'{kw:<30}  {p:>4}  {si:>7}  {r:>6}')

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'\n结果已保存到 {args.output}')


if __name__ == '__main__':
    main()
