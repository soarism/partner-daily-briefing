#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 PushPlus 将每日简报以纯文字推送到个人微信。

读取 daily_data.json 构造纯文字摘要（无 markdown 符号，方便手机直接阅读），
POST 到 PushPlus API（template=txt）。未配置 token 时自动跳过；
主动防护失败时在正文顶部标注告警。
"""
import json
import os
import sys
import urllib.request

PUSHPLUS_API = "https://www.pushplus.plus/send"
REPO_URL = "https://github.com/soarism/partner-daily-briefing"
BRIEFING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_data.json")


def build_text(d):
    pe = d.get("pre_eval", {}) or {}
    ms = d.get("mid_sales", {}) or {}
    date = d.get("date", "")
    live = d.get("api_success")
    failed = d.get("live_failed")
    src = d.get("data_source", "")

    lines = []
    lines.append("📋 三级库合作伙伴评估体系 · 每日简报")
    lines.append("{} ｜ 数据来源：{}".format(
        date, "实时数据" if live else "快照数据（缓存/历史）"))
    if failed:
        lines.append("")
        lines.append("⚠️ 主动防护：实时数据获取失败，已回退至{}，请检查 TDOCS_TOKEN 配置".format(src))

    lines.append("")
    lines.append("【核心指标】")
    lines.append("🤝 合作伙伴总数：{}".format(d.get("partner_count", 114)))
    lines.append("✅ 已完成入库评估：{}（覆盖率 {}%）".format(pe.get("completed", 0), pe.get("coverage", 0)))
    lines.append("📦 极速通已签项目：{}".format(d.get("express_count", 66)))
    lines.append("🔧 售中支撑记录：{}".format(ms.get("total", 66)))
    lines.append("📅 本月更新：{} 条 ｜ 🗓️ 今年更新：{} 条".format(
        d.get("month_updated", 0), d.get("year_updated", 0)))

    alerts = d.get("alerts", []) or []
    if alerts:
        lines.append("")
        lines.append("【预警与建议】")
        for a in alerts[:5]:
            lines.append("- {}".format(a.get("title", "")))

    lines.append("")
    lines.append("完整简报（电脑端查看）：{}/blob/main/partner_daily_briefing.html".format(REPO_URL))
    return "\n".join(lines)


def main():
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        print("未配置 PUSHPLUS_TOKEN，跳过推送。")
        return 0
    if not os.path.exists(BRIEFING_PATH):
        print("未找到 daily_data.json，跳过推送。")
        return 0

    with open(BRIEFING_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)

    content = build_text(d)
    date = d.get("date", "")
    failed = d.get("live_failed")
    title = ("⚠️ 每日简报 {}".format(date)) if failed else ("每日简报 {}".format(date))

    payload = json.dumps(
        {
            "token": token,
            "title": title,
            "content": content,
            "template": "txt",
            "channel": "wechat",
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        PUSHPLUS_API,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            print("PushPlus 推送响应:", body)
            try:
                if json.loads(body).get("code") != 200:
                    print("⚠️ PushPlus 返回非成功状态码")
            except Exception:
                pass
    except Exception as e:
        print("PushPlus 推送失败:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
