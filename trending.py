"""
点点数据搜索指数榜单
用法: python3 trending.py [--country cn] [--category 工具] [--limit 50]
     python3 trending.py --country us --category 购物
     python3 trending.py --country cn --category 益智解谜 -o /tmp/trending.json

分类可选值：
  应用子分类: 摄影与录像 娱乐 教育 效率 社交 生活 购物 工具 音乐 图书
              商务 财务 美食佳饮 健康健美 报刊杂志 医疗 导航 新闻 参考资料
              体育 旅游 天气 软件开发工具 儿童 图形与设计
  游戏子分类: 益智解谜 动作 角色扮演 策略 休闲 体育 模拟 冒险 家庭聚会
              桌面 卡牌 音乐 竞速 问答 字谜 娱乐场
"""
import json, time, os, sys, argparse
from playwright.sync_api import sync_playwright

SESSION_PATH = '/tmp/diandian_session.json'

COUNTRY_MAP = {
    'cn': 75, 'us': 24, 'jp': 27, 'kr': 28, 'gb': 25,
    'au': 26, 'de': 29, 'fr': 30, 'ca': 31,
}

APP_SUB_CATS = {
    '全部应用', '摄影与录像', '娱乐', '教育', '效率', '社交', '生活', '购物',
    '工具', '音乐', '图书', '商务', '财务', '美食佳饮', '健康健美', '报刊杂志',
    '医疗', '导航', '新闻', '参考资料', '体育', '旅游', '天气', '软件开发工具',
    '儿童', '图形与设计',
}
GAME_SUB_CATS = {
    '全部游戏', '益智解谜', '动作', '角色扮演', '策略', '休闲', '体育', '模拟',
    '冒险', '家庭聚会', '桌面', '卡牌', '音乐', '竞速', '问答', '字谜', '娱乐场',
}


def load_session(context):
    if not os.path.exists(SESSION_PATH):
        print('❌ Session 文件不存在，请先运行: python3 login_v2.py', file=sys.stderr)
        sys.exit(1)
    with open(SESSION_PATH) as f:
        session = json.load(f)
    context.add_cookies(session.get('cookies', []))
    return session.get('localStorage', {})


def resolve_country(country):
    key = str(country).lower()
    if key.isdigit():
        return int(key)
    return COUNTRY_MAP.get(key, 75)


def apply_category_filter(page, category):
    if category in ('应用', '全部应用'):
        top_level, sub_level = '应用', '全部应用'
    elif category in ('游戏', '全部游戏'):
        top_level, sub_level = '游戏', '全部游戏'
    elif category in APP_SUB_CATS:
        top_level, sub_level = '应用', category
    elif category in GAME_SUB_CATS:
        top_level, sub_level = '游戏', category
    else:
        print(f'⚠️  未知分类: {category}，跳过筛选', file=sys.stderr)
        return

    # Step 1: 打开 cascader
    page.evaluate("() => { const c = document.querySelector('.el-cascader'); if (c) c.click(); }")
    time.sleep(1)

    # Step 2: hover 顶级菜单项展开子菜单
    page.evaluate(f"""
        () => {{
            for (const item of document.querySelectorAll('.el-cascader-menu li')) {{
                if (item.textContent.trim() === '{top_level}') {{
                    item.dispatchEvent(new MouseEvent('mouseenter', {{bubbles: true}}));
                    item.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                    item.dispatchEvent(new Event('focus', {{bubbles: true}}));
                    return;
                }}
            }}
        }}
    """)
    time.sleep(2)

    # Step 3: 点击子分类（用原生 mouse 事件序列触发 Vue 响应）
    page.evaluate(f"""
        () => {{
            const menus = document.querySelectorAll('.el-cascader-menu');
            if (menus.length < 2) return;
            for (const item of menus[menus.length - 1].querySelectorAll('li')) {{
                if (item.textContent.trim() === '{sub_level}') {{
                    const rect = item.getBoundingClientRect();
                    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
                    const target = document.elementFromPoint(x, y) || item;
                    for (const t of ['mousedown', 'mouseup', 'click']) {{
                        target.dispatchEvent(new MouseEvent(t, {{bubbles: true, cancelable: true, clientX: x, clientY: y}}));
                    }}
                    return;
                }}
            }}
        }}
    """)
    time.sleep(5)


def fetch_trending(country='cn', device='iphone', category='', limit=50):
    country_id = resolve_country(country)
    device_id = 2 if device == 'ipad' else 1
    url = f'https://app.diandian.com/rank/trend-1-{device_id}-{country_id}-0-0'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        local_storage = load_session(ctx)

        if local_storage:
            ls_script = 'Object.entries(' + json.dumps(local_storage) + ').forEach(([k,v])=>localStorage.setItem(k,v));'
            ctx.add_init_script(ls_script)

        page = ctx.new_page()
        page.goto(url, timeout=30000, wait_until='domcontentloaded')
        time.sleep(8)

        if category:
            apply_category_filter(page, category)

        results = page.evaluate("""
            () => {
                const items = [];
                const rows = document.querySelectorAll('tr.dd-data-table-row, tr.dd-hover-row');
                for (const row of rows) {
                    const tds = [...row.querySelectorAll('td')];
                    if (tds.length < 5) continue;

                    const rankEl = tds[0].querySelector('.rank-value');
                    const rank = parseInt(rankEl?.textContent?.trim() || tds[0].textContent.trim()) || (items.length + 1);
                    const keyword = tds[1].textContent.trim();
                    if (!keyword) continue;

                    const si = parseInt(tds[2].textContent.trim().replace(/,/g, '')) || 0;
                    const p  = parseInt(tds[3].textContent.trim()) || 0;
                    const r  = parseInt(tds[4].textContent.trim().replace(/,/g, '')) || 0;

                    let top1_app = '', top1_app_id = '';
                    if (tds[5]) {
                        for (const a of tds[5].querySelectorAll('a[href*="/app/"]')) {
                            const text = a.textContent.trim();
                            if (text && text.length > 1 && !/^[\\d.]+$/.test(text)) top1_app = text;
                            const m = a.getAttribute('href')?.match(/\\/app\\/([^/]+)/);
                            if (m) top1_app_id = m[1];
                        }
                    }
                    items.push({rank, keyword, search_index: si, popularity: p, results: r, top1_app, top1_app_id});
                }
                return items;
            }
        """)

        browser.close()

    return (results or [])[:limit]


def main():
    parser = argparse.ArgumentParser(description='点点数据搜索指数榜单')
    parser.add_argument('--country', default='cn', help='国家代码或ID（cn/us/jp，默认cn）')
    parser.add_argument('--device', default='iphone', choices=['iphone', 'ipad'])
    parser.add_argument('--category', default='', help='分类筛选（如：工具、益智解谜）')
    parser.add_argument('--limit', type=int, default=50, help='结果数量（默认50）')
    parser.add_argument('--output', '-o', help='输出JSON文件路径')
    args = parser.parse_args()

    print(f'获取搜索指数榜单（country={args.country}, category="{args.category or "全部"}"）...')
    results = fetch_trending(args.country, args.device, args.category, args.limit)

    if not results:
        print('❌ 未获取到数据，请检查 session 是否有效', file=sys.stderr)
        sys.exit(1)

    print(f'\n{"排名":>4}  {"关键词":<30}  {"SI":>8}  {"P":>4}  {"搜索结果":>8}  TOP1 App')
    print('-' * 85)
    for item in results:
        si = f'{item["search_index"]:,}' if item['search_index'] else '—'
        r  = f'{item["results"]:,}'      if item['results']       else '—'
        print(f'{item["rank"]:>4}  {item["keyword"]:<30}  {si:>8}  {item["popularity"]:>4}  {r:>8}  {item["top1_app"]}')

    print(f'\n共 {len(results)} 条')

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'结果已保存到 {args.output}')


if __name__ == '__main__':
    main()
