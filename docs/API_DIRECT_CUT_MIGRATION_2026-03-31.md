# AI 对话系统接口迁移说明（Direct Cut）

生效日期：2026-03-31
适用范围：`server` 后端 API（意图检测/执行/Gateway/Chat）

## 1. 统一契约字段
以下接口统一返回核心字段（单意图场景）：
- `detected`
- `intent_type`
- `action`
- `params`
- `confidence`
- `need_confirm`
- `execution`

多意图接口返回：
- `detected`
- `intents`（每项同单意图核心字段结构）
- `has_ambiguity`
- `clarification_dialog`
- `chain`

## 2. 新接口主线
- `POST /agent/detect-intent`
- `POST /agent/detect-intent-multi`
- `POST /agent/execute`
- `POST /agent/chat-execute`
- `POST /smart-agent/smart-execute`
- `POST /smart-agent/smart-chat`
- `GET /smart-agent/supported-operations`

Gateway 主线：
- `GET /gateway/status`
- `POST /gateway/devices/register`
- `POST /gateway/devices/authenticate`
- `GET /gateway/devices`
- `GET /gateway/devices/{device_id}`
- `DELETE /gateway/devices/{device_id}`
- `POST /gateway/devices/{device_id}/permissions`
- `POST /gateway/messages/send`
- `POST /gateway/messages/send-and-wait`
- `POST /gateway/messages/broadcast`
- `POST /gateway/bindings`
- `GET /gateway/bindings`
- `DELETE /gateway/bindings/{rule_id}`
- `POST /gateway/agents/spawn`
- `GET /gateway/agents/spawned`
- `DELETE /gateway/agents/spawned/{spawned_id}`
- `POST /gateway/agents/results/collect`
- `WS /gateway/ws`

Chat 主线：
- 仅保留 `api.chat.routes` 作为 `/chat` 路由实现
- `api/chat.py` 作为 shim 转发 `router`，不再承载第二套语义

## 3. 废弃与替换映射
1. 旧：多套意图返回结构（不同模块字段不一致）
- 新：统一 `IntentResult/MultiIntentResult` 映射到 API 契约字段

2. 旧：`agent/executor.py` 与 `agent/core/engine/executor.py` 并行语义
- 新：`agent.core.executor.UnifiedExecutor` 作为统一入口

3. 旧：`/setup/*` 在集成测试中作为 Gateway 依赖
- 新：从 Gateway 集成测试基线移除，按独立 setup 模块维护

4. 旧：`/chat` 占位与正式路由并存
- 新：统一到 `api.chat.routes` 单路由语义

## 4. 兼容策略
本次为“直接切新”，不保留旧行为分支。
调用方需在同版本内完成切换。

## 5. 状态机与会话元数据
`/agent/chat-execute` 会按阶段写入会话元数据 `execution_timeline`：
- `detected`
- `planned`
- `generated`（内容生成分支）
- `persisted`（执行结果持久化）

## 6. 已验证测试基线
- `server/tests/test_gateway.py`
- `server/tests/test_gateway_integration.py`
- `server/tests/test_agent_executor.py`
- `server/tests/test_agent_api_contract.py`
