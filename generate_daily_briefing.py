#!/usr/bin/env python3
"""
三级库合作伙伴评估体系 - 每日简报生成系统
===========================================
通过腾讯文档 API 自动获取智能表格数据，生成每日简报 HTML。
配合工蜂 CI 定时流水线，每天下午 5:00 自动运行。

表格结构：
- t00i2h: 综合情况及评分 (114条)
- trLD8T: 入库前能力评估 (118条)
- tVbMml: 售前支撑记录、评估 (3条)
- tqrs1H: 售中支撑记录、评估 (66条)
- tuAwI3: 售后支撑加扣分记录 (0条)
- t4khjh: 场景梳理 (27条)
- ttKzck: 极速通已签项目 (66条)
- tWujqj: 合作伙伴清单 (114条)
"""

import json
import os
import sys
from datetime import datetime
from collections import Counter

# ============================================================
# 配置
# ============================================================
FILE_ID = "QwBeLNOgcHHF"  # WB-三级库合作伙伴评估体系 智能表格 ID

# 工作表映射
SHEETS = {
    "comprehensive": "t00i2h",   # 综合情况及评分
    "pre_eval": "trLD8T",        # 入库前能力评估
    "pre_sales": "tVbMml",       # 售前支撑记录、评估
    "mid_sales": "tqrs1H",       # 售中支撑记录、评估
    "post_sales": "tuAwI3",      # 售后支撑加扣分记录
    "scenes": "t4khjh",          # 场景梳理
    "express_projects": "ttKzck", # 极速通已签项目
    "partner_list": "tWujqj",    # 合作伙伴清单
}

BRIEFING_DIR = os.path.dirname(os.path.abspath(__file__))
BRIEFING_FILE = os.path.join(BRIEFING_DIR, "partner_daily_briefing.html")
DATA_FILE = os.path.join(BRIEFING_DIR, "daily_data.json")
LOG_DIR = os.path.join(BRIEFING_DIR, "logs")

# ============================================================
# 数据获取层（通过腾讯文档 MCP API）
# 在工蜂 CI 环境中，需配置 TDOCS_API_BASE 和 TDOCS_TOKEN 环境变量
# ============================================================

def _mcp_rpc(api_base, token, payload, session_id=None):
    """调用腾讯文档 MCP（Streamable HTTP）端点，返回 (解析后JSON, session_id)。"""
    import urllib.request
    import urllib.error
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(api_base, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            return _parse_sse_or_json(raw), sid
    except urllib.error.HTTPError as e:
        print(f"  [WARN] MCP 调用失败 {e.code}: {e.read().decode()[:200]}")
        return None, None
    except urllib.error.URLError as e:
        print(f"  [WARN] MCP 连接失败: {e}")
        return None, None


def _parse_sse_or_json(raw):
    if not raw:
        return None
    if "data:" in raw or "event:" in raw:
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        out.append(json.loads(chunk))
                    except Exception:
                        pass
        return out[-1] if out else None
    try:
        return json.loads(raw)
    except Exception:
        return None


# 实时抓取状态（供“主动防护”使用）：标记是否真正尝试了实时 API、以及失败原因
LIVE_ATTEMPTED = False
LIVE_FAIL_REASON = ""

def fetch_records(sheet_id, limit=200):
    global LIVE_ATTEMPTED, LIVE_FAIL_REASON
    """
    从腾讯文档获取工作表记录，按优先级：
    1. 配置了 TDOCS_API_BASE / TDOCS_TOKEN（个人 Token）→ 直接调用公网 MCP 端点（真正实时）。
    2. 未配置 → 读取 live_cache/ 中由沙箱抓取落盘的真实记录。
    3. 再无 → 返回 None（上层用 daily_data.json 快照兜底）。
    """
    api_base = os.environ.get("TDOCS_API_BASE", "").rstrip("/")
    token = os.environ.get("TDOCS_TOKEN", "")

    if api_base and token:
        LIVE_ATTEMPTED = True
        # 1) initialize 握手（捕获 session id）
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "partner-briefing", "version": "1.0"}}}
        init_res, sid = _mcp_rpc(api_base, token, init)
        if not init_res or "result" not in init_res:
            LIVE_FAIL_REASON = LIVE_FAIL_REASON or "live_api_failed"
            print("  [WARN] MCP initialize 失败，回退 live_cache")
        else:
            # 2) tools/call smartsheet_list_records
            call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "smartsheet.list_records",
                               "arguments": {"file_id": FILE_ID, "sheet_id": sheet_id, "limit": limit}}}
            res, _ = _mcp_rpc(api_base, token, call, session_id=sid)
            if res and "result" in res:
                for c in res["result"].get("content", []):
                    if c.get("type") == "text":
                        try:
                            data = json.loads(c["text"])
                            if "records" in data:
                                return data, "live"
                        except Exception:
                            pass
                # 部分实现把结果直接放在 result 顶层
                if "records" in res.get("result", {}):
                    return res["result"], "live"
            print("  [WARN] MCP 返回结构异常，回退 live_cache")

    # 回退：live_cache
    if LIVE_ATTEMPTED:
        LIVE_FAIL_REASON = LIVE_FAIL_REASON or "live_api_failed"
    cache_name = {"trLD8T": "pre_eval", "tqrs1H": "mid_sales", "ttKzck": "express"}.get(sheet_id)
    if cache_name:
        cache_path = os.path.join(BRIEFING_DIR, "live_cache", f"{cache_name}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  ✓ 从 live_cache 读取 {cache_name}：{len(data.get('records', []))} 条")
                return data, "cache"
            except Exception as e:
                print(f"  [WARN] live_cache 读取失败: {e}")
    return None, "none"

def load_snapshot():
    """加载上次数据快照"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_snapshot(data):
    """保存当前数据快照"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============================================================
# 数据分析
# ============================================================

def analyze_pre_eval(records, snap=None):
    """分析入库前能力评估数据。records 为 None 时回退到最近一次真实快照。"""
    if records:
        total = len(records)
        completed = partial = empty = 0
        for r in records:
            fvs = r.get("field_values", [])
            field_names = {fv.get("field", "") for fv in fvs}
            eval_fields = field_names - {"合作伙伴"}
            if len(eval_fields) >= 4:
                completed += 1
            elif len(eval_fields) >= 1:
                partial += 1
            else:
                empty += 1
        return {
            "total": total, "completed": completed, "partial": partial, "empty": empty,
            "coverage": round(completed / total * 100, 1) if total > 0 else 0
        }
    # 无实时数据：使用最近一次真实快照（由沙箱实时抓取生成）
    if snap and snap.get("pre_eval"):
        return snap["pre_eval"]
    return {"total": 118, "completed": 22, "partial": 3, "empty": 93, "coverage": 18.6}

def analyze_mid_sales(records, snap=None):
    """分析售中支撑记录。records 为 None 时回退到最近一次真实快照。"""
    if records:
        stats = {
            "total": len(records),
            "delivery_on_time": 0,
            "delivery_late": 0,
            "quality_ok": 0,
            "quality_issue": 0,
            "satisfaction_normal_plus": 0,
            "satisfaction_bad": 0,
            "cooperation_good": 0,
            "cooperation_bad": 0,
            "alert_items": []
        }
        for r in records:
            for fv in r.get("field_values", []):
                field = fv.get("field", "")
                opt = fv.get("option_value", {})
                items = opt.get("items", [])
                
                if field == "交付及时性":
                    if items and items[0].get("text") in ["按时交付"]:
                        stats["delivery_on_time"] += 1
                    elif items and items[0].get("text") in ["超时交付"]:
                        stats["delivery_late"] += 1
                        stats["alert_items"].append({
                            "project": _get_project(r),
                            "partner": _get_partner(r),
                            "issue": "超时交付"
                        })
                elif field == "交付质量":
                    if items and items[0].get("text") in ["无质量问题"]:
                        stats["quality_ok"] += 1
                    elif items and items[0].get("text") in ["有质量问题"]:
                        stats["quality_issue"] += 1
                elif field == "业主满意度":
                    if items and items[0].get("text") in ["正常", "非常满意"]:
                        stats["satisfaction_normal_plus"] += 1
                    elif items and items[0].get("text") in ["不满意"]:
                        stats["satisfaction_bad"] += 1
                elif field == "配合程度":
                    if items and items[0].get("text") in ["配合", "主动配合"]:
                        stats["cooperation_good"] += 1
                elif items and items[0].get("text") in ["有不配合的现象"]:
                    stats["cooperation_bad"] += 1
        return stats
    # 无实时数据：使用最近一次真实快照
    if snap and snap.get("mid_sales"):
        return snap["mid_sales"]
    return {"total": 66, "delivery_on_time": 0, "delivery_late": 0, "quality_ok": 0,
            "quality_issue": 0, "satisfaction_normal_plus": 0, "satisfaction_bad": 0,
            "cooperation_good": 0, "cooperation_bad": 0, "alert_items": []}

def _get_project(record):
    for fv in record.get("field_values", []):
        if fv.get("field") == "项目名称":
            items = fv.get("text_value", {}).get("items", [])
            if items:
                return items[0].get("text", "")[:60]
    return "未知项目"

def _get_partner(record):
    for fv in record.get("field_values", []):
        if fv.get("field") == "合作伙伴":
            items = fv.get("text_value", {}).get("items", [])
            if items:
                return items[0].get("text", "")
    return "未知"

def detect_changes(current, previous):
    """对比数据变化"""
    changes = []
    if not previous:
        return changes
    
    prev_date = previous.get("date", "未知")
    
    # 检查入库评估数量变化
    prev_eval = previous.get("pre_eval", {})
    curr_eval = current.get("pre_eval", {})
    if prev_eval.get("completed", 0) != curr_eval.get("completed", 0):
        diff = curr_eval.get("completed", 0) - prev_eval.get("completed", 0)
        changes.append(f"入库评估完成数: {prev_eval.get('completed', 0)} → {curr_eval.get('completed', 0)} ({'+' if diff > 0 else ''}{diff})")
    
    # 检查售中支撑记录数量变化
    prev_mid = previous.get("mid_sales", {}).get("total", 0)
    curr_mid = current.get("mid_sales", {}).get("total", 0)
    if prev_mid != curr_mid:
        changes.append(f"售中支撑记录: {prev_mid} → {curr_mid} ({'+' if curr_mid - prev_mid > 0 else ''}{curr_mid - prev_mid})")
    
    return changes

# ============================================================
# HTML 简报生成
# ============================================================

def generate_html(data, changes):
    """生成简报 HTML"""
    today = datetime.now()
    date_str = today.strftime("%Y年%m月%d日")
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today.weekday()]
    time_str = today.strftime("%H:%M")
    
    pre_eval = data.get("pre_eval", {"total": 118, "completed": 22, "partial": 3, "empty": 93, "coverage": 18.6})
    mid_sales = data.get("mid_sales", {"total": 66})
    
    coverage = pre_eval["coverage"]
    coverage_color = "#059669" if coverage >= 50 else ("#d97706" if coverage >= 25 else "#dc2626")
    
    # 变化信息
    changes_html = ""
    if changes:
        changes_items = "".join([f"<li>{c}</li>" for c in changes])
        changes_html = f"""
        <div class="section" style="border-left: 4px solid #7c3aed;">
          <div class="section-title">
            <span class="icon">🔄</span> 较昨日变化
          </div>
          <div class="section-body">
            <ul style="font-size:14px; line-height:2;">{changes_items}</ul>
          </div>
        </div>
        """
    
    # 预警项
    alerts = data.get("alerts", [])
    alerts_html = ""
    if alerts:
        alert_items = ""
        for a in alerts:
            color = a.get("color", "yellow")
            alert_items += f"""
            <div class="alert-item">
              <div class="alert-dot {color}"></div>
              <div>
                <strong>{a.get('title', '')}</strong>
                <p style="font-size:13px; color:var(--text-secondary);">{a.get('desc', '')}</p>
              </div>
            </div>"""
        alerts_html = f"""
        <div class="section">
          <div class="section-title"><span class="icon">⚠️</span> 预警与建议</div>
          <div class="section-body">{alert_items}</div>
        </div>"""
    
    # 主动防护：实时数据获取失败时，顶部显示红色告警横幅
    alert_banner_html = ""
    if data.get("live_failed"):
        reason = data.get("fallback_reason", "实时数据获取失败")
        src = data.get("data_source", "本地缓存/历史快照")
        alert_banner_html = f"""
        <div class="alert-banner">
          <div class="alert-banner-icon">⚠️</div>
          <div class="alert-banner-body">
            <div class="alert-banner-title">实时数据获取失败 · 主动防护告警</div>
            <div class="alert-banner-desc">
              {reason} 当前简报基于 <strong>{src}</strong> 生成，<strong>可能不是最新数据</strong>。
              请检查仓库 Secrets 中的 <code>TDOCS_TOKEN</code> / <code>TDOCS_API_BASE</code> 配置，以及腾讯文档服务状态。
            </div>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>三级库合作伙伴评估体系 - 每日简报</title>
<style>
  :root {{ --bg: #f5f7fa; --card-bg: #ffffff; --text: #1a1a2e; --text-secondary: #6b7280; --border: #e5e7eb; --accent: #2563eb; --success: #059669; --warning: #d97706; --danger: #dc2626; --info: #7c3aed; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px; }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f, #2563eb); color: white; border-radius: 16px; padding: 32px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(37, 99, 235, 0.15); }}
  .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
  .header .subtitle {{ opacity: 0.85; font-size: 16px; }}
  .header .date {{ margin-top: 12px; font-size: 14px; opacity: 0.7; }}
  .header .update-time {{ font-size: 12px; opacity: 0.5; margin-top: 4px; }}
  .overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .stat-card {{ background: var(--card-bg); border-radius: 12px; padding: 20px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  .stat-card .label {{ font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }}
  .stat-card .value {{ font-size: 32px; font-weight: 700; }}
  .section {{ background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px; overflow: hidden; }}
  .section-title {{ font-size: 17px; font-weight: 600; padding: 18px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }}
  .section-body {{ padding: 20px 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ background: #f8fafc; font-weight: 600; color: var(--text-secondary); font-size: 12px; text-transform: uppercase; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }}
  .badge.green {{ background: #ecfdf5; color: #059669; }}
  .badge.red {{ background: #fef2f2; color: #dc2626; }}
  .badge.yellow {{ background: #fffbeb; color: #d97706; }}
  .badge.blue {{ background: #eff6ff; color: #2563eb; }}
  .badge.purple {{ background: #f5f3ff; color: #7c3aed; }}
  .progress-bar {{ height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-top: 6px; }}
  .progress-bar .fill {{ height: 100%; border-radius: 4px; }}
  .alert-item {{ display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }}
  .alert-item:last-child {{ border-bottom: none; }}
  .alert-dot {{ width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }}
  .alert-dot.red {{ background: #dc2626; }}
  .alert-dot.yellow {{ background: #d97706; }}
  .alert-dot.blue {{ background: #2563eb; }}
  .footer {{ text-align: center; padding: 20px; color: var(--text-secondary); font-size: 12px; }}
  .status-tag {{ display: inline-flex; align-items: center; gap: 4px; font-size: 13px; padding: 4px 12px; border-radius: 20px; }}
  .status-tag.live {{ background: #ecfdf5; color: #059669; }}
  .status-tag.cached {{ background: #fef3c7; color: #d97706; }}
  /* 主动防护：实时数据获取失败时的红色告警横幅 */
  .alert-banner {{ display: flex; align-items: flex-start; gap: 14px; background: #fef2f2; border: 1px solid #fecaca; border-left: 6px solid #dc2626; border-radius: 12px; padding: 18px 22px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(220,38,38,0.08); }}
  .alert-banner-icon {{ font-size: 24px; line-height: 1; flex-shrink: 0; }}
  .alert-banner-body {{ flex: 1; }}
  .alert-banner-title {{ font-size: 16px; font-weight: 700; color: #b91c1c; margin-bottom: 4px; }}
  .alert-banner-desc {{ font-size: 13px; color: #7f1d1d; line-height: 1.7; }}
  .alert-banner-desc code {{ background: #fee2e2; padding: 1px 6px; border-radius: 4px; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">

  {alert_banner_html}

  <div class="header">
    <h1>📋 三级库合作伙伴评估体系</h1>
    <div class="subtitle">每日数据简报</div>
    <div class="date">{date_str} {weekday}</div>
    <div class="update-time">
      数据获取时间：{time_str} | 
      <span class="status-tag {'live' if data.get('api_success') else 'cached'}">{'🔗 实时数据' if data.get('api_success') else '📦 快照数据'}</span>
    </div>
  </div>

  <div class="overview">
    <div class="stat-card">
      <div class="label">🤝 合作伙伴总数</div>
      <div class="value" style="color:var(--accent);">{data.get('partner_count', 114)}</div>
    </div>
    <div class="stat-card">
      <div class="label">✅ 已完成入库评估</div>
      <div class="value" style="color:{coverage_color};">{pre_eval['completed']}</div>
      <div class="progress-bar"><div class="fill" style="width:{coverage}%; background:{coverage_color};"></div></div>
      <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">覆盖率 {coverage}%</div>
    </div>
    <div class="stat-card">
      <div class="label">📦 极速通已签项目</div>
      <div class="value" style="color:#7c3aed;">{data.get('express_count', 66)}</div>
    </div>
    <div class="stat-card">
      <div class="label">🔧 售中支撑记录</div>
      <div class="value" style="color:#0891b2;">{mid_sales.get('total', 66)}</div>
    </div>
  </div>

  {changes_html}

  <div class="section">
    <div class="section-title"><span class="icon">📝</span> 入库前能力评估状态</div>
    <div class="section-body">
      <table>
        <tr><th>状态</th><th>数量</th><th>占比</th><th>说明</th></tr>
        <tr>
          <td><span class="badge green">已完成评估</span></td>
          <td><strong>{pre_eval['completed']}</strong></td>
          <td>{coverage}%</td>
          <td>含方案/交付/培训/场景/代理/案例等能力项</td>
        </tr>
        <tr>
          <td><span class="badge blue">部分评估</span></td>
          <td><strong>{pre_eval['partial']}</strong></td>
          <td>{round(pre_eval['partial'] / pre_eval['total'] * 100, 1)}%</td>
          <td>已录入部分能力项</td>
        </tr>
        <tr>
          <td><span class="badge red">待评估</span></td>
          <td><strong>{pre_eval['empty']}</strong></td>
          <td>{round(pre_eval['empty'] / pre_eval['total'] * 100, 1)}%</td>
          <td>仅录入名称，尚未评估</td>
        </tr>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title"><span class="icon">🔧</span> 售中支撑记录 - 评估概览</div>
    <div class="section-body">
      <table>
        <tr><th>评估维度</th><th>正常/优秀</th><th>问题项</th><th>状态</th></tr>
        <tr>
          <td>交付及时性</td>
          <td>按时交付：{mid_sales.get('delivery_on_time', '—')}</td>
          <td>超时交付：{mid_sales.get('delivery_late', '—')}</td>
          <td>{'<span class="badge green">正常</span>' if mid_sales.get('delivery_late', 1) <= 1 else '<span class="badge yellow">需关注</span>'}</td>
        </tr>
        <tr>
          <td>交付质量</td>
          <td>无质量问题：{mid_sales.get('quality_ok', '—')}</td>
          <td>有质量问题：{mid_sales.get('quality_issue', '—')}</td>
          <td>{'<span class="badge green">正常</span>' if mid_sales.get('quality_issue', 1) <= 1 else '<span class="badge yellow">需关注</span>'}</td>
        </tr>
        <tr>
          <td>业主满意度</td>
          <td>正常/非常满意：{mid_sales.get('satisfaction_normal_plus', '—')}</td>
          <td>不满意：{mid_sales.get('satisfaction_bad', '—')}</td>
          <td>{'<span class="badge green">正常</span>' if mid_sales.get('satisfaction_bad', 1) <= 1 else '<span class="badge yellow">需关注</span>'}</td>
        </tr>
        <tr>
          <td>配合程度</td>
          <td>配合/主动配合：{mid_sales.get('cooperation_good', '—')}</td>
          <td>有不配合现象：{mid_sales.get('cooperation_bad', '—')}</td>
          <td>{'<span class="badge green">正常</span>' if mid_sales.get('cooperation_bad', 1) <= 1 else '<span class="badge yellow">需关注</span>'}</td>
        </tr>
      </table>
    </div>
  </div>

  {alerts_html}

  <div class="footer">
    本简报由工蜂 CI 定时流水线自动生成 | 三级库合作伙伴评估体系 | {date_str}<br>
    数据来源：WB-三级库合作伙伴评估体系智能表格 | 每天下午 5:00 自动更新
  </div>

</div>
</body>
</html>"""

# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("三级库合作伙伴评估体系 - 每日简报生成")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 尝试从 API 获取数据
    api_success = False
    global LIVE_ATTEMPTED, LIVE_FAIL_REASON
    LIVE_ATTEMPTED = False
    LIVE_FAIL_REASON = ""

    # 加载最近一次真实快照（沙箱实时抓取生成），用于无 API 时的兜底
    snapshot = load_snapshot()

    print("\n[1/4] 获取入库前能力评估数据...")
    pre_eval_records, pre_src = fetch_records(SHEETS["pre_eval"])
    if pre_eval_records:
        api_success = True
        print(f"  ✓ 获取到 {len(pre_eval_records.get('records', []))} 条记录")

    print("\n[2/4] 获取售中支撑记录数据...")
    mid_sales_records, mid_src = fetch_records(SHEETS["mid_sales"])
    if mid_sales_records:
        print(f"  ✓ 获取到 {len(mid_sales_records.get('records', []))} 条记录")

    print("\n[2.5/4] 获取极速通已签项目数据...")
    express_records, exp_src = fetch_records(SHEETS["express_projects"])
    if express_records:
        print(f"  ✓ 获取到 {len(express_records.get('records', []))} 条记录")

    # 数据分析
    print("\n[3/4] 分析数据...")
    pre_eval = analyze_pre_eval(pre_eval_records.get("records") if pre_eval_records else None, snap=snapshot)
    mid_sales = analyze_mid_sales(mid_sales_records.get("records") if mid_sales_records else None, snap=snapshot)

    # 真实数据来源判定：API 或 live_cache 任一取到即算实时
    # 主动防护：实时成功要求「配置齐全」且「三表均取自实时 API」
    sources = [pre_src, mid_src, exp_src]
    live_ok = LIVE_ATTEMPTED and all(s == "live" for s in sources)
    api_success = live_ok

    # 回退层级与原因（用于告警横幅文案）
    data_source = "本地缓存快照（live_cache）" if "cache" in sources else "历史数据快照（daily_data.json）"
    if not live_ok:
        if not LIVE_ATTEMPTED:
            fallback_reason = "未检测到腾讯文档 API 配置（TDOCS_TOKEN / TDOCS_API_BASE 未设置），已回退至缓存/快照。"
        else:
            fallback_reason = LIVE_FAIL_REASON or "腾讯文档实时 API 调用失败，已回退至缓存/快照。"
        print(f"  [主动防护] 实时数据获取失败：{fallback_reason} 当前简报基于 {data_source}。")
    else:
        fallback_reason = ""
        print("  [主动防护] 实时数据获取成功，未触发告警。")

    print(f"  入库评估: {pre_eval['completed']}/{pre_eval['total']} 完成 ({pre_eval['coverage']}%)")
    print(f"  售中支撑: {mid_sales['total']} 条记录")
    
    # 预警分析
    alerts = [
        {
            "color": "red" if pre_eval["coverage"] < 25 else "yellow",
            "title": f"入库评估覆盖率 {'偏低' if pre_eval['coverage'] < 25 else '需持续关注'}",
            "desc": f"当前 {pre_eval['coverage']}%（{pre_eval['completed']}/{pre_eval['total']}），{'建议加快评估进度' if pre_eval['coverage'] < 25 else '持续推进中'}。"
        }
    ]
    
    if mid_sales.get("delivery_late", 0) > 0:
        late_items = mid_sales.get("alert_items", [])
        alert_desc = "；".join([f"{a.get('partner','')} - {a.get('project') or a.get('issue','')}" for a in late_items[:3]])
        alerts.append({
            "color": "red",
            "title": f"售中超时交付: {mid_sales['delivery_late']} 条",
            "desc": alert_desc
        })
    
    if mid_sales.get("cooperation_bad", 0) > 0:
        alerts.append({
            "color": "yellow",
            "title": f"配合度问题: {mid_sales['cooperation_bad']} 条",
            "desc": "存在不配合现象，需跟进沟通。"
        })
    
    # 当前数据（取真实数据时用真实条数，否则回退最近一次真实快照）
    current_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "api_success": api_success,
        "live_failed": (not live_ok),
        "data_source": data_source,
        "fallback_reason": fallback_reason,
        "partner_count": snapshot.get("partner_count", 114),
        "express_count": len(express_records.get("records", [])) if express_records else snapshot.get("express_count", 66),
        "pre_eval": pre_eval,
        "mid_sales": mid_sales,
        "alerts": alerts,
    }
    
    # 对比变化
    previous = load_snapshot()
    changes = detect_changes(current_data, previous)
    
    # 生成简报
    print("\n[4/4] 生成简报 HTML...")
    html = generate_html(current_data, changes)
    
    with open(BRIEFING_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # 保存快照
    save_snapshot(current_data)
    
    print(f"  ✓ 简报已生成: {BRIEFING_FILE}")
    print(f"  ✓ 数据快照已保存: {DATA_FILE}")
    print(f"\n{'=' * 60}")
    print("简报生成完成!")
    print(f"{'=' * 60}")
    
    return BRIEFING_FILE

if __name__ == "__main__":
    main()
