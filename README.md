# 三级库合作伙伴评估体系 - 每日简报

## 项目说明

每天下午 5:00（北京时间，工作日）自动从「WB-三级库合作伙伴评估体系」智能表格获取最新数据，生成每日简报 HTML 并提交归档。

## 文件结构

```
├── generate_daily_briefing.py   # 简报生成脚本（GitHub Actions 调用；无 API 时回退真实快照）
├── build_real_briefing.py       # 实时简报生成器（沙箱内调用腾讯文档连接器抓取真实数据）
├── partner_daily_briefing.html  # 每日简报（自动更新）
├── daily_data.json              # 数据快照（真实抓取结果，供 GitHub 无 API 时回退 + 变化对比）
├── live_cache/                  # 沙箱实时抓取落盘的原始记录（pre_eval / mid_sales / express）
├── .github/workflows/
│   └── daily-briefing.yml       # GitHub Actions 定时流水线（cron: 0 9 * * 1-5 UTC = 北京 17:00 工作日）
├── archive/                     # 历史简报归档（每日一份）
└── logs/                        # 运行日志
```

## 简报内容

- 📊 数据总览（合作伙伴总数、入库评估完成数/覆盖率、极速通已签项目、售中支撑记录）
- 📝 入库前能力评估状态（已完成 / 部分 / 待评估）
- 🔧 售中支撑记录评估（交付及时性 / 质量 / 业主满意度 / 配合程度）
- ⚠️ 预警与建议（覆盖率偏低、超时交付、配合度问题等）

## 数据来源

- WB-三级库合作伙伴评估体系 智能表格 (ID: `QwBeLNOgcHHF`)

## 运行方式

- **自动**：GitHub Actions 每个工作日下午 5:00（北京时间）触发，生成简报并归档提交。
- **手动**：在仓库 Actions 页面点击 `daily-briefing.yml` → Run workflow。

## ⚠️ 关于「实时数据」的重要说明

GitHub Actions 运行在 GitHub 服务器上，**无法访问腾讯文档 MCP 连接器**。因此 Actions 自动生成的简报会回退使用 `daily_data.json` 中由沙箱实时抓取保存的真实快照（简报标记为「📦 快照数据」）。

要让 Actions 实现**每日自动重新抓取实时数据**，二选一：

1. **配置腾讯文档开放 API**（推荐用于全自动）：在仓库 `Settings → Secrets → Actions` 中添加
   - `TDOCS_API_BASE`：腾讯文档智能表 HTTP API 地址
   - `TDOCS_TOKEN`：访问令牌
   
   脚本已内置对该 API 的调用逻辑（`generate_daily_briefing.py` 的 `fetch_records`）。

2. **沙箱实时生成**（当前可用，需会话内触发）：在 CodeBuddy 沙箱中运行
   ```bash
   python3 build_real_briefing.py
   git add -A && git commit -m "更新实时简报" && git push
   ```
   需先通过腾讯文档连接器把最新记录抓取到 `live_cache/`（由 agent 执行）。

> 简报页眉的「🔗 实时数据 / 📦 快照数据」标识，表示本次数据来源。
