# QuantGodBackend

QuantGod 的后端仓库，负责本地优先的 MT5/HFM 运行证据、研究闭环、AI 分析、治理判断和只读 API。

这个仓库只保留后端职责：

- `MQL5/`：MT5 EA 源码、preset、tester 配置、live/shadow 守护资产。
- `Dashboard/`：本地 Node API server，以及由前端仓库构建后同步进来的 `Dashboard/vue-dist/`。
- `tools/`：Python 研究工具、Governance、ParamLab、AI Analysis、Vibe Coding、Telegram push、MT5 bridge、CI guard。
- `tests/`：Python 单元测试与 Node API contract 测试。
- `archive/`：本地 backtest、ParamLab、research 归档；运行生成数据默认不进入 Git。

前端源码、Cloudflare/infra 自动化和完整文档已经拆到独立仓库：

- Frontend：<https://github.com/Boowenn/QuantGodFrontend>
- Infra：<https://github.com/Boowenn/QuantGodInfra>
- Docs：<https://github.com/Boowenn/QuantGodDocs>

## 本地开发

```powershell
python -m unittest discover tests -v
python -m pytest tests -q --cov=tools --cov-report=term-missing
node --test tests/node/*.mjs
Dashboard\start_dashboard.bat
```

前端 dist 已同步后，本地工作台入口是：

```text
http://localhost:8080/vue/
```

开发前端时，不要在本仓库改 Vue 源码。请在 `QuantGodFrontend` 启动 Vite dev server，并通过 proxy 调用本后端的 `http://127.0.0.1:8080/api/*`。

## 前端 dist 同步

本仓库不再拥有 Vue source。前端构建与同步流程如下：

```powershell
cd ..\QuantGodFrontend
npm install
npm run build
cd ..\QuantGodInfra
python scripts\qg-workspace.py --workspace workspace\quantgod.workspace.json sync-frontend-dist
```

同步后，`QuantGodBackend/Dashboard/vue-dist` 会作为后端 server 的静态页面目录。

## 安全边界

任何自动化都不能绕过 `Kill Switch`、authorization lock、dry-run guard、live preset mutation guard、Telegram push-only 边界或 Vibe Coding research-only 边界。任何 live route 变化仍然必须经过 backtest evidence、ParamLab、Governance、Version Gate 和人工授权。
