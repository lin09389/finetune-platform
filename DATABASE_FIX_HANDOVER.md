# 数据库致命 Bug 修复 — 交接文档

**日期**：2026-05-04  
**范围**：`server/` 全栈数据库层（基础设施 → Repository → API）

---

## 一、问题背景

| 问题 | 风险等级 | 症状 |
|------|---------|------|
| DEFERRED 事务模式下多写并发 SQLITE_BUSY 死锁 | 🔴 致命 | 训练/推理并发时数据库锁死 |
| COMMIT 失败后归还污染连接 | 🔴 致命 | 后续请求读到脏数据或崩溃 |
| `executescript()` 隐式 COMMIT 破坏事务原子性 | 🟠 严重 | 迁移脚本中途失败导致半完成状态 |
| 动态拼接字段名无白名单校验 | 🟠 严重 | SQL 注入向量 |
| `INSERT OR REPLACE` 触发 CASCADE 删除子表数据 | 🟠 严重 | 工作流模板更新时 agents/steps 被清空 |
| N+1 查询导致列表页慢 | 🟡 中等 | 项目/模板列表逐行发 SQL |
| async def 路由中同步 SQLite 阻塞事件循环 | 🟡 中等 | 高并发下 API 延迟飙升 |

---

## 二、变更清单

### 2.1 基础设施层 — `server/core/db_manager.py`

| 变更 | 说明 |
|------|------|
| `get_connection()` 使用 `BEGIN IMMEDIATE` | 写事务默认加写锁，消除 DEFERRED→EXCLUSIVE 锁升级死锁 |
| `get_readonly_connection()` | 纯 SELECT 不开事务、不争写锁 |
| 连接归还前健康检查 `_check_connection()` | 避免签出已断开连接 |
| COMMIT/ROLLBACK 失败后 `_destroy_connection()` | 污染连接物理销毁，不再归还池 |
| `safe_execute_script()` | 在独立连接上 autocommit 模式执行 DDL，不干扰池中其他事务 |
| `validate_column_names()` | 正则 `[A-Za-z_][A-Za-z0-9_]*` + 可选白名单校验 |
| `run_sync()` (async) | 基于 `anyio.to_thread.run_sync` 的异步包装，将同步 SQLite 操作移至线程池 |

### 2.2 Repository 层 — SQL 注入防护

| 文件 | 变更 |
|------|------|
| `agent_session/repository.py` | 新增 `_SESSION_UPDATABLE`、`_PART_UPDATABLE` 白名单；`update_session`/`update_part` 改用 `validate_column_names` |
| `agent_runtime/repository.py` | 已有 `_WORKFLOW_UPDATABLE`、`_STEP_UPDATABLE`、`_TOOL_CALL_UPDATABLE`、`_ACTION_UPDATABLE`（前期已加） |
| `digital_team/repository.py` | 已有 `_PROJECT_UPDATABLE`、`_TASK_UPDATABLE`（前期已加） |
| `chat_agent/repository.py` | 已有 `_RUN_UPDATABLE`（前期已加） |

### 2.3 Repository 层 — INSERT OR REPLACE → ON CONFLICT

| 文件 | 表 | 修复 |
|------|---|------|
| `agent_runtime/repository.py` | `workflow_templates` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(id) DO UPDATE SET`（保留 created_at） |
| `agent_runtime/repository.py` | `workflow_context_profiles` | 已有 `ON CONFLICT(workflow_id)` 子句（前期已修） |
| `workspace/project_manager.py` | `projects` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(id) DO UPDATE SET` |
| `workspace/file_manager.py` | `files` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(id) DO UPDATE SET` |
| `workspace/version_control.py` | `file_versions` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(version_id) DO UPDATE SET` |
| `workspace/task_manager.py` | `tasks` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(id) DO UPDATE SET` |
| `workspace/task_manager.py` | `task_notifications` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(id) DO UPDATE SET` |
| `rag/structured/table_store.py` | `table_registry` | `INSERT OR REPLACE` → `INSERT ... ON CONFLICT(table_id) DO UPDATE SET` |

**核心原因**：`INSERT OR REPLACE` 在 SQLite 中先 DELETE 再 INSERT，若表有 `ON DELETE CASCADE` 外键，子表数据会被级联删除。改用 `ON CONFLICT DO UPDATE SET` 只更新指定列，不触发 DELETE。

### 2.4 Repository 层 — N+1 查询消除

| 位置 | 原问题 | 修复 |
|------|--------|------|
| `agent_runtime/repository.py` `list_templates()` | 每个 template 单独查 agents + steps（2N+1 查询） | 批量 `WHERE template_id IN (?)` 一次查出所有 agents/steps，按 template_id 分组 |
| `agent_runtime/repository.py` `get_project()` | 单独调 `get_tasks()`（2 次连接） | 同一 readonly 连接中一次性查出 tasks |
| `agent_runtime/repository.py` `_project_from_row()` | 新增 `preloaded_tasks` 参数避免二次查询 | |
| `digital_team/repository.py` `_project_from_row()` | 同上，新增 `preloaded_tasks` 参数 | |

### 2.5 Repository 层 — 读写连接分类

| 文件 | 原问题 | 修复 |
|------|--------|------|
| `agent_session/repository.py` | `get_session`/`get_part`/`list_parts`/`list_events`/`get_event` 用 `get_connection()` 开写事务 | 改为 `get_readonly_connection()` |
| `agent_runtime/repository.py` | `_template_from_row` 用 `get_connection()` | 改为 `get_readonly_connection()` |
| `agent_runtime/repository.py` | `list_projects`、`get_project`、`get_task`、`get_tasks` 等已有 `get_readonly_connection()` | 保持 |

### 2.6 API 层 — 异步安全 (`run_sync`)

**新增**：`from core.db_manager import run_sync` — 将同步 DB 调用移至线程池

| 文件 | 修复的调用数 |
|------|-------------|
| `api/workflows.py` | 20+ sync service 调用改用 `await run_sync(service.xxx, ...)` |
| `api/chat/routes.py` | 所有 sync `session_manager` 调用 |
| `api/digital_team.py` | 7 个 sync service 调用 |
| `api/agent_sessions.py` | 10 个 sync service 调用 |

**注意**：已 `await service.xxx()` 的真正异步方法（如 `service.run_workflow()`、`service.approve_action()`）保持不变。

### 2.7 维护性增强

| 变更 | 说明 |
|------|------|
| `_with_schema_retry` 退避逻辑 | 新增 `max_retries=2`、指数退避 `0.1 * 2^attempt` 秒、捕获更广泛的 `no such` 错误 |
| 迁移幂等性确认 | 所有 `.sql` 迁移文件已使用 `CREATE TABLE IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS` |

---

## 三、关键设计决策

### 3.1 为什么用 `BEGIN IMMEDIATE` 而不是 `BEGIN`？

| 模式 | 行为 | 并发写 | 并发读写 |
|------|------|--------|----------|
| DEFERRED (原) | 首次读获取 SHARED 锁，首次写升级 EXCLUSIVE | ⚠️ 升级时可能 SQLITE_BUSY 死锁 | ✅ |
| IMMEDIATE (新) | 立即获取 RESERVED 锁 | ✅ 很快获得锁或 BUSY 重试 | ✅ |
| EXCLUSIVE | 立即独占 | ✅ 无竞争 | ⚠️ 阻塞读 |

选择 IMMEDIATE：写事务即获锁无升级风险，读事务用 `get_readonly_connection()` 不开事务不争锁。

### 3.2 为什么用 `ON CONFLICT DO UPDATE SET` 而不是 `INSERT OR REPLACE`？

```
INSERT OR REPLACE → SQLite: DELETE old row → INSERT new row
                      → ON DELETE CASCADE 触发 → 子表数据全没了

INSERT ... ON CONFLICT(id) DO UPDATE SET col=excluded.col → 只 UPDATE 指定列
                      → 不触发 DELETE → 子表数据安全
```

### 3.3 为什么 `run_sync` 而不是 `asyncio.to_thread`？

`anyio.to_thread.run_sync` 在 FastAPI 中兼容性最好，同时支持 asyncio 和 trio 后端。FastAPI 依赖 `anyio`（通过 `starlette`），无需额外安装。

---

## 四、受影响文件清单

```
server/core/db_manager.py                           # 核心改动
server/agent_runtime/repository.py                  # N+1 + INSERT OR REPLACE + validate
server/agent_session/repository.py                  # validate + readonly 连接
server/chat_agent/repository.py                     # validate (已有)
server/digital_team/repository.py                   # N+1 + validate (已有)
server/api/workflows.py                              # run_sync
server/api/chat/routes.py                            # run_sync
server/api/digital_team.py                           # run_sync
server/api/agent_sessions.py                         # run_sync
server/workspace/project_manager.py                 # INSERT OR REPLACE
server/workspace/file_manager.py                    # INSERT OR REPLACE + 缩进修复
server/workspace/version_control.py                 # INSERT OR REPLACE
server/workspace/task_manager.py                    # INSERT OR REPLACE (2处)
server/rag/structured/table_store.py                # INSERT OR REPLACE
```

---

## 五、验证结果

| 检查项 | 结果 |
|--------|------|
| `python -c "from main import app"` | ✅ 导入成功 |
| `test_workflow_observability_actions` (9 tests) | ✅ 全部通过 |
| `test_chat_agent` (3 tests) | ✅ 全部通过 |
| `test_evaluation_deployment` (6 tests) | ✅ 全部通过 |
| `test_training` (46 tests) | ✅ 全部通过 |
| `test_action_policy::test_allowlisted_command_auto_executes` | ❌ 失败（**已有 Bug**，非本次改动引入） |

---

## 六、已知遗留项

### 6.1 本次已修复的遗留问题

| 变更 | 文件 | 说明 |
|------|------|------|
| 补充 14+ 高频查询缺失索引 | `core/migrations/008_missing_indexes.sql` (新增) | 覆盖 status、workflow_id、action_id 等字段 |
| `db_connector.py` 添加 WAL/FK 等 pragmas | `rag/structured/db_connector.py` | 之前长连接缺少 foreign_keys、WAL、synchronous、busy_timeout |
| `table_store.py` 连接管理重构 | `rag/structured/table_store.py` | 10 处裸 `sqlite3.connect()` → `_get_connection()` + `_db()` context manager，统一设置 pragma + row_factory |
| `table_store.py` 列名/表名 SQL 注入防护 | `rag/structured/table_store.py` | `create_table()`/`insert_rows()`/`query()`/`_get_table_name()` 加入 `_SAFE_IDENTIFIER_RE` 正则校验 |
| `table_store.py` `query()` 输入校验 | `rag/structured/table_store.py` | columns 正则校验，where/order_by 拒绝 `;` 分号注入，limit/offset 强制 int |
| `table_store.py` `execute_sql()` DDL 拦截 | `rag/structured/table_store.py` | 阻止 DROP/ALTER/CREATE 等 DDL 语句执行 |
| `db_connector.py` 表名校验 | `rag/structured/db_connector.py` | `get_table_schema()`/`get_table_sample()` 加入 `_validate_table_name()` |

### 6.2 剩余待修复（低优先级）

| 项目 | 优先级 | 说明 |
|------|--------|------|
| `test_action_policy::test_allowlisted_command_auto_executes` | 中 | 已有 Bug，非本次引入 |
| `db_connector.py` 表名拼入 SQL | 低 | `get_table_schema()`/`get_table_sample()` 虽已校验标识符，仍建议改用 parameterized query |
| 其余 API 路由未加 `run_sync` | 低 | `chat_share.py`、`chat_branch.py`、`compat.py` 等同步调用 |

---

## 七、回滚指引

如需回滚，所有改动均可通过 `git revert` 按文件还原。重点关注：

1. **`db_manager.py`** — 回滚后 `get_connection()` 将恢复为 DEFERRED 模式，`run_sync` 将不可用
2. **Repository INSERT OR REPLACE** — 回滚后需确认子表数据未被级联删除（如有新数据写入）
3. **API `run_sync`** — 回滚后恢复为同步调用，功能正常但事件循环阻塞风险恢复