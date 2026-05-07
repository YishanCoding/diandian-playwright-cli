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
