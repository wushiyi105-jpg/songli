"""Web 入口:零依赖 http.server,单页 + JSON API。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, db, llm, rules

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>送礼 · 人情方案</title>
<style>
  :root{--bg:#fbf8f4;--card:#fff;--ink:#3a2f28;--muted:#7d6d61;--accent:#a8552f;--soft:#fbe9df;
        --line:#eee1d8;--red:#b42318;--green:#067647;--amber:#b54708;--radius:16px}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
  .wrap{max-width:980px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:26px;margin:0 0 4px} header p{color:var(--muted);margin:0 0 22px}
  .badge{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--soft);color:var(--accent);margin-left:8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(58,47,40,.04)}
  label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
  textarea,input{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px;font-family:inherit;background:#fff}
  textarea{line-height:1.7}
  button{background:var(--accent);color:#fff;border:none;padding:12px 22px;border-radius:12px;font-size:15px;cursor:pointer}
  .hint{color:var(--muted);font-size:12px;margin-top:8px}
  .spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result{display:none}.result.show{display:block}
  h3{font-size:15px;color:var(--muted);margin:20px 0 8px}
  .gift{border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
  .gift b{font-size:16px}.price{color:var(--accent);font-weight:600}
  .box{background:#fffdfb;border-radius:10px;padding:12px 14px;margin:8px 0;font-size:14px;line-height:1.8}
  ul{margin:6px 0 0 18px;padding:0}li{margin:6px 0;font-size:14px}
  .warn{color:var(--amber)}.bad{color:var(--red)}.ok{color:var(--green)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>送礼 · 人情方案<span class="badge" id="badge">…</span></h1>
    <p>说清楚送给谁、什么场合、多少预算:三套能落地的方案,连同避雷和话术。</p>
  </header>
  <div class="card">
    <label>送礼需求</label>
    <textarea id="text" rows="5" placeholder="送长辈,生日,预算 500,对方喜欢喝茶,不喝酒"></textarea>
    <div style="margin-top:16px"><button id="btn">出方案</button></div>
    <div class="hint">价位与预算拆分由本地算;模型只润色理由与话术,不能改价位。</div>
  </div>
  <div class="result" id="res"></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function load(btn,on){btn.disabled=on;if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.innerHTML='<span class="spin"></span>';}else{btn.innerHTML=btn.dataset.label||btn.textContent;}}
$('#btn').onclick=async()=>{
  const el=$('#res');el.classList.remove('show');load($('#btn'),true);
  try{
    const p=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#text').value})});
    const r=await p.json(); if(r.error) throw new Error(r.error);
    const b=r.brief;
    let h='<div class="card"><div class="hint">'+(r.mode==='model'?'模型已连接':'离线模式')+'</div>';
    h+='<p>关系 <b>'+esc(b.relation||'未写')+'</b> · 场合 <b>'+esc(b.occasion||'未写')+'</b> · 预算 <b>'+esc(b.budget||'未写')+'</b></p>';
    if(r.split.main){h+='<div class="box">预算拆分:主礼 '+r.split.main+' / 花 '+r.split.flower+' / 卡 '+r.split.card+' / 包装 '+r.split.wrap+'</div>';}
    if(r.taboos.length){h+='<h3>命中禁忌</h3>';r.taboos.forEach(t=>{h+='<div class="bad">🚫 '+esc(t.name)+' —— '+esc(t.reason)+' → '+esc(t.alt)+'</div>';});}
    h+='<h3>三套方案</h3>';
    r.schemes.forEach((g,i)=>{h+='<div class="gift"><b>'+(i+1)+'. '+esc(g.name)+'</b> <span class="price">'+g.low+'–'+g.high+' 元</span><div class="hint">'+esc(g.category)+' · '+esc(g.tag)+'</div><div>'+esc(g.reason)+'</div></div>';});
    h+='<h3>时机</h3><div class="box">'+esc(r.timing)+'</div>';
    h+='<h3>话术</h3><ul>';r.scripts.say.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul><div class="hint">被推辞时:</div><ul>';
    r.scripts.refuse.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul>';
    if(r.risks.length){h+='<h3>风险</h3><ul>';r.risks.forEach(x=>h+='<li class="warn">'+esc(x)+'</li>');h+='</ul>';}
    h+='</div>';el.innerHTML=h;
  }catch(e){el.innerHTML='<div class="card" style="color:#b42318">请求失败:'+esc(e.message)+'</div>';}
  el.classList.add('show');load($('#btn'),false);
};
fetch('/api/status').then(r=>r.json()).then(s=>{const b=$('#badge');
  if(s.mock){b.textContent='离线模式';b.style.background='#fee2e2';b.style.color='#b42318';}
  else{b.textContent=s.model||'模型已连接';b.style.background='#dcfce7';b.style.color='#067647';}
}).catch(()=>{});
</script>
</body></html>
"""


def _handler(cfg, force_mock, db_path):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock = force_mock or not cfg.get("api_key")
                self._json({"mock": mock, "model": None if mock else cfg.get("model")})
            elif path == "/api/history":
                db.use(db_path)
                self._json(db.history(None, 20))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/plan":
                self._json({"error": "not found"}, 404)
                return
            try:
                body = self._read()
                db.use(db_path)
                text = body.get("text", "")
                recipient = body.get("recipient") or (rules.parse(text).get("relation") or "")
                r = agent.analyze(text, sent=db.sent_names(recipient), force_mock=force_mock)
                if body.get("save", True) and recipient:
                    db.record(recipient, r["brief"].get("occasion"), r["brief"].get("relation"),
                              r["schemes"][0]["name"], r["schemes"][0]["low"], text[:200])
                self._json(r)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, db_path=None, force_mock=False):
    cfg = llm.default_config()
    httpd = ThreadingHTTPServer((host, port), _handler(cfg, force_mock, db_path))
    mode = "离线模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else "模型:%s" % cfg.get("model")
    print("🎁 送礼已启动:http://%s:%s  [%s]" % (host, port, mode))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
