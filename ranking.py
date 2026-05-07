"""
点点数据 App 榜单（App Store / Google Play）
用法: python3 ranking.py [free|paid|grossing] [--market ios|gp] [--country cn] [--category 工具]

示例:
  python3 ranking.py free --country cn                    # iOS 中国免费榜
  python3 ranking.py grossing --country cn --category 游戏 # iOS 中国游戏畅销榜
  python3 ranking.py free --market gp --country us        # GP 美国免费榜
  python3 ranking.py paid --country cn --category 工具 -o /tmp/ranking.json

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

TYPE_COL_INDEX = {'free': 0, 'paid': 1, 'grossing': 2}


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
        top_level, sub_level = '应用', ''
    elif category in ('游戏', '全部游戏'):
        top_level, sub_level = '游戏', ''
    elif category in APP_SUB_CATS:
        top_level, sub_level = '应用', category
    elif category in GAME_SUB_CATS:
        top_level, sub_level = '游戏', category
    else:
        print(f'⚠️  未知分类: {category}，跳过筛选', file=sys.stderr)
        return

    # 点击顶级 tab（应用/游戏）
    page.evaluate(f"""
        () => {{
            for (const el of document.querySelectorAll('.label, span')) {{
                const text = el.textContent.trim();
                if (text === '{top_level}榜' || text === '{top_level}') {{
                    const rect = el.getBoundingClientRect();
                    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
                    const target = document.elementFromPoint(x, y) || el;
                    for (const t of ['mousedown', 'mouseup', 'click']) {{
                        target.dispatchEvent(new MouseEvent(t, {{bubbles: true, cancelable: true, clientX: x, clientY: y}}));
                    }}
                    return;
                }}
            }}
        }}
    """)
    time.sleep(3)

    if not sub_level:
        return

    # 打开子分类 cascader
    page.evaluate("() => { const c = document.querySelector('.el-cascader'); if (c) c.click(); }")
    time.sleep(1)

    page.evaluate(f"""
        () => {{
            for (const opt of document.querySelectorAll('.el-cascader-menu li, .el-select-dropdown__item')) {{
                if (opt.textContent.trim() === '{sub_level}') {{
                    const rect = opt.getBoundingClientRect();
                    const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
                    const target = document.elementFromPoint(x, y) || opt;
                    for (const t of ['mousedown', 'mouseup', 'click']) {{
                        target.dispatchEvent(new MouseEvent(t, {{bubbles: true, cancelable: true, clientX: x, clientY: y}}));
                    }}
                    return;
                }}
            }}
        }}
    """)
    time.sleep(3)


def fetch_ranking(rank_type='free', market='ios', country='cn', device='iphone', category='', limit=20):
    country_id = resolve_country(country)
    col_index = TYPE_COL_INDEX.get(rank_type, 0)
    platform = 'googleplay' if market == 'gp' else 'ios'
    url = f'https://app.diandian.com/rank/{platform}/'

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

        # 按 x 坐标分列提取对应榜单 App
        results = page.evaluate(f"""
            () => {{
                const allApps = document.querySelectorAll('a.top-start');
                if (allApps.length === 0) return [];

                const positions = [];
                for (const a of allApps) {{
                    const rect = a.getBoundingClientRect();
                    if (rect.width === 0) continue;
                    positions.push({{el: a, x: rect.x}});
                }}
                if (positions.length === 0) return [];

                // 按 x 坐标聚类成列
                const xValues = positions.map(p => p.x).sort((a, b) => a - b);
                const columns = [];
                let lastX = -999;
                for (const x of xValues) {{
                    if (x - lastX > 100) columns.push({{minX: x, apps: []}});
                    lastX = x;
                }}

                for (const pos of positions) {{
                    let best = 0, bestDist = Infinity;
                    for (let i = 0; i < columns.length; i++) {{
                        const dist = Math.abs(pos.x - columns[i].minX);
                        if (dist < bestDist) {{ bestDist = dist; best = i; }}
                    }}
                    columns[best].apps.push(pos.el);
                }}

                const colIndex = {col_index};
                if (colIndex >= columns.length) return [];

                const items = [];
                for (const a of columns[colIndex].apps) {{
                    const name = a.textContent.trim();
                    if (!name || name.includes('榜单')) continue;
                    const href = a.getAttribute('href') || '';
                    const id = href.match(/\\/app\\/([^/]+)/)?.[1] || '';
                    if (!id) continue;

                    const listItem = a.closest('.rank-list') || a.parentElement?.parentElement?.parentElement;
                    const lines = (listItem?.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean);

                    let categoryRank = '', developer = '', price = '';
                    for (const line of lines) {{
                        if (line.includes('名') && line.includes('：')) categoryRank = line;
                        else if (line.startsWith('¥') || line.startsWith('$')) price = line;
                        else if (!line.includes('榜') && !line.includes('霸榜') && line !== name
                                 && line.length > 3 && line.length < 60 && !/^\\d/.test(line)) {{
                            if (!developer) developer = line;
                        }}
                    }}

                    items.push({{rank: items.length + 1, name, internal_id: id, category_rank: categoryRank, developer, price}});
                }}
                return items;
            }}
        """)

        browser.close()

    return (results or [])[:limit]


def main():
    parser = argparse.ArgumentParser(description='点点数据 App 榜单')
    parser.add_argument('type', nargs='?', default='free', choices=['free', 'paid', 'grossing'],
                        help='榜单类型：free=免费(默认) paid=付费 grossing=畅销')
    parser.add_argument('--market', default='ios', choices=['ios', 'gp'], help='平台（ios/gp，默认ios）')
    parser.add_argument('--country', default='cn', help='国家代码或ID（cn/us/jp，默认cn）')
    parser.add_argument('--device', default='iphone', choices=['iphone', 'ipad'], help='设备（仅iOS）')
    parser.add_argument('--category', default='', help='分类筛选（如：游戏、工具、益智解谜）')
    parser.add_argument('--limit', type=int, default=20, help='结果数量（默认20）')
    parser.add_argument('--output', '-o', help='输出JSON文件路径')
    args = parser.parse_args()

    type_label = {'free': '免费榜', 'paid': '付费榜', 'grossing': '畅销榜'}[args.type]
    market_label = 'Google Play' if args.market == 'gp' else 'App Store'
    cat_label = f' · {args.category}' if args.category else ''
    print(f'获取 {market_label} {args.country} {type_label}{cat_label}...')

    results = fetch_ranking(args.type, args.market, args.country, args.device, args.category, args.limit)

    if not results:
        print('❌ 未获取到数据，请检查 session 是否有效', file=sys.stderr)
        sys.exit(1)

    print(f'\n{"排名":>4}  {"App名称":<35}  {"internal_id":<20}  {"开发者":<25}  {"价格"}')
    print('-' * 100)
    for item in results:
        print(f'{item["rank"]:>4}  {item["name"]:<35}  {item["internal_id"]:<20}  {item["developer"]:<25}  {item["price"]}')

    print(f'\n共 {len(results)} 条')

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'结果已保存到 {args.output}')


if __name__ == '__main__':
    main()
