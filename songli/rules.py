"""Local logic: parse brief, filter pool, taboo check, budget split, timing and scripts."""

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_CACHE = {}

RELATIONS = ["父母", "长辈", "伴侣", "朋友", "同事", "领导", "客户", "孩子", "老师"]
OCCASIONS = ["生日", "婚礼", "乔迁", "满月", "节日", "探病", "毕业", "职场", "纪念日", "感谢"]

# 口语里的称呼:命中这些词就归到对应关系类别,不然会判成「没写送给谁」
SYNONYMS = (
    ("父母", ("爸爸", "妈妈", "爸妈", "父亲", "母亲", "老爹", "老妈")),
    ("长辈", ("爷爷", "奶奶", "外公", "外婆", "姥姥", "姥爷", "叔叔", "阿姨",
              "舅舅", "姑姑", "伯伯", "岳父", "岳母")),
    ("伴侣", ("老公", "老婆", "对象", "男朋友", "女朋友", "爱人", "男友", "女友")),
    ("朋友", ("闺蜜", "好友", "同学", "兄弟", "姐妹", "室友")),
    ("同事", ("同组", "组里", "搭档")),
    ("领导", ("老板", "上司", "主管")),
    ("客户", ("甲方", "供应商")),
    ("孩子", ("儿子", "女儿", "外甥", "外甥女", "侄子", "侄女", "孙子", "孙女", "小朋友")),
    ("老师", ("教授", "班主任", "导师")),
)

TIMING = {
    "生日": "当天送到,或提前一天;不要迟到后补,补送要单独说明",
    "婚礼": "提前一周送到新房,当天只带红包与祝福",
    "乔迁": "入宅后一周内上门,带礼物别带刀具",
    "满月": "满月酒当天交给家长,直接给大人,别塞给婴儿",
    "节日": "节前 3–7 天,避开节前快递高峰",
    "探病": "探视时间内,先问护士站能否带花与食物",
    "毕业": "离校前一周,别等到散伙饭",
    "职场": "私下给,不要在工位当众递,避免比较",
    "纪念日": "当天,提前订好位置或安排好时间",
    "感谢": "事成后一周内,越晚越像客套",
}

SCRIPTS = {
    "父母": ["没挑贵的,挑了个您平时用得上的,先用着试试。", "知道您不缺东西,就是看着合适,顺手带一个。"],
    "长辈": ["不值什么钱,是个心意,您别嫌轻。", "听说您喜欢这个,正好看到就带了。"],
    "伴侣": ["不是节日才买,是看到就想到你。", "这个我挑了很久,你看看喜不喜欢。"],
    "朋友": ["别客气,咱俩不讲这个。", "你不是一直想要吗,正好碰到。"],
    "同事": ["顺手带的,别当回事,大家一起用。", "不值钱,就是觉得你用得上。"],
    "领导": ["一点心意,感谢这段时间的指点。", "不是贵重东西,您留着用。"],
    "客户": ["一点地方特产,给您尝尝鲜。", "合作顺利,表达个心意,不成敬意。"],
    "孩子": ["这是给你的,自己拆。", "表现不错,这是奖励,不是每次都有。"],
    "老师": ["孩子这点进步多亏您,一点心意,您别推。", "不是贵重东西,就是份感谢。"],
}

REFUSAL = ["您别推,推来推去我反而不好意思。", "真不值钱,您收着,下次我不带了。"]


def load(name):
    if name not in _CACHE:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            _CACHE[name] = json.load(f)
    return _CACHE[name]


def gifts():
    return load("gifts.json")["gifts"]


def taboo_rules():
    return load("taboos.json")["rules"]


BUDGET_RE = re.compile(r"(?:预算|大概|差不多)?\s*(\d{2,6})\s*(?:元|块)?(?:\s*[-–~到]\s*(\d{2,6}))?")
ZH_BUDGET_RE = re.compile(r"(?:预算|大概|差不多|约)\s*([一二两三四五六七八九十百千万]+)\s*(?:元|块)?|([一二两三四五六七八九十百千万]+)\s*(?:元|块)")
_ZH_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def zh_number(s):
    """中文数字转整数:「五百」→500、「一千二」→1200、「两百五」→250。"""
    total, cur, last_unit = 0, 0, None
    for ch in s or "":
        if ch in _ZH_DIGITS:
            cur = _ZH_DIGITS[ch]
        elif ch in _ZH_UNITS:
            unit = _ZH_UNITS[ch]
            if unit == 10000:
                total = (total + cur) * 10000 if (total + cur) else 10000
            else:
                total += (cur or 1) * unit
            cur, last_unit = 0, unit
    if cur:
        # 「一百五」「一千二」这类省略说法:末位数字按上一个单位的十分之一算
        total += cur * (last_unit // 10) if last_unit and last_unit >= 100 else cur
    return total


def parse(text):
    low = text or ""
    relation = next((r for r in RELATIONS if r in low), None)
    if not relation:
        relation = next((cat for cat, words in SYNONYMS if any(w in low for w in words)), None)
    occasion = next((o for o in OCCASIONS if o in low), None)
    m = None
    for cand in BUDGET_RE.finditer(low):
        if int(cand.group(1)) >= 50:
            m = cand
            break
    budget = None
    if m:
        budget = int(m.group(2) or m.group(1))
    else:
        for cand in ZH_BUDGET_RE.finditer(low):
            value = zh_number(cand.group(1) or cand.group(2))
            if value >= 50:
                budget = value
                break
    allergies = [w for w in ("过敏", "不吃", "忌口", "素食", "清真", "不喝酒", "不抽烟") if w in low]
    interests = [w for w in ("茶", "咖啡", "书", "运动", "香", "花", "手作", "数码", "做饭") if w in low]
    return {"relation": relation, "occasion": occasion, "budget": budget,
            "allergies": allergies, "interests": interests}


def split_budget(budget):
    if not budget:
        return {"main": None, "flower": None, "card": None, "wrap": None}
    main = int(round(budget * 0.8 / 10) * 10)
    flower = int(round(budget * 0.12 / 10) * 10)
    card = max(5, int(round(budget * 0.04)))
    if main + flower + card > budget:
        # 预算太小:先砍花,再砍卡,最后主礼兜底,四格不允许出现负数
        flower = max(0, budget - main - card)
        if main + flower + card > budget:
            card = max(0, budget - main)
        if main + flower + card > budget:
            main = max(0, budget - flower - card)
    wrap = budget - main - flower - card
    return {"main": main, "flower": flower, "card": card, "wrap": wrap, "total": budget}


def taboo_hits(text):
    """Taboo rules triggered by the user's own words (对方不喝酒 / 香水过敏 / 长辈)."""
    low = text or ""
    return [r for r in taboo_rules() if any(k in low for k in r["keywords"])]


def gift_taboo(gift):
    name = gift["name"]
    return [r for r in taboo_rules() if any(k in name for k in r["keywords"])]


def pool(relation=None, occasion=None, budget=None, sent=None, interests=None):
    sent = set(sent or [])
    out = []
    for g in gifts():
        if g["name"] in sent:
            continue
        if relation and relation not in g["relations"]:
            continue
        if occasion and occasion not in g["occasions"]:
            continue
        if budget and g["low"] > budget:
            continue
        if gift_taboo(g):
            continue
        if interests:
            hit = sum(1 for w in interests if w in g["name"] or w in g["tag"])
        else:
            hit = 0
        out.append({**g, "interest": hit})
    return out


def score(g, relation, occasion, budget):
    s = 0
    if relation and relation in g["relations"]:
        s += 3
    if occasion and occasion in g["occasions"]:
        s += 3
    if budget:
        ratio = ((g["low"] + g["high"]) / 2) / budget
        if 0.6 <= ratio <= 1.0:
            s += 4
        elif 0.3 <= ratio < 0.6:
            s += 2
    s += g.get("interest", 0) * 3
    return s


def _band(g, budget):
    if not budget:
        return "mid"
    main = max(1, budget * 0.8)
    ratio = (g["low"] + g["high"]) / 2 / main
    if ratio < 0.4:
        return "low"
    if ratio < 0.85:
        return "mid"
    return "high"


def schemes(brief, sent=None, limit=3):
    relation, occasion, budget = brief.get("relation"), brief.get("occasion"), brief.get("budget")
    candidates = pool(relation, occasion, budget, sent, brief.get("interests"))
    if not candidates:
        candidates = pool(relation, occasion, None, sent, brief.get("interests"))
    if not candidates:
        # 场合在池里没有对应品类(比如满月):退回按关系与预算挑,别给出空方案
        candidates = (pool(relation, None, budget, sent, brief.get("interests"))
                      or pool(relation, None, None, sent, brief.get("interests")))
    if not candidates:
        candidates = pool(None, None, budget, sent, brief.get("interests"))
    scored = sorted(candidates, key=lambda g: (-score(g, relation, occasion, budget), g["low"]))
    picked = []
    used_cat = set()
    if budget:
        for band in ("mid", "low", "high"):
            for g in scored:
                if _band(g, budget) == band and g["category"] not in used_cat and g not in picked:
                    picked.append(g)
                    used_cat.add(g["category"])
                    break
    for g in scored:
        if len(picked) >= limit:
            break
        if g in picked or g["category"] in used_cat:
            continue
        picked.append(g)
        used_cat.add(g["category"])
    for g in scored:
        if len(picked) >= limit:
            break
        if g not in picked:
            picked.append(g)
    return picked


def reason(g, brief):
    relation, occasion = brief.get("relation"), brief.get("occasion")
    parts = []
    if relation and relation in g["relations"]:
        parts.append("适合送%s" % relation)
    if occasion and occasion in g["occasions"]:
        parts.append("贴%s场合" % occasion)
    parts.append("%s,价位 %d–%d 元" % (g["tag"], g["low"], g["high"]))
    return ",".join(parts) + "。"


def timing(brief):
    return TIMING.get(brief.get("occasion"), "提前 3–7 天准备好,当天当面给")


def scripts(brief):
    key = brief.get("relation")
    return {"say": SCRIPTS.get(key, ["一点心意,您收着。"]), "refuse": REFUSAL}


def check(brief, sent=None, text=None):
    picked = schemes(brief, sent)
    note = None
    if not picked:
        note = "礼物池里没有同时满足关系、场合与预算的品类,先把预算或场合放宽一条。"
    elif brief.get("occasion") and not pool(None, brief["occasion"], None):
        note = ("礼物池里还没有「%s」场合的对应品类,方案按关系与预算挑,"
                "时机与话术仍按场合给。" % brief["occasion"])
    return {
        "brief": brief,
        "split": split_budget(brief.get("budget")),
        "taboos": taboo_hits(text),
        "avoided": sorted({r["name"] for g in gifts() for r in gift_taboo(g)}),
        "schemes": [dict(g, reason=reason(g, brief)) for g in picked],
        "timing": timing(brief),
        "scripts": scripts(brief),
        "sent_filtered": sorted(set(sent or [])),
        "note": note,
    }
