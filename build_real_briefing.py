#!/usr/bin/env python3
"""
实时简报生成器（沙箱版）
========================
从 live_cache/ 下的真实抓取数据生成每日简报，标记 api_success=True（实时数据）。
数据由腾讯文档 MCP 连接器抓取后落盘到 live_cache/。
"""
import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "live_cache")
BRIEFING_FILE = os.path.join(BASE, "partner_daily_briefing.html")
DATA_FILE = os.path.join(BASE, "daily_data.json")


def load(sheet):
    with open(os.path.join(CACHE, f"{sheet}.json"), "r", encoding="utf-8") as f:
        return json.load(f).get("records", [])


def opt_text(fv):
    items = fv.get("option_value", {}).get("items", [])
    return items[0].get("text", "") if items else ""


def txt(fv):
    items = fv.get("text_value", {}).get("items", [])
    return items[0].get("text", "") if items else ""


def analyze_pre_eval(records):
    total = len(records)
    completed = partial = empty = 0
    for r in records:
        fields = {fv.get("field", "") for fv in r.get("field_values", [])}
        eval_fields = fields - {"合作伙伴"}
        if len(eval_fields) >= 4:
            completed += 1
        elif len(eval_fields) >= 1:
            partial += 1
        else:
            empty += 1
    return {
        "total": total, "completed": completed, "partial": partial, "empty": empty,
        "coverage": round(completed / total * 100, 1) if total else 0,
    }


def analyze_mid_sales(records):
    stats = {
        "total": len(records), "delivery_on_time": 0, "delivery_late": 0,
        "quality_ok": 0, "quality_issue": 0, "satisfaction_normal_plus": 0,
        "satisfaction_bad": 0, "cooperation_good": 0, "cooperation_bad": 0,
        "alert_items": [],
    }
    for r in records:
        partner = ""
        for fv in r.get("field_values", []):
            if fv.get("field") == "合作伙伴":
                partner = txt(fv)
            elif fv.get("field") == "交付及时性":
                t = opt_text(fv)
                if t == "按时交付":
                    stats["delivery_on_time"] += 1
                elif t == "超时交付":
                    stats["delivery_late"] += 1
                    stats["alert_items"].append({"partner": partner, "issue": "超时交付"})
            elif fv.get("field") == "交付质量":
                t = opt_text(fv)
                if t == "无质量问题":
                    stats["quality_ok"] += 1
                elif t == "有质量问题":
                    stats["quality_issue"] += 1
            elif fv.get("field") == "业主满意度":
                t = opt_text(fv)
                if t in ("正常", "非常满意"):
                    stats["satisfaction_normal_plus"] += 1
                elif t == "不满意":
                    stats["satisfaction_bad"] += 1
            elif fv.get("field") == "配合程度":
                t = opt_text(fv)
                if t in ("配合", "主动配合"):
                    stats["cooperation_good"] += 1
                elif t == "有不配合的现象":
                    stats["cooperation_bad"] += 1
    return stats


def generate_html(data, changes):
    today = datetime.now()
    date_str = today.strftime("%Y年%m月%d日")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today.weekday()]
    time_str = today.strftime("%H:%M")

    pre_eval = data["pre_eval"]
    mid_sales = data["mid_sales"]
    coverage = pre_eval["coverage"]
    coverage_color = "#059669" if coverage >= 50 else ("#d97706" if coverage >= 25 else "#dc2626")

    changes_html = ""
    if changes:
        items = "".join([f"<li>{c}</li>" for c in changes])
        changes_html = f"""
        <div class="section" style="border-left:4px solid #7c3aed;">
          <div class="section-title"><span class="icon">🔄</span> 较上次核实变化</div>
          <div class="section-body"><ul style="font-size:14px;line-height:2;">{items}</ul></div>
        </div>"""

    alerts = data.get("alerts", [])
    alerts_html = ""
    if alerts:
        a_items = ""
        for a in alerts:
            a_items += f"""
            <div class="alert-item">
              <div class="alert-dot {a.get('color','yellow')}"></div>
              <div><strong>{a.get('title','')}</strong>
              <p style="font-size:13px;color:var(--text-secondary);">{a.get('desc','')}</p></div>
            </div>"""
        alerts_html = f"""
        <div class="section">
          <div class="section-title"><span class="icon">⚠️</span> 预警与建议</div>
          <div class="section-body">{a_items}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>三级库合作伙伴评估体系 - 每日简报</title>
<style>
  :root {{ --bg:#f5f7fa;--card-bg:#fff;--text:#1a1a2e;--text-secondary:#6b7280;--border:#e5e7eb;--accent:#2563eb;--success:#059669;--warning:#d97706;--danger:#dc2626;--info:#7c3aed; }}
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:24px; }}
  .container {{ max-width:1000px;margin:0 auto; }}
  .header {{ background:linear-gradient(135deg,#1e3a5f,#2563eb);color:#fff;border-radius:16px;padding:32px;margin-bottom:24px;box-shadow:0 4px 20px rgba(37,99,235,.15); }}
  .header h1 {{ font-size:28px;font-weight:700;margin-bottom:4px; }}
  .header .subtitle {{ opacity:.85;font-size:16px; }}
  .header .date {{ margin-top:12px;font-size:14px;opacity:.7; }}
  .header .update-time {{ font-size:12px;opacity:.5;margin-top:4px; }}
  .overview {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px; }}
  .stat-card {{ background:var(--card-bg);border-radius:12px;padding:20px;border:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,.04); }}
  .stat-card .label {{ font-size:13px;color:var(--text-secondary);margin-bottom:6px; }}
  .stat-card .value {{ font-size:32px;font-weight:700; }}
  .section {{ background:var(--card-bg);border-radius:12px;border:1px solid var(--border);margin-bottom:20px;overflow:hidden; }}
  .section-title {{ font-size:17px;font-weight:600;padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px; }}
  .section-body {{ padding:20px 24px; }}
  table {{ width:100%;border-collapse:collapse;font-size:14px; }}
  th,td {{ padding:10px 14px;text-align:left;border-bottom:1px solid var(--border); }}
  th {{ background:#f8fafc;font-weight:600;color:var(--text-secondary);font-size:12px;text-transform:uppercase; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:500; }}
  .badge.green {{ background:#ecfdf5;color:#059669; }}
  .badge.red {{ background:#fef2f2;color:#dc2626; }}
  .badge.yellow {{ background:#fffbeb;color:#d97706; }}
  .badge.blue {{ background:#eff6ff;color:#2563eb; }}
  .badge.purple {{ background:#f5f3ff;color:#7c3aed; }}
  .progress-bar {{ height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;margin-top:6px; }}
  .progress-bar .fill {{ height:100%;border-radius:4px; }}
  .alert-item {{ display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid var(--border); }}
  .alert-item:last-child {{ border-bottom:none; }}
  .alert-dot {{ width:8px;height:8px;border-radius:50%;margin-top:6px;flex-shrink:0; }}
  .alert-dot.red {{ background:#dc2626; }} .alert-dot.yellow {{ background:#d97706; }} .alert-dot.blue {{ background:#2563eb; }}
  .footer {{ text-align:center;padding:20px;color:var(--text-secondary);font-size:12px; }}
  .status-tag {{ display:inline-flex;align-items:center;gap:4px;font-size:13px;padding:4px 12px;border-radius:20px; }}
  .status-tag.live {{ background:#ecfdf5;color:#059669; }}
  .status-tag.cached {{ background:#fef3c7;color:#d97706; }}
</style></head>
<body>
<div class="container">
  <div class="header">
    <h1>📋 三级库合作伙伴评估体系</h1>
    <div class="subtitle">每日数据简报（实时核实）</div>
    <div class="date">{date_str} {weekday}</div>
    <div class="update-time">数据获取时间：{time_str} |
      <span class="status-tag {'live' if data.get('api_success') else 'cached'}">{'🔗 实时数据' if data.get('api_success') else '📦 快照数据'}</span>
    </div>
  </div>
  <div class="overview">
    <div class="stat-card"><div class="label">🤝 合作伙伴总数</div><div class="value" style="color:var(--accent);">{data.get('partner_count',114)}</div></div>
    <div class="stat-card"><div class="label">✅ 已完成入库评估</div><div class="value" style="color:{coverage_color};">{pre_eval['completed']}</div>
      <div class="progress-bar"><div class="fill" style="width:{coverage}%;background:{coverage_color};"></div></div>
      <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">覆盖率 {coverage}%</div></div>
    <div class="stat-card"><div class="label">📦 极速通已签项目</div><div class="value" style="color:#7c3aed;">{data.get('express_count',66)}</div></div>
    <div class="stat-card"><div class="label">🔧 售中支撑记录</div><div class="value" style="color:#0891b2;">{mid_sales.get('total',66)}</div></div>
  </div>
  {changes_html}
  <div class="section">
    <div class="section-title"><span class="icon">📝</span> 入库前能力评估状态</div>
    <div class="section-body"><table>
      <tr><th>状态</th><th>数量</th><th>占比</th><th>说明</th></tr>
      <tr><td><span class="badge green">已完成评估</span></td><td><strong>{pre_eval['completed']}</strong></td><td>{coverage}%</td><td>含方案/交付/培训/场景/代理/案例等能力项</td></tr>
      <tr><td><span class="badge yellow">部分评估</span></td><td><strong>{pre_eval['partial']}</strong></td><td>{round(pre_eval['partial']/pre_eval['total']*100,1)}%</td><td>已录入部分能力项</td></tr>
      <tr><td><span class="badge red">待评估</span></td><td><strong>{pre_eval['empty']}</strong></td><td>{round(pre_eval['empty']/pre_eval['total']*100,1)}%</td><td>仅录入名称，尚未评估</td></tr>
    </table></div>
  </div>
  <div class="section">
    <div class="section-title"><span class="icon">🔧</span> 售中支撑记录 - 评估概览</div>
    <div class="section-body"><table>
      <tr><th>评估维度</th><th>正常/优秀</th><th>问题项</th><th>状态</th></tr>
      <tr><td>交付及时性</td><td>按时交付：{mid_sales.get('delivery_on_time','—')}</td><td>超时交付：{mid_sales.get('delivery_late','—')}</td><td>{'<span class="badge green">正常</span>' if mid_sales.get('delivery_late',1)<=1 else '<span class="badge yellow">需关注</span>'}</td></tr>
      <tr><td>交付质量</td><td>无质量问题：{mid_sales.get('quality_ok','—')}</td><td>有质量问题：{mid_sales.get('quality_issue','—')}</td><td>{'<span class="badge green">正常</span>' if mid_sales.get('quality_issue',1)<=1 else '<span class="badge yellow">需关注</span>'}</td></tr>
      <tr><td>业主满意度</td><td>正常/非常满意：{mid_sales.get('satisfaction_normal_plus','—')}</td><td>不满意：{mid_sales.get('satisfaction_bad','—')}</td><td>{'<span class="badge green">正常</span>' if mid_sales.get('satisfaction_bad',1)<=1 else '<span class="badge yellow">需关注</span>'}</td></tr>
      <tr><td>配合程度</td><td>配合/主动配合：{mid_sales.get('cooperation_good','—')}</td><td>有不配合现象：{mid_sales.get('cooperation_bad','—')}</td><td>{'<span class="badge green">正常</span>' if mid_sales.get('cooperation_bad',1)<=1 else '<span class="badge yellow">需关注</span>'}</td></tr>
    </table></div>
  </div>
  {alerts_html}
  <div class="footer">本简报由腾讯文档连接器实时抓取生成 | 三级库合作伙伴评估体系 | {date_str}<br>数据来源：WB-三级库合作伙伴评估体系智能表格 | 每天下午 5:00 自动更新</div>
</div>
</body>
</html>"""


def main():
    print("=" * 60)
    print("三级库合作伙伴评估体系 - 实时简报生成（沙箱版）")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    pre_records = load("pre_eval")
    mid_records = load("mid_sales")
    express_records = load("express")
    partner_records = load("partner_list") if os.path.exists(os.path.join(CACHE, "partner_list.json")) else None

    print(f"[1/4] 入库前能力评估: {len(pre_records)} 条")
    print(f"[2/4] 售中支撑记录: {len(mid_records)} 条")
    print(f"[3/4] 极速通已签项目: {len(express_records)} 条")

    pre_eval = analyze_pre_eval(pre_records)
    mid_sales = analyze_mid_sales(mid_records)
    print(f"  入库评估: {pre_eval['completed']}/{pre_eval['total']} 完成 ({pre_eval['coverage']}%)")
    print(f"  售中支撑: {mid_sales['total']} 条 | 超时:{mid_sales['delivery_late']} 质量问题:{mid_sales['quality_issue']} 不满意:{mid_sales['satisfaction_bad']} 不配合:{mid_sales['cooperation_bad']}")

    alerts = [{
        "color": "red" if pre_eval["coverage"] < 25 else "yellow",
        "title": f"入库评估覆盖率 {'偏低' if pre_eval['coverage'] < 25 else '需持续关注'}",
        "desc": f"当前 {pre_eval['coverage']}%（{pre_eval['completed']}/{pre_eval['total']}），{'建议加快评估进度' if pre_eval['coverage'] < 25 else '持续推进中'}。",
    }]
    if mid_sales.get("delivery_late", 0) > 0:
        alerts.append({"color": "red", "title": f"售中超时交付: {mid_sales['delivery_late']} 条",
                       "desc": "；".join([f"{a['partner']}（{a['issue']}）" for a in mid_sales.get("alert_items", [])[:5]])})
    if mid_sales.get("cooperation_bad", 0) > 0:
        alerts.append({"color": "yellow", "title": f"配合度问题: {mid_sales['cooperation_bad']} 条", "desc": "存在不配合现象，需跟进沟通。"})

    current = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "api_success": True,
        "partner_count": len(partner_records) if partner_records else 114,
        "express_count": len(express_records),
        "pre_eval": pre_eval,
        "mid_sales": mid_sales,
        "alerts": alerts,
    }

    previous = {}
    if os.path.exists(DATA_FILE):
        try:
            previous = json.load(open(DATA_FILE, encoding="utf-8"))
        except Exception:
            previous = {}
    changes = []
    if previous:
        pe = previous.get("pre_eval", {})
        if pe.get("completed", 0) != current["pre_eval"]["completed"]:
            d = current["pre_eval"]["completed"] - pe.get("completed", 0)
            changes.append(f"入库评估完成数: {pe.get('completed',0)} → {current['pre_eval']['completed']} ({'+' if d>0 else ''}{d})")
        pm = previous.get("mid_sales", {}).get("total", 0)
        cm = current["mid_sales"]["total"]
        if pm != cm:
            changes.append(f"售中支撑记录: {pm} → {cm} ({'+' if cm-pm>0 else ''}{cm-pm})")

    html = generate_html(current, changes)
    with open(BRIEFING_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    print(f"[4/4] 简报已生成: {BRIEFING_FILE}")
    print("实时简报生成完成!")


if __name__ == "__main__":
    main()
