# Data Agent 前端

React 19 + TypeScript + Vite。此次界面重构仅涉及 `frontend/`，沿用现有分析服务和 SSE 事件协议。

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
- 新建分析会保留先前会话，可在侧栏切换。会话和结果只保存在本次打开期间的内存中，刷新页面后清除。
- 元数据管理：SQLite 与 Milvus 分别操作，一次只执行一个同步任务。执行记录保留本次打开期间最近 30 次操作。
- 深浅主题与 Milvus 接口路径保存在当前浏览器；手工输入的同步凭据仅保存在内存中。

## 元数据同步接口

两个入口都同步**单表元数据**，不复制业务行数据，也不会在前端直接连接数据库或 Milvus。

### SQLite 缓存

调用现有 `POST /api/cache/sync`，携带 `X-Requested-With: SQL-Insight-Workbench`。若配置了凭据，同时发送 `X-Cache-Sync-Token`。成功后重新读取 `/health` 刷新缓存数量；健康检查失败不会把已成功的同步改成失败。

### Milvus collection

当前仓库后端仅提供 `main.py sync-schema` 命令，**没有 Milvus HTTP 同步路由**。前端已经提供真实请求按钮与错误反馈，但需要已有或后续提供的 HTTP 接口才能完成同步。此次未更改后端。

默认请求 `POST /api/milvus/sync`；可在「元数据管理 → 接口设置」修改，或通过 `VITE_MILVUS_SYNC_URL` 配置。仅允许本站 `/api/` 下的路径。若配置了凭据，发送 `X-Milvus-Sync-Token`。不发送自定义 JSON 请求体。

支持返回已完成状态（`success`、`ok`、`synced`、`completed`、`ready`、`cached` 或 `success: true`），以及 `table_count` / `total`、`written`、`skipped`、`collection`、`message` 等字段。

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

404/405、无效 JSON、失败状态与无法识别的响应均会明确提示。202 或 `pending` / `queued` / `running` 等只代表任务被接收，页面不会据此标记同步成功；异步任务需要后端提供状态查询契约后再接入。

复制 `.env.example` 为 `.env.local` 可以配置默认路径。`VITE_*` 会进入公开的前端构建产物；不要将私密服务凭据作为构建环境变量发布。
