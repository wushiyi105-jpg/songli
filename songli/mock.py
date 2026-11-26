"""Offline draft: local reasons and scripts, same shape as the model answer."""


def risks(base):
    out = []
    brief = base["brief"]
    if base.get("note"):
        out.append(base["note"])
    if not brief.get("budget"):
        out.append("没写预算,方案按关系与场合挑,价位可能超出预期。")
    if not brief.get("relation"):
        out.append("没写关系类别(父母 / 长辈 / 伴侣 / 朋友 / 同事 / 领导 / 客户 / 孩子 / 老师),话术按通用口径。")
    if not brief.get("occasion"):
        out.append("没写场合,同样的礼物在生日和探病是两回事。")
    for t in base["taboos"]:
        out.append("你自己提到「%s」:按禁忌规则要避开,方案池里已剔除相关品类。" % t["name"])
    if base["sent_filtered"]:
        out.append("已排除送过的 %d 件,避免撞礼。" % len(base["sent_filtered"]))
    return out[:4] or ["按当前条件看没有明显风险,注意别当众比较价位。"]


def draft(base):
    return {
        "reasons": [{"name": g["name"], "reason": g["reason"]} for g in base["schemes"]],
        "scripts": base["scripts"]["say"],
        "refuse": base["scripts"]["refuse"],
        "risks": risks(base),
    }
