# 修复计划 (Finetune Platform 2.0)

## 1. 摘要 (Summary)
针对之前深度检测中发现的各方面问题，本计划旨在系统性地修复前端 TypeScript/ESLint 错误，使用 Ruff 自动修复后端的代码格式与规范问题，并修复因近期代码重构导致的测试套件引用错误，以全面恢复项目的构建和测试健康度。

## 2. 当前状态分析 (Current State Analysis)
- **前端**：存在 1 个 TS 属性访问类型错误，以及几处阻碍构建的 ESLint `error` 级别错误（`no-constant-condition`、`prefer-const`）。
- **后端 (规范)**：存在超过 20,000 个 `ruff` 检查出的警告和规范问题（主要是 `W293` 多余空格，以及 `UP045/UP006` 老旧类型注解），这些问题大多可以通过工具安全地自动修复。
- **后端 (测试)**：由于部分模块（如 `agent.security` -> `agent.security_old`，`gateway.session` 移除等）被重构或移动，导致 8 个测试文件在 `pytest` 收集阶段就报 `ImportError` 失败。

## 3. 建议的修改 (Proposed Changes)

### 3.1 前端问题修复
- **目标文件**：`client/src/hooks/chat/useAgentExecutor.ts`
  - **修改内容**：将 `task.params.message` 修改为 `task.params['message']`，解决索引签名属性访问的 TypeScript 错误。
- **目标文件**：`client/src/components/ChatHistoryDrawer.tsx`
  - **修改内容**：将 `errorMsg` 变量从 `let` 修改为 `const`，修复 `prefer-const` 错误。
- **目标文件**：`client/src/services/StreamManager.ts`、`client/src/services/api.ts`、`client/src/components/ChatBranchManager.tsx`
  - **修改内容**：对引起 `no-constant-condition` 报错的 `while (true)` 等必要逻辑添加 `// eslint-disable-next-line no-constant-condition` 忽略注释，或者调整为合法的逻辑。

### 3.2 后端代码规范一键修复
- **执行命令**：在 `server` 目录下运行 `ruff check . --fix`。
- **预期结果**：自动清理所有多余空格、更新 `Optional[X]` 为 `X | None`，更新 `List[X]` 为 `list[X]` 等 Python 3.10+ 标准写法。

### 3.3 后端测试套件 `ImportError` 修复
需要修复由于路径变动导致的 `tests/` 目录中的导入错误：
1. **`test_agent.py`, `test_agent_module.py`, `test_complex_integration.py`**:
   - 将 `from agent.security import SecurityValidator` 更新为 `from agent.security_old import SecurityValidator`。
2. **`test_agent_executor.py`**:
   - 更新 `OperationHandler`、`OperationResult` 等相关类的导入路径。通过修改 `from agent.core.interfaces import ...` 到具体定义的子模块中（如 `agent.core.interfaces.base_executor` 等），确保测试能正确找到引用。
3. **`test_gateway.py`**:
   - 将 `AgentConfig` 的导入从 `gateway.agent_isolation` 更改为其正确路径 `agent.config`。
4. **`test_gateway_comprehensive.py`**:
   - 移除文件顶部的无效导入 `from gateway.session import SessionManager`（局部函数内部已经做了正确的导入或模拟）。
5. **`test_gateway_integration.py`**:
   - 将 `from server.main import app` 更改为 `from main import app`（由于 pytest 在 `server` 根目录下运行）。
6. **`test_heartbeat_comprehensive.py`**:
   - 移除 `TestTaskPriority` 测试类及其相关导入，因为 `TaskPriority` 已经被移出 `heartbeat` 模块。

## 4. 假设与决策 (Assumptions & Decisions)
- 假设 `SecurityValidator` 位于 `agent.security_old` 模块内并且其接口暂未变动。
- 假设针对 `while(true)` 的 ESLint 报错是因为有意设计的事件循环/轮询机制，因此使用注释屏蔽该错误是最合理的做法。
- 假设 `TaskPriority` 移除后不再属于 `heartbeat` 的测试范畴，直接在当前测试中清理掉是安全的。
- 决策：采用 `ruff` 的 `--fix` 自动修复，而非手动调整，以确保效率和准确性。

## 5. 验证步骤 (Verification steps)
1. 在 `client` 目录执行 `npm run typecheck` 和 `npm run lint`，确保以 `0` 状态码退出，无 Errors。
2. 在 `server` 目录执行 `ruff check .`，确认绝大多数或所有的自动修复项已清理干净。
3. 在 `server` 目录执行 `pytest`，确保收集阶段的 8 个 `ImportError` 完全消除，并且所有的测试套件可以正常开始执行。