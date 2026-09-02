# vanna-upgrade 全面升级计划（问题驱动）

> **性质**：本仓库的长期改造蓝图，由你按阶段落地；本文只定义问题、目标、思路、验收标准与推荐顺序。  
> **当前基线**：`SqlRunner` + `SqlRunnerPool` + SQLite `SchemaCache` + 工具链 `list_tables` / `describe_table` / `run_sql`；`AgentMemory` 接口已有但实现为内存子串匹配，**未接入检索增强链路**。  
> **第一优先级**：检索增强（RAG / Training Data Retrieval）。

---

## 0. 一句话总览

今天系统几乎每次都在「**从零猜库表 → 看字段 → 拼 SQL → 试错**」。  
升级目标是变成：「**先检索已知知识（相似问题/SQL、相关表 DDL、业务说明）→ 再少量工具补洞 → 产出稳定 SQL**」。

```
现在：  用户问题 → LLM → 多轮工具摸索 → SQL（高轮次、不稳定）
目标：  用户问题 → 检索增强上下文 → LLM → 少工具或直接 SQL → 校验/执行
```

---

## 1. 问题清单（问题驱动，先认清再动手）

### P1 — 工具轮次过高（成本高、慢、易触顶）

| 项 | 说明 |
|----|------|
| **现象** | 一个简单问数/列表，常要 `list_tables` → 多次 `describe_table` → `run_sql`，接近或达到 `max_tool_iterations`（当前默认 10）。 |
| **根因** | Schema 知识只在 SQLite 缓存里，**不会自动进入 prompt**；LLM 必须靠工具「探路」。缓存解决的是「查元数据别打业务库」，没有解决「模型不知道该看哪张表」。 |
| **不改会怎样** | 延迟与 token 成本线性上涨；复杂问题更容易中途失败。 |

### P2 — SQL 不精准、试错多

| 项 | 说明 |
|----|------|
| **现象** | 表名/字段名猜错、JOIN 条件错、过滤条件漏、方言函数用错（达梦 vs MySQL）。 |
| **根因** | 缺少「正确 SQL 范例」与「表用途说明」；仅有字段列表不等于会写业务 SQL。 |
| **不改会怎样** | 结果偶对偶错，用户不信任；错误 SQL 虽只读仍浪费轮次。 |

### P3 — 已知正确 SQL 无法复用（「学过的不会用」）

| 项 | 说明 |
|----|------|
| **现象** | 某人/某次已经验证过的「问题 ↔ SQL」，下次相似问题仍重新摸工具。 |
| **根因** | `AgentMemory.save_tool_usage` / `search_similar_usage` **几乎未参与主链路**；现有实现是内存 + 子串包含，无向量、无持久化、重启即丢。 |
| **不改会怎样** | 系统永远像新人；人工纠错成果无法沉淀。 |

### P4 — 行为不稳定（同一问题多次答案漂移）

| 项 | 说明 |
|----|------|
| **现象** | 相同问题不同轮次选不同表、不同 SQL 写法。 |
| **根因** | 无检索锚定；`temperature` 默认偏高（config 默认 0.7，bootstrap 可读 env）；prompt 过泛（DefaultSystemPromptBuilder 无 Text2SQL 约束）。 |
| **不改会怎样** | 无法做回归测试，无法上生产。 |

### P5 — SchemaCache 能力边界被高估

| 项 | 说明 |
|----|------|
| **现象** | 以为「有了 SQLite 缓存就够用了」。 |
| **事实** | Cache = 元数据本地化；**不是**语义检索。关键字搜索表名/注释仍依赖 LLM 先想到 keyword。 |
| **正确位置** | Cache 保留为「工具回源加速 + 全量同步」；检索层应另建「可 embedding 的知识库」。 |

### P6 — 与 Vanna 能力差距（对齐方向）

| Vanna 经典能力 | 本仓库现状 |
|----------------|------------|
| `add_question_sql` / 相似问题检索 | 接口雏形有，未产品化、未进主流程 |
| `add_ddl` / 相关 DDL 检索 | 仅有 SchemaCache 结构化表，无向量检索 |
| `add_documentation` / 业务文档检索 | 无 |
| 检索结果注入 prompt（enhancer） | `LlmContextEnhancer` 存在但是 **NoOp** |
| 记忆工具（save/search） | Vanna 有 tools；本仓库工具侧未接 |

---

## 2. 目标架构（升级后应长什么样）

```
                    ┌─────────────────────────────┐
                    │   Knowledge Store（可检索）   │
                    │  - question_sql 对           │
                    │  - ddl / 表摘要              │
                    │  - documentation 业务说明    │
                    └──────────────┬──────────────┘
                                   │ top-k 检索
用户问题 ──► Retriever ────────────┤
                                   ▼
                         Context Pack（注入 prompt）
                                   │
                                   ▼
                              LLM（Text2SQL）
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              直接给 SQL     少量工具补洞      拒绝/澄清
                    │         (describe/run)
                    ▼
              validate_sql → run_sql → 结果/纠错回写知识库
```

**分层原则（对齐 Vanna，勿塞进 core）：**

| 层 | 放什么 |
|----|--------|
| `capabilities/` | `SqlRunner`、`AgentMemory`、**新建 `KnowledgeStore` / Retriever 接口** |
| `integrations/` | 向量库实现、embedding、本地 SQLite/Chroma、DamengRunner/MySQLRunner |
| `tools/` | run_sql、list/describe；**新增 save/search 知识工具（可选）** |
| `core/` | Agent 编排、`LlmContextEnhancer` 真正接入检索 |
| `SchemaCache` | 留在 `integrations/local`，继续服务工具；**可被「DDL 入库」消费，但不替代检索** |

---

## 3. 阶段总览（建议你按此顺序做）

| 阶段 | 名称 | 解决的问题 | 优先级 |
|------|------|------------|--------|
| **S0** | 基线度量与问题用例集 | 所有 P* 的可量化 | 立刻 |
| **S1** | 检索增强（RAG）MVP | P1/P2/P3/P4 主干 | **最高** |
| **S2** | 知识写入与人工校正闭环 | P3 沉淀 | 高 |
| **S3** | Schema 智能裁剪（从 Cache → 检索） | P1/P5 | 高 |
| **S4** | SQL 校验与自愈 | P2 | 中 |
| **S5** | Prompt / 策略 / 稳定性 | P4 | 中 |
| **S6** | 观测、评测、回归 | 长期 | 中 |
| **S7** | 体验与产品化（前端/管理） | 可用性 | 低～中 |

---

## 4. S0 — 基线度量（动手前必做，半天～1 天）

### 4.1 问题

没有「坏到什么程度」的数字，后面任何优化都无法证明有效。

### 4.2 思路

固定一组真实业务问题，记录：工具轮次、是否一次 SQL 成功、延迟、最终 SQL。

### 4.3 具体怎么做

1. 建文件例如 `evals/cases.jsonl`，每行至少：
   - `id`, `question`, `expected_sql`（可空）, `expected_tables`, `notes`
2. 跑 10～30 条典型问题（含：简单计数、多表、模糊业务词、已有标准 SQL 的题）。
3. 记录基线表：

| case_id | tool_calls | sql_ok | latency_s | notes |
|---------|------------|--------|-----------|-------|
| ... | | | | |

4. 定义升级成功门槛（示例，可改）：
   - 简单题平均工具轮次 **≤ 2**
   - 有标准 SQL 的相似题 **≥ 80% 零工具或仅 run_sql 一次**
   - 同题 3 次运行 SQL 一致率 **≥ 70%**（温度降低后应更高）

### 4.4 验收

有可重复跑的 case 集 + 一版基线数字。

---

## 5. S1 — 检索增强 MVP（第一优先级，最详细）

### 5.1 要解决的问题

- **P3**：已知问答无法复用  
- **P1**：靠工具摸表导致轮次爆炸  
- **P2**：缺少范例 SQL / 相关 DDL 导致写错  
- **P4**：无锚定时答案漂移  

### 5.2 核心思路（务必统一认知）

检索增强不是「再做一个 SQLite 查表工具」，而是：

1. **离线/半自动**：把三类知识写入可向量检索的库  
2. **在线**：用户问题进来 → embedding → top-k → **拼进 system/user 上下文**  
3. LLM 带着「证据」写 SQL；工具只做验证与补洞  

三类知识（对齐 Vanna training data）：

| 类型 | 内容 | 解决什么 |
|------|------|----------|
| **question_sql** | 自然语言问题 + 正确 SQL（+方言 +库） | 直接复用/仿写 |
| **ddl** | 表级 DDL 或「表名+注释+关键列摘要」 | 缩小表空间，替代盲目 list/describe |
| **documentation** | 业务口径（「活跃用户指…」「工单状态枚举…」） | 减少业务误解 |

### 5.3 推荐落地路径（由简到繁）

#### 路径 A（建议先做）：本地向量库 MVP

- Embedding：可用 DeepSeek/OpenAI embedding，或本地 `sentence-transformers`（看环境）
- 存储：先 **Chroma / FAISS / 甚至 SQLite+向量扩展**；与现有 `SchemaCache` 的 SQLite **分库分文件**，勿混在一张业务元数据表里糊成一团
- 目录建议：
  ```
  capabilities/knowledge_store/     # 抽象接口
  integrations/local/knowledge/     # 本地实现
  data/knowledge/                   # 持久化目录（gitignore）
  ```

#### 路径 B（以后）：对接 Vanna 同款或云向量（Qdrant/Chroma 服务端）

接口稳定后再换实现即可。

### 5.4 接口设计草案（你实现时按此拆）

```text
KnowledgeStore
  add_question_sql(question, sql, *, dialect, metadata) -> id
  add_ddl(ddl_or_table_summary, *, table_name, dialect) -> id
  add_documentation(text, *, metadata) -> id
  search(question, *, kinds=["question_sql","ddl","doc"], top_k=5) -> List[Hit]
  delete(id) / list()
```

`Hit` 至少含：`kind`, `content`, `score`, `metadata`。

### 5.5 如何注入 Agent（关键：否则检索等于没做）

当前已有扩展点：`LlmContextEnhancer.enhance_system_prompt(system_prompt, user_message, user)`。

**具体做法：**

1. 实现 `RetrievalEnhancer(LlmContextEnhancer)`：
   - 对 `user_message` 做 `knowledge_store.search(...)`
   - 把 top-k 格式化成固定模板追加到 system prompt，例如：
     ```
     ## Retrieved question-SQL examples
     Q: ...
     SQL: ...

     ## Retrieved relevant schema
     TABLE users (...关键列...)

     ## Retrieved documentation
     ...
     ```
2. 在 `bootstrap.build_agent()` 里注入该 enhancer，替换 `NoOpLlmContextEnhancer`。
3. **不要**指望模型自己去调「search 工具」才增强——第一期必须是 **自动检索、强制注入**（工具检索可作为第二期补充）。

### 5.6 与 SchemaCache 的关系（避免做错）

| | SchemaCache | KnowledgeStore |
|--|-------------|----------------|
| 用途 | 工具查表结构、启动全量同步 | 语义检索，服务 prompt |
| 查询方式 | SQL / 关键字 | embedding 相似度 |
| 内容 | 全库表字段结构化 | 精选或摘要后的可检索文本 |
| 关系 | 可从 Cache **导出** ddl 摘要批量 `add_ddl` | 不替代 Cache |

建议 S1 最小闭环：

1. 人工录入 20～50 条 `question_sql`（从现网正确 SQL 抄）  
2. 从 SchemaCache 导出「表名+注释+前 N 列」进 `ddl`（可脚本化）  
3. 写 5～10 条业务 documentation  
4. 接上 RetrievalEnhancer  
5. 用 S0 case 复测轮次与准确率  

### 5.7 Prompt 约束（S1 一并改，成本低收益大）

替换/增强 `DefaultSystemPromptBuilder`，明确：

- 你是 Text2SQL 助手；优先使用「Retrieved examples」中的 SQL 改写  
- 表名字段名必须来自检索到的 schema 或工具结果，禁止臆造  
- 仅生成只读 SELECT；不确定时先 clarify 或 describe **一张**相关表  
- 若检索已给出几乎相同问题，直接出 SQL，再 `run_sql` 验证  

同时把 `LLM_TEMPERATURE` 默认降到 **0～0.2**（写 SQL 场景）。

### 5.8 S1 验收标准

- [ ] 对「知识库中已有相似问题」的 case：工具轮次显著下降（目标均值 ≤ 2）  
- [ ] 日志能看到每次请求的 retrieved hits（便于调 top_k / 阈值）  
- [ ] 知识库存盘，进程重启不丢  
- [ ] `DB_DIALECT` 切换时检索可按 dialect 过滤（避免 MySQL 范例污染达梦）  

### 5.9 S1 风险与对策

| 风险 | 对策 |
|------|------|
| 检索到错误范例误导模型 | 人工审核入库；score 阈值；展示来源；允许用户「踩」 |
| embedding 与中文业务词不匹配 | 选中文友好模型；documentation 补同义词 |
| 上下文过长 | top_k 小（3～5）；ddl 用摘要非全表 dump |
| 与工具抢戏 | prompt 写清「有高分范例则先仿写再执行」 |

---

## 6. S2 — 知识写入与校正闭环

### 6.1 问题

只有检索没有写入，知识库会过时；人工改对的 SQL 进不了库。

### 6.2 思路

「成功执行的 SELECT + 用户问题」可自动/半自动入库；错误的可标记。

### 6.3 具体怎么做

1. **半自动（推荐先做）**  
   - 管理命令或脚本：`python -m sql_agent.knowledge add-sql --q "..." --sql "..."`  
   - 或简单 HTTP：`POST /api/knowledge/question_sql`  
2. **自动（谨慎）**  
   - `run_sql` 成功且 `row_count` 合理、无异常时，候选入库，**默认需确认**或仅对白名单用户自动写入  
3. **对齐 Vanna tools（可选）**  
   - `SaveQuestionToolArgsTool` / `SearchSavedCorrectToolUsesTool`  
   - 注意：工具型记忆依赖模型主动调用，**不能替代** S1 的自动 RetrievalEnhancer  
4. 支持删除、按 id 更新、按 dialect 隔离  

### 6.4 验收

人工纠正一条 SQL 后，相似问题下次能被检索到并明显少走弯路。

---

## 7. S3 — Schema 智能进入检索（减轻 list/describe）

### 7.1 问题

全库 describe 轮次高；模型不知道「该问哪个 keyword」。

### 7.2 思路

把 SchemaCache 变成 KnowledgeStore 的 **DDL 语料源**：启动 sync 后（或定时）把每张表渲染成可 embedding 文本。

### 7.3 具体怎么做

1. 定义表摘要模板，例如：  
   `表 ORDER_MAIN（订单主表）。关键列: ID, USER_ID, STATUS, CREATED_AT。注释: ...`  
2. `SchemaCache.ensure_ready()` 成功后触发 `reindex_ddl()`  
3. 检索时 `kinds` 含 `ddl`，top_k 表摘要进 prompt  
4. 调整工具策略：有高分 ddl 命中时，**禁止**无脑 list_tables；最多 `describe_table` 补细节  

### 7.4 验收

新问题在无 question_sql 命中时，仍能靠 ddl 检索把平均工具轮次打下来。

---

## 8. S4 — SQL 校验与自愈

### 8.1 问题

即便有检索，模型仍可能产出非法/不准 SQL。

### 8.2 思路

执行前静态检查 + 失败后带错误信息重试（有限次）。

### 8.3 具体怎么做

1. 扩展现有 `validate_sql`：方言关键字、禁止多语句、可选表名是否在检索集合中  
2. Agent 在 `run_sql` 失败时：把错误 + 相关 ddl 再喂给 LLM，**最多重试 1～2 次**  
3. 不要无限循环；失败则返回可读错误（前端已有 error 展示）  

### 8.4 验收

故意错表名的 case 能自纠或明确失败；不再 silently 乱试 10 轮。

---

## 9. S5 — 稳定性与策略

### 9.1 问题

同问不同答。

### 9.2 具体怎么做

1. 写 SQL 场景 `temperature=0` 或 `0.1`  
2. Prompt 固定输出约定（可先自然语言解释，但最终 SQL 唯一代码块）  
3. 可选：对高分 question_sql（score > 0.92）走 **快捷路径**——跳过工具循环，直接 run 检索到的 SQL（或仅允许微小改写）——用 `WorkflowHandler` 扩展点实现  
4. 会话内缓存「本题已选表」避免来回 list  

### 9.3 验收

S0 中标注「应稳定」的 case，3 次运行 SQL 文本一致或等价。

---

## 10. S6 — 观测与评测

### 10.1 问题

线上「感觉变好了」无法证明。

### 10.2 具体怎么做

1. 每次请求记录：retrieved hits、tool 序列、最终 SQL、成功与否、耗时  
2. 定期跑 `evals/cases.jsonl` 出报告  
3. 对比 S0 基线，作为是否进入下一阶段的门禁  

---

## 11. S7 — 产品化（可后置）

- 前端：展示「参考了哪些历史 SQL / 表」提升可信度  
- 知识库管理页：增删改查 question_sql / ddl / doc  
- 按用户/租户隔离记忆（若多用户）  

---

## 12. 明确「不做什么 / 后做什么」（防范围膨胀）

| 本期不要一上来就做 | 原因 |
|--------------------|------|
| 重写整个 Agent 框架 | 现有扩展点够用 |
| 把向量库塞进 `core/` | 违反 Vanna 分层，难维护 |
| 用 SchemaCache 冒充语义检索 | 解决不了 P3 |
| 完全去掉 list/describe | 检索未命中时仍需要 |
| 一上来上分布式向量集群 | MVP 用本地即可 |

---

## 13. 建议的实施看板（你可直接当 To-do）

### Sprint 1（检索增强 MVP）— 你标的最重要

- [ ] S0：cases + 基线数字  
- [ ] `KnowledgeStore` 接口 + 本地向量实现  
- [ ] `add_question_sql` / `add_ddl` / `add_documentation` + CLI/脚本导入  
- [ ] 录入第一批真实 question_sql（≥20）  
- [ ] 从 SchemaCache 批量导出表摘要为 ddl  
- [ ] `RetrievalEnhancer` 接入 `build_agent`  
- [ ] Text2SQL 专用 system prompt + 低温  
- [ ] 日志打印 retrieval hits  
- [ ] 用 S0 case 对比轮次/准确率  

### Sprint 2

- [ ] 成功 SQL 半自动入库  
- [ ] dialect 过滤  
- [ ] Schema 变更后 ddl 重索引  
- [ ] 失败重试策略（S4 轻量版）  

### Sprint 3

- [ ] 高分范例快捷路径（WorkflowHandler）  
- [ ] 评测报告自动化  
- [ ] 前端展示检索依据（可选）  

---

## 14. 关键文件地图（方便你改时代码定位）

| 关注点 | 当前路径 |
|--------|----------|
| Agent 主循环 / 工具迭代 | `src/sql_agent/core/agent/agent.py` |
| 上下文增强扩展点 | `src/sql_agent/core/enhancer/base.py`（现 NoOp） |
| System prompt | `src/sql_agent/core/system_prompt/default.py` |
| AgentMemory 接口 | `src/sql_agent/capabilities/agent_memory/` |
| 内存假检索 | `src/sql_agent/integrations/local/agent_memory.py` |
| SchemaCache | `src/sql_agent/integrations/local/schema_cache.py` |
| 组装入口 | `src/sql_agent/bootstrap.py` |
| SQL 工具 | `src/sql_agent/tools/run_sql.py` 等 |
| 参考：Vanna 记忆工具 | 旁库 `vanna/src/vanna/tools/agent_memory.py` |
| 参考：Vanna SqlRunner | `vanna/src/vanna/capabilities/sql_runner/` |

**计划新建（建议）：**

| 模块 | 建议路径 |
|------|----------|
| 知识库接口 | `src/sql_agent/capabilities/knowledge_store/` |
| 本地向量实现 | `src/sql_agent/integrations/local/knowledge/` |
| 检索增强器 | `src/sql_agent/integrations/local/retrieval_enhancer.py` |
| 导入脚本 | `scripts/import_knowledge.py` |
| 评测 | `evals/cases.jsonl` + `scripts/run_eval.py` |

---

## 15. 决策记录（你落地前可勾选）

在开始写代码前，建议你先定这几件事（写在本段下方即可）：

1. Embedding 提供方：□ DeepSeek  □ OpenAI  □ 本地模型  □ 其他：_______  
2. 向量存储：□ Chroma  □ FAISS  □ SQLite  □ Qdrant  □ 其他：_______  
3. 第一期知识来源：□ 仅人工 question_sql  □ + Cache 导出 ddl  □ + 业务文档  
4. 自动入库：□ 关闭  □ 半自动确认  □ 全自动（不推荐初期）  
5. 多方言：□ 单库先跑通  □ 必须按 DB_DIALECT 隔离  

---

## 16. 结语

当前最大的结构性缺陷不是「没有 SQLite 缓存」，而是 **「缓存没有变成可检索、可注入的知识，历史正确 SQL 没有进入决策闭环」**。  

因此全面升级的第一斧必须是 **S1 检索增强**：建知识库 → 向量检索 → Enhancer 注入 → 再用工具补洞。SchemaCache、连接池、SqlRunner 继续作为执行与元数据底座，而不是 Text2SQL 的大脑。

按本文阶段推进时，每做完一阶段就更新 S0 评测表；数字变好再开下一阶段，避免「感觉优化」。
