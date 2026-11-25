"""Orchestration: local filtering, model only for reasons and wording."""

import json
import re

from . import llm, mock, rules

MONEY_RE = re.compile(r"(?:¥|￥)?\d+(?:\.\d+)?\s*(?:元|块|万|k|K)")
BANNED_RE = re.compile(r"(?:钟|伞|鞋|刀|药|烟|酒|香水|白菊|绿帽)")


def strip_money(text):
    return MONEY_RE.sub("该价位", text or "")


def guard_reason(name, text, schemes):
    """Reason must belong to a local scheme and must not introduce a price."""
    if not name or name not in {g["name"] for g in schemes}:
        return None
    if MONEY_RE.search(text or ""):
        return None
    return text.strip()


def local_reasons(base):
    return [{"name": g["name"], "reason": g["reason"]} for g in base["schemes"]]


PROMPT = """你是送礼顾问。下面是程序按预算、关系、场合、禁忌筛出的三套方案,你只负责解释与措辞:
- 给每套方案一句理由(不要改价位、不要新造礼物)
- 给 3 句当面话术和 2 句被推辞时的接话
- 指出 2 条风险

只输出 JSON:
{"reasons": [{"name": "方案名", "reason": "..."}], "scripts": ["..."], "refuse": ["..."], "risks": ["..."]}

方案:
%s
"""


def analyze(text, sent=None, force_mock=False):
    brief = rules.parse(text)
    base = rules.check(brief, sent, text)
    if force_mock or not llm.default_config().get("api_key"):
        draft = mock.draft(base)
        mode = "offline"
    else:
        try:
            payload = json.dumps({"brief": brief, "schemes": [
                {k: g[k] for k in ("name", "tag", "low", "high", "category")} for g in base["schemes"]
            ], "taboos": [t["name"] for t in base["taboos"]]}, ensure_ascii=False, indent=2)
            raw = llm.chat([{"role": "user", "content": PROMPT % payload}])
            draft = llm.extract_json(raw)
            mode = "model"
        except Exception as e:
            draft = mock.draft(base)
            draft["error"] = str(e)
            mode = "offline"
    reasons = {}
    for item in draft.get("reasons") or []:
        if not isinstance(item, dict):
            continue
        ok = guard_reason(item.get("name"), item.get("reason"), base["schemes"])
        if ok:
            reasons[item["name"]] = strip_money(ok)
    for g in base["schemes"]:
        g["reason"] = reasons.get(g["name"]) or g["reason"]
    scripts = [strip_money(x) for x in (draft.get("scripts") or []) if str(x).strip()]
    refuse = [strip_money(x) for x in (draft.get("refuse") or []) if str(x).strip()]
    base["scripts"] = {
        "say": scripts or base["scripts"]["say"],
        "refuse": refuse or base["scripts"]["refuse"],
    }
    base["risks"] = [strip_money(x) for x in (draft.get("risks") or [])][:4] or mock.risks(base)
    base["mode"] = mode
    return base
