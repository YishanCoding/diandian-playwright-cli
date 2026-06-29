# diandian-playwright-cli

Python + Playwright 自动化操作 [app.diandian.com](https://app.diandian.com)，提取 ASO 关键词、App 信息、竞品数据。

## 环境要求

```bash
pip install playwright
playwright install chromium
```

## 认证

认证 token 存储在 localStorage（JWT），必须用 `login_v2.py` 保存完整 session：

```bash
# 首次登录 / session 失效时（会打开浏览器，手动登录后自动保存）
python3 login_v2.py

# 验证 session 是否有效
python3 check_session.py
```

session 保存到 `/tmp/diandian_session.json`，包含 cookies + localStorage。

> ⚠️ 同一账号只允许一个浏览器同时登录，禁止多脚本并发运行。

## 脚本说明

| 脚本 | 功能 | 示例 |
|------|------|------|
| `login_v2.py` | 手动登录，保存 session | `python3 login_v2.py` |
| `check_session.py` | 验证 session 有效性（返回 0=有效） | `python3 check_session.py` |
| `fetch_keyword_popularity.py` | 批量查关键词 P/SI/搜索结果数（SSR 直出，快） | `python3 fetch_keyword_popularity.py "funko pop" anime` |
| `get_app_keywords.py` | 获取 App 完整 ASO 关键词列表（API 拦截） | `python3 get_app_keywords.py <internal_id> "App名" -o /tmp/out.json` |
| `diandian_rank_check_v2.py` | 查单词在指定国家的 SERP 排名 | `python3 diandian_rank_check_v2.py "jujubit" --country 24` |
| `global_scan.py` | 多国并行扫描单词排名 | `python3 global_scan.py --app_id <id> --keyword "xxx"` |
| `get_countries_v2.py` | 探测 App 在架国家列表 | `python3 get_countries_v2.py` |
| `seed_mining.py` | 种子词竞品挖掘完整流水线 | `python3 seed_mining.py --seeds "funko pop,anime" --output /tmp/results` |
| `trending.py` | 搜索指数榜单（支持分类筛选） | `python3 trending.py --country cn --category 工具` |
| `ranking.py` | App Store / GP 榜单（免费/付费/畅销） | `python3 ranking.py free --country cn --category 游戏` |
| `fetch_diandian_keyword_trends.py` | 抓每个关键词近 N 天**分日排名趋势**（OpenCLI 驱动，非 Playwright） | `python3 fetch_diandian_keyword_trends.py --internal-id <id> --candidates words.json --days 30 --out trends.json` |

## 分日排名趋势（fetch_diandian_keyword_trends.py）

点点关键词「📊 关键词综合走势」弹窗调的端点是
`POST /pc/app/v1/word/app/trend`，返回 `data.lines[0].stats = [[unix_ts, rank], …]` 的每日排名序列。
该请求带前端生成的 `k` 签名，**无法直接构造**。解法：通过 **OpenCLI** 驱动已登录点点的浏览器，
调用页面自带的已签名 axios 实例 `window.$nuxt.context.$axios`（baseURL `https://api.diandian.com/pc`）——
拦截器自动加 `k` + 带 cookie，无需破解签名。

```bash
# 前置：OpenCLI daemon 在跑、扩展已连接；浏览器已登录点点（脚本会自动注入 /tmp/diandian_session.json）
# candidates 为 JSON 字符串数组（如当前排名 ≤30 的词），逐词拉 30 天分日排名
python3 fetch_diandian_keyword_trends.py \
    --internal-id 53u5u6xw9779mt7 --country-id 24 \
    --candidates /tmp/candidates.json --days 30 --batch 10 \
    --out /tmp/kw_trends.json
```

- 每请求 8s 超时、每批落盘、断点续跑（`--out` 已存在则跳过已抓到的词）。
- 与本仓库其它脚本不同：本脚本走 OpenCLI（`opencli browser <session> eval`），不是 Playwright。

## 常用流程

### 批量查关键词流行度
```bash
python3 fetch_keyword_popularity.py "funko pop" "anime figure" "dnd miniature"
python3 fetch_keyword_popularity.py --file /tmp/keywords.txt --output /tmp/results.json
```

### 获取竞品完整关键词
```bash
python3 get_app_keywords.py <internal_id> "App名" -o /tmp/keywords.json
# 可选筛选: --min-p 6  --min-si 1  --max-rank 50
```

### 种子词竞品挖掘
```bash
python3 seed_mining.py \
  --seeds "funko pop,warhammer,anime figure" \
  --output /tmp/seed_results \
  --top-n 3
```

## 常用参数

| 参数 | 值 | 含义 |
|------|---|------|
| country | 24 | 美国 (US) |
| country | 36 | 中国 (CN) |
| country | 27 | 日本 (JP) |
| market | 1 | App Store |
| market | 2 | Google Play |

## License

MIT
