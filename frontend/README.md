# Data Agent 前端

React 19 + TypeScript + Vite。沿用现有分析服务和 SSE 事件协议；SQLite 与 Milvus 的浏览、检查通过后端只读接口提供。

## 本地运行

使用 Node.js 22 或更新版本（系统旧版 Node 不支持当前构建工具）。

```sh
npm install
npm run dev
```

打开 Vite 显示的本地地址，默认 `http://localhost:5173`。开发代理将 `/health` 和 `/api` 转发到 `http://127.0.0.1:8000`。前端不启动后端，也不在页面加载时触发元数据同步。

```sh
npm run build
npm test
```

## 页面与会话

- 分析工作台：提问模板、流式对话、工具执行轨迹、SQL、图表、数据搜索与排序、行详情、CSV 导出。
- 桌面并排显示对话与结果；窄屏通过「分析对话 / 查询结果」切换。
- 会话、运行事件和结果保存在后端 SQLite，刷新后恢复；断线按原 run_id 核对和补读事件，不重新执行 SQL。运行记录可导出 JSON。
- 元数据管理：SQLite 与 Milvus 分别提交持久任务，服务端串行执行并去重；最近 30 条记录刷新后可恢复，显示批次进度和失败原因。
- SQLite 缓存浏览：显示真实表/字段数量、缓存文件和更新时间；按表名、注释或字段搜索，按 Schema 筛选并分页；选择表后查看全部缓存字段、类型、长度、可空性和注释。
- Milvus 文档浏览：展示当前数据源实际存储的单表文档、向量维度、BM25 索引、模型配置、更新时间和内容指纹，按表名或 Schema 搜索并分页。
- 检查 SQLite 文件完整性、缺字段的表、孤立字段和重复字段；检查 Milvus 有效文档与 SQLite 的内容指纹、标识和缺失情况，配置不一致单独提示。
- 深浅主题保存在当前浏览器。

## 元数据同步接口

两个入口都同步**单表元数据**，不复制业务行数据，也不会在前端直接连接数据库或 Milvus。

### SQLite 缓存

前端使用 `POST /api/metadata/jobs`（`target=sqlite`），携带 `X-Requested-With: SQL-Insight-Workbench`，返回 `202` 和任务编号；轮询 `GET /api/metadata/jobs`。兼容入口 `POST /api/cache/sync` 也只提交同一队列，`202` 不能当作同步完成。任务成功后刷新缓存与健康状态。

浏览接口：`GET /api/cache/tables?q=关键词&offset=0&limit=30`（可选 `schema_name`），以及 `GET /api/cache/table?table_name=表名&schema_name=Schema`。列表单页最多 100 张表，前端每页 30 张；详情读取该表全部已缓存字段。浏览只读当前配置的 SQLite，即使未启用业务库连接也可查看已有缓存，不会触发回源查询或向量化。

进入元数据管理页或点击「刷新列表」时读取缓存，SQLite 同步完成后自动刷新。快速搜索/切表会取消旧请求，防止较慢响应覆盖当前选择。无缓存、无匹配、字段未缓存和接口不可用均有对应提示；新增接口需重启后端后生效。

### Milvus collection

前端使用 `POST /api/metadata/jobs`（`target=milvus`）提交单表同步。兼容入口 `POST /api/milvus/sync` 返回 `202` 任务记录。命令行也可使用 `main.py sync-schema`；连接和模型配置由后端管理。

检查与同步分别操作：切换到「Milvus 文档」只读取已有数据，不调用 Embedding，不创建数据库、Collection 或索引，也不会自动加载 Collection。当前关闭 `RAG_ENABLED` 时仍可检查已有文档。进入页面默认查看 SQLite，选择 Milvus 后才发起远程读取。

只读接口：

- `GET /api/cache/check`：SQLite 完整性和元数据记录检查。
- `GET /api/milvus/documents?q=关键词&offset=0&limit=30`：当前数据源与租户内的文档列表及索引配置。
- `GET /api/milvus/document?record_id=文档标识`：真实存储文本、内容指纹及与 SQLite 的状态。
- `GET /api/milvus/check`：有效文档与本地表结构的一致性检查。

数据源、租户和 Collection 固定取后端配置，浏览器不能切换到其他范围。每次检查最多读取 5,000 条标量摘要，不读取向量数组；范围不足会标明未完成，未知数量显示 `—`。无法连接、Collection 缺失、未加载与真正空数据分别提示，读取失败不会被标记为检查通过。两边同步成功后刷新相应浏览区；新增接口需重启后端后生效。

任务完成后，job.report 包含 `table_count` / `total`、`written`、`skipped`、`deactivated`、`collection`、`message` 等字段；例如：

```json
{
  "status": "success",
  "total": 24,
  "written": 20,
  "skipped": 4,
  "collection": "table_schema",
  "message": "单表元数据同步完成"
}
```

404/405、无效 JSON 和失败状态均会提示。前端从持久任务列表判断 success/error/interrupted，并恢复未结束任务。确认记忆另行显示 pending/indexed/failed，并支持失败重试。

`VITE_*` 会进入公开的前端构建产物；不要将私密服务凭据作为构建环境变量发布。

## 结果、图表与导出（2026-10-26）

单个统计值以指标卡片和表格展示；明细和口径不明确的数据默认表格。合适的分类/时间与数值可以推荐柱状图、折线图、面积图，非负且类别较少的单指标可用饼图，两个不同数值字段可用散点图。可手动修改维度、数值、系列和聚合；重复维度未指定聚合时不绘图，不默认求和。图表仅反映已加载数据，截断和系列上限明确提示。

表格支持 CSV 和 JSON，导出范围可选已加载全部、筛选排序后或当前页。CSV 做公式防护和数值文本保护；需要无前缀原始值时导出 JSON。另可导出 SQL、完整分析 JSON、执行记录 JSON，以及带标题和数据范围说明的 PNG/SVG 图表。精确小数和大整数按后端 numeric_encoding 保留，避免前端转换后丢精度。

HTTP 服务按单进程部署，后台 worker 与运行记录共用 `SQL_AGENT_RUNTIME_DB`；重启后未完成运行标为中断，不自动重跑 SQL。取消请求表示等待当前模型/数据库调用安全收尾，并不承诺驱动立即停止。

默认本地单人模式。多人部署可配置服务器端 `SQL_AGENT_AUTH_SECRET`，接收可信身份网关签发的 `sql_agent_session` HttpOnly Cookie；管理接口额外要求 admin。前端不再读取 VITE 管理员 Token。部署和缓存迁移说明见 `docs/REFACTOR_2026_10_26.md`。
