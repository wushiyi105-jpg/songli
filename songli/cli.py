"""命令行入口:python -m songli <命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, db, llm, rules
from .llm import LLMError

BANNER = ("⚠️  当前为离线模式(未配置 LLM_API_KEY):方案由本地按关系/场合/预算/禁忌筛出,话术用模板。\n"
          "   填入 LLM_API_KEY 后,理由与话术由模型润色(价位仍以本地为准)。\n")


def _text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def render(r):
    mode = "模型" if r["mode"] == "model" else "离线模式"
    b = r["brief"]
    lines = ["🎁 送礼方案  [%s]" % mode, "",
             "关系:%s · 场合:%s · 预算:%s"
             % (b.get("relation") or "未写", b.get("occasion") or "未写",
                ("%d 元" % b["budget"]) if b.get("budget") else "未写")]
    if b.get("interests"):
        lines.append("偏好:" + "、".join(b["interests"]))
    lines.append("")
    s = r["split"]
    if s.get("main"):
        lines.append("💰 预算拆分:主礼 %d / 花 %d / 卡 %d / 包装 %d(合计 %d)"
                     % (s["main"], s["flower"], s["card"], s["wrap"], s["total"]))
        lines.append("")
    if r["taboos"]:
        lines.append("🚫 命中禁忌")
        for t in r["taboos"]:
            lines.append("  · %s —— %s;替代:%s" % (t["name"], t["reason"], t["alt"]))
        lines.append("")
    lines.append("🎯 三套方案")
    if not r["schemes"]:
        lines.append("  " + (r.get("note") or "没有符合条件的礼物,先把预算或场合放宽一条。"))
    for i, g in enumerate(r["schemes"], 1):
        lines.append("  %d. %s(%s,%d–%d 元)" % (i, g["name"], g["category"], g["low"], g["high"]))
        lines.append("     理由:" + g["reason"])
        lines.append("     渠道:%s" % ("线下专柜/门店" if g["high"] >= 300 else "品牌旗舰店或商场"))
    lines.append("")
    lines.append("⏰ 时机")
    lines.append("  " + r["timing"])
    lines.append("")
    lines.append("🗣 话术")
    for x in r["scripts"]["say"]:
        lines.append("  · " + x)
    lines.append("  被推辞时:")
    for x in r["scripts"]["refuse"]:
        lines.append("  · " + x)
    if r["risks"]:
        lines.append("")
        lines.append("🚩 风险")
        for x in r["risks"]:
            lines.append("  · " + x)
    return "\n".join(lines)


def cmd_plan(args):
    text = _text(args)
    if not text.strip():
        print("❌ 没有描述:说清楚送给谁、什么场合、多少预算。", file=sys.stderr)
        sys.exit(2)
    db.use(args.db)
    recipient = args.recipient or (rules.parse(text).get("relation") or "")
    sent = db.sent_names(recipient) if recipient else []
    r = agent.analyze(text, sent=sent, force_mock=args.mock)
    if args.save:
        r["saved_id"] = db.record(recipient, r["brief"].get("occasion"), r["brief"].get("relation"),
                                  r["schemes"][0]["name"] if r["schemes"] else None,
                                  r["schemes"][0]["low"] if r["schemes"] else None, text[:200])
        db.save_plan(r, recipient)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(render(r))


def cmd_check(args):
    a = rules.taboo_hits(_text(args))
    if not a:
        print("✅ 没命中已知禁忌;但过敏、宗教、丧事场合仍需自己确认。")
        return
    print("🚫 命中 %d 条禁忌" % len(a))
    for t in a:
        print("  · %s —— %s → %s" % (t["name"], t["reason"], t["alt"]))


def cmd_pool(args):
    brief = rules.parse(args.text or "")
    rows = rules.pool(brief.get("relation"), brief.get("occasion"), brief.get("budget"))
    rows = sorted(rows, key=lambda g: -(g["high"]))[:args.limit]
    print("🎁 可选礼物池(%d 条,按价位从高到低)" % len(rows))
    for g in rows:
        print("  · %-28s %-6s %4d–%-4d 元  %s" % (g["name"], g["category"], g["low"], g["high"],
                                                 "、".join(g["relations"])))


def cmd_history(args):
    db.use(args.db)
    rows = db.history(args.recipient, args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("还没有记录。`python -m songli plan --text \"送长辈 生日 预算500\" --save` 存一条。")
        return
    print("📚 送过的礼")
    for r in rows:
        print("  #%d  %s  %s  %s  %s 元  %s"
              % (r["id"], r["recipient"] or "—", r["occasion"] or "—", r["name"] or "—",
                 r["price"] if r["price"] is not None else "—", r["created_at"]))


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser():
    p = argparse.ArgumentParser(prog="songli", description="送礼 · 人情:三套方案、禁忌、预算拆分、话术。")
    p.add_argument("--version", action="version", version="songli %s" % __version__)
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 路径")
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("plan", help="出三套方案")
    pp.add_argument("--text", help="送给谁、什么场合、预算、偏好与禁忌")
    pp.add_argument("--file", help="从文件读")
    pp.add_argument("--recipient", help="记录用的收礼人")
    pp.add_argument("--save", action="store_true")
    pp.set_defaults(func=cmd_plan)

    cp = sub.add_parser("check", help="只查禁忌")
    cp.add_argument("--text", help="礼物或对方情况")
    cp.add_argument("--file", help="从文件读")
    cp.set_defaults(func=cmd_check)

    op = sub.add_parser("pool", help="看候选礼物池")
    op.add_argument("--text", help="关系/场合/预算")
    op.add_argument("--limit", type=int, default=12)
    op.set_defaults(func=cmd_pool)

    hp = sub.add_parser("history", help="送过的礼")
    hp.add_argument("--recipient", help="只看某个人")
    hp.add_argument("--limit", type=int, default=20)
    hp.set_defaults(func=cmd_history)

    wp = sub.add_parser("web", help="启动 Web 界面")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.add_argument("--mock", action="store_true", default=argparse.SUPPRESS)
    wp.set_defaults(func=cmd_web)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.mock and args.command == "plan" and not llm.default_config().get("api_key"):
        print(BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
