#!/usr/bin/env python3
"""
抓取点点(diandian) 每个关键词的「分日排名」趋势。

原理（2026-06-29 逆向确认）：
  点点关键词「📊 关键词综合走势」弹窗调的端点是
    POST https://api.diandian.com/pc/app/v1/word/app/trend
    body: {ids:[internal_id], country_id, word, start_time, end_time, cut_by:1, k:<签名>}
    resp: {code,msg,data:{lines:[{word,name:"Ranking",stats:[[unix_ts, rank], ...]}]}}
  `k` 签名由前端 Nuxt 应用生成，无法直接构造。
  解法：通过 OpenCLI 驱动已登录点点的浏览器，调用页面自带的已签名 axios 实例
    window.$nuxt.context.$axios  (baseURL = https://api.diandian.com/pc)
  即 ax.post('/app/v1/word/app/trend', {...}) —— 拦截器自动加 k + 带 cookie。

前置：
  1. OpenCLI daemon 在跑、扩展已连接（curl 127.0.0.1:19825/status）。
  2. 浏览器已打开并登录点点的目标 App ASO 页（本脚本会用 session 注入 + open）。
     若 OpenCLI 浏览器未登录，先用 inject_session() 注入 /tmp/diandian_session.json。

用法：
  python3 fetch_diandian_keyword_trends.py \
      --internal-id 53u5u6xw9779mt7 --country-id 24 \
      --candidates /tmp/dd_candidates.json --days 30 \
      --out /tmp/jujubit_kw_trends.json
"""
import json, subprocess, argparse, time, sys, os

OPENCLI_SESSION = "dd"   # opencli browser <session>


def opencli_eval(js, timeout=90):
    p = subprocess.run(["opencli", "browser", OPENCLI_SESSION, "eval", js],
                       capture_output=True, text=True, timeout=timeout)
    out = p.stdout
    # opencli 可能夹杂插件 warning，取第一个 { 起的 JSON
    i = out.find("{")
    j = out.rfind("}")
    if i == -1 or j == -1:
        # 也可能直接返回字符串 JSON（被引号包裹）
        return out.strip()
    return out[i:j+1]


def ensure_logged_in(internal_id, country_id):
    """打开 ASO 页并确认登录；未登录则注入本地 session 后重试。"""
    url = (f"https://app.diandian.com/app/{internal_id}/ios-aso"
           f"?market=1&country={country_id}&system=4&id=&n=")
    subprocess.run(["opencli", "browser", OPENCLI_SESSION, "open", url],
                   capture_output=True, text=True, timeout=60)
    time.sleep(10)
    chk = opencli_eval("JSON.stringify({login:location.href.indexOf('/login')>-1,"
                       "ax:!!(window.$nuxt&&window.$nuxt.context&&window.$nuxt.context.$axios)})")
    try:
        st = json.loads(json.loads(chk) if chk.startswith('"') else chk)
    except Exception:
        st = {}
    if st.get("login") or not st.get("ax"):
        # 注入本地 session
        sp = "/tmp/diandian_session.json"
        if os.path.exists(sp):
            inject_session(sp)
            subprocess.run(["opencli", "browser", OPENCLI_SESSION, "open", url],
                           capture_output=True, text=True, timeout=60)
            time.sleep(12)
        else:
            print("⚠️ 浏览器未登录点点，且无 /tmp/diandian_session.json 可注入。"
                  "请在 OpenCLI 浏览器里手动登录点点后重跑。", file=sys.stderr)
            sys.exit(2)
    return True


def inject_session(session_path):
    import base64
    s = json.load(open(session_path))
    payload = {"ls": s.get("localStorage", {}),
               "ck": [{"name": c["name"], "value": c["value"]}
                      for c in s.get("cookies", []) if not c.get("httpOnly")]}
    b = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    js = ("(function(){var raw=new TextDecoder().decode(Uint8Array.from(atob('" + b +
          "'),function(c){return c.charCodeAt(0)}));var o=JSON.parse(raw);"
          "for(var k in o.ls){try{localStorage.setItem(k,o.ls[k])}catch(e){}}"
          "o.ck.forEach(function(c){try{document.cookie=c.name+'='+c.value+"
          "';path=/;domain=.diandian.com'}catch(e){}});return 'ok'})()")
    opencli_eval(js)


def fetch_batch(internal_id, country_id, words, days):
    """通过页面 $axios 拉一批词的分日排名。返回 {word: [[ts,rank],...] or None}
    每个请求有 8s 超时（Promise.race），避免单个挂起拖垮整批/触发 opencli 超时。"""
    js = ("(async function(){var W=" + json.dumps(words, ensure_ascii=False) + ";"
          "var APP=" + json.dumps(internal_id) + ";var CID=" + str(country_id) + ";"
          "var now=Math.floor(Date.now()/1000);var start=now-" + str(days) + "*86400;"
          "var ax=window.$nuxt.context.$axios;var out={};"
          "function TO(ms){return new Promise(function(_,rej){setTimeout(function(){rej(new Error('to'))},ms)})}"
          "for(var i=0;i<W.length;i++){try{"
          "var r=await Promise.race([ax.post('/app/v1/word/app/trend',{ids:[APP],country_id:CID,word:W[i],"
          "start_time:start,end_time:now,cut_by:1}),TO(8000)]);"
          "out[W[i]]=(r&&r.data&&r.data.lines&&r.data.lines[0]&&r.data.lines[0].stats)||[];"
          "}catch(e){out[W[i]]=null;}"
          "await new Promise(function(res){setTimeout(res,120)});}"
          "return JSON.stringify(out);})()")
    try:
        raw = opencli_eval(js, timeout=110)
    except Exception as e:
        print("  batch eval timeout/err:", str(e)[:50], file=sys.stderr)
        return {w: None for w in words}
    try:
        return json.loads(json.loads(raw) if raw.startswith('"') else raw)
    except Exception as e:
        print("  batch parse err:", e, "| head:", raw[:120], file=sys.stderr)
        return {w: None for w in words}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal-id", required=True)
    ap.add_argument("--country-id", type=int, default=24)
    ap.add_argument("--candidates", required=True, help="JSON list of keyword strings")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--out", default="/tmp/jujubit_kw_trends.json")
    a = ap.parse_args()

    cands = json.load(open(a.candidates))
    # 断点续跑：若 out 已存在，跳过已抓到（非 None）的词
    trends = {}
    if os.path.exists(a.out):
        try:
            trends = json.load(open(a.out)).get("trends", {})
            print(f"续跑：已有 {sum(1 for v in trends.values() if v is not None)} 词")
        except Exception:
            trends = {}
    todo = [w for w in cands if w not in trends or trends.get(w) is None]
    print(f"候选词 {len(cands)} 个，待抓 {len(todo)}，window {a.days} 天，batch {a.batch}")
    ensure_logged_in(a.internal_id, a.country_id)

    def save():
        json.dump({"internal_id": a.internal_id, "country_id": a.country_id,
                   "days": a.days, "trends": trends},
                  open(a.out, "w"), ensure_ascii=False)

    for i in range(0, len(todo), a.batch):
        b = todo[i:i+a.batch]
        res = fetch_batch(a.internal_id, a.country_id, b, a.days)
        trends.update(res)
        save()  # 每批落盘，崩溃不丢进度
        got = sum(1 for w in b if res.get(w))
        print(f"  [{i+len(b)}/{len(todo)}] batch ok={got}/{len(b)}  (saved)")
        time.sleep(0.3)

    save()
    ok = sum(1 for v in trends.values() if v)
    print(f"完成：{ok}/{len(trends)} 词有数据 → {a.out}")


if __name__ == "__main__":
    main()
