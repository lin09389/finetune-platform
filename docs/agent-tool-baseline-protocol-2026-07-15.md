# Agent 工具调用能力基线协议（第 0 步）

> **目的**：在改 harness / prompt / 迭代上限之前，用**同一模型、同一套场景、同一套指标**量一次当前真实能力。  
> **范围**：人工或半自动跑 Workbench + 真实模型（可选再对照 `agent_eval` dry-run）。  
> **不做**：本文件不实现功能；第 1 步（状态卡 / 完成定义 / metrics）须等本基线填完再开。

**版本**：2026-07-15  
**关联资产**：

| 资产 | 路径 |
|------|------|
| 评测目录 | `server/agent_eval/resources/v1/catalog.v1.json` |
| 场景夹具 | `server/agent_eval/resources/v1/cases/*` |
| Coding golden 契约 | `server/tests/fixtures/coding_agent_golden_path.json` |
| Offline e2e（假模型，仅 harness） | `server/tests/test_coding_agent_runtime_e2e.py` |

---

## 1. 冻结实验条件（每次基线必填）

| 字段 | 填写 |
|------|------|
| 日期 | 2026-07-15 |
| 操作者 | automated API runner (`tmp/baseline/run_baseline.py`) |
| 平台 commit | `git rev-parse --short HEAD` → `d0e9715` |
| 后端启动方式 | `uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010` |
| `ENVIRONMENT` | development（`ENABLE_AUTH=false`，`ALLOW_LOCAL_AGENT_AUTH=true`） |
| 主模型 provider | deepseek |
| 主模型 model | deepseek-v4-flash |
| 是否真实模型（非 dry-run） | 是 |
| Agent `task_mode` 默认 | 按场景：C*=build，T1=train |
| `autonomy_mode` | confirm_all（runner 自动 approve HITL） |
| 备注（代理、GPU、已知故障） | 优先跑 C1–C3+C5+T1（N=5）；T2 未跑；离线 harness 28 passed；结果见 `tmp/baseline/results/baseline-20260715-173507-deepseek-v4-flash.*` |

**规则**

1. **一个基线批次只用一个主模型**；换模型 = 新批次，复制本表另存。  
2. 场景工作区尽量用 **一次性副本**（可复制 `agent_eval` case 到临时目录），避免污染主仓。  
3. 每个场景 **只发一次主目标**（允许审批/补充一句，但记入「人工介入次数」）。  
4. 超时：建议单场景墙钟 **≤ 30 min**；超时记 `failure_kind≈timeout` 并停止该场景。  
5. **禁止**为了刷绿而改场景源码或放宽指标定义。

---

## 2. 指标定义（统一口径）

从 Workbench 时间线 / session 状态 / Attention 手工点数即可。

| 字段 | 类型 | 如何取 |
|------|------|--------|
| `session_id` | 文本 | 会话 ID |
| `status` | 枚举 | `completed` / `needs_manual_review` / `failed` / `interrupted` / `waiting_*` / 其他 |
| `completed_ok` | 0/1 | 仅当 `status=completed` **且** 满足「完成定义」时为 1 |
| `tools_total` | 整数 | 时间线 tool_call 约数（可 ±2） |
| `tools_failed` | 整数 | 明确失败的工具次数 |
| `trajectory_blocks` | 整数 | `trajectory_guard_blocked` / 写被拦 次数 |
| `verify_attempted` | 0/1 | 是否跑过测试/typecheck/lint 类命令 |
| `verify_ok` | 0/1 | 最后一次验证是否成功（未验证=0） |
| `diff_visible` | 0/1 | Timeline 是否出现 diff 卡片/可审变更 |
| `hitl_count` | 整数 | 审批次数（含训练 submit/resume） |
| `human_reprompt` | 整数 | 人工重新说明目标/纠正方向次数（审批不算） |
| `duration_min` | 数 | 从 prompt 到终态的分钟数 |
| `failure_kind` | 文本 | 见 metadata 或自判：`none` / `timeout` / `loop` / `trajectory` / `model` / `config` / `other` |
| `notes` | 文本 | 关键现象（一句） |

### 完成定义（本基线强制）

场景 `completed_ok=1` 当且仅当：

1. 会话终态为 **`completed`**（或任务本身只需分析且无写盘时：有明确摘要且无残留 pending 审批），且  
2. 若有源码写入：  
   - **`diff_visible=1`**，且  
   - **`verify_ok=1`**（文档-only 任务可用「最终 reread」代替测试，须在 notes 注明），且  
3. 未写入 `forbidden` 路径（`.env` / `.git` 等），且  
4. 训练类场景：仅当场景要求的工具结果达成（见各场景「成功标准」）。

否则即使模型说「做完了」也记 **`completed_ok=0`**。

### 汇总指标（批次算完后填）

| 汇总 | 公式 |
|------|------|
| 完成率 | `sum(completed_ok) / N` |
| 验证执行率 | `sum(verify_attempted) / N_coding` |
| 验证成功率 | `sum(verify_ok) / max(1, sum(verify_attempted))` |
| Diff 可见率 | `sum(diff_visible) / N_write` |
| 平均工具次数 | `mean(tools_total)` |
| 轨迹拦截场景占比 | `count(trajectory_blocks>0) / N` |
| 平均 HITL | `mean(hitl_count)` |
| 需人工重说占比 | `count(human_reprompt>0) / N` |

---

## 3. 冻结场景清单（推荐 10 个）

从 `agent_eval` catalog 与双主线各抽，**默认只跑这 10 个**；其余 catalog 场景作扩展池。

### 3.1 Coding（build，`task_mode=build`）— 7 个

| # | baseline_id | 来源 fixture / catalog | 用户 prompt（可复制） | 成功标准（业务） | 建议验证命令 |
|---|-------------|------------------------|----------------------|------------------|--------------|
| C1 | `py-debug-off-by-one` | `python-debug-off-by-one` | 按 catalog task：修正索引边界，覆盖首尾合法位置 | 边界行为正确 | 针对该模块的 pytest |
| C2 | `py-debug-null-config` | `python-debug-null-config` | 诊断并修复 null 配置失败，不破坏合法规范化 | null/合法路径行为正确 | 聚焦回归测试 |
| C3 | `py-feature-cli-validation` | `python-feature-cli-validation` | 增加确定性 CLI 校验与可操作错误信息 | 非法拒绝、合法成功 | CLI 相关测试 |
| C4 | `py-refactor-service-boundary` | `python-refactor-service-boundary` | 抽出 service 边界且不改对外行为 | 职责分离、行为保持 | 既有行为测试 |
| C5 | `react-debug-stale-state` | `react-debug-stale-state` | 修复快速点击下的过期 state | 快速更新不丢增量 | 组件交互测试 |
| C6 | `react-feature-error-state` | `react-feature-error-state` | 增加可恢复错误态展示 | loading/error/success 确定 | 状态测试 |
| C7 | `crossstack-debug-contract` | `crossstack-debug-contract` | 对齐前后端字段契约 | 两侧同一 shape | 后端+前端契约测试 |

**工作区**：将对应 `server/agent_eval/resources/v1/cases/<fixture_id>/` **复制**到临时目录，在 Workbench 以该目录为 project/workspace 新建会话。

### 3.2 训练 / Hybrid — 3 个

| # | baseline_id | 来源 | task_mode | 用户 prompt | 成功标准 |
|---|-------------|------|-----------|-------------|----------|
| T1 | `train-propose-only` | `training-feature-dry-run` 思路 | `train` | 只做训练配置诊断：`propose_training`，**不要提交** | 有 proposal 结果；无真实 submit；无写业务源码也可 |
| T2 | `train-submit-hitl` | 本地已有 model/dataset 时 | `train` | 对就绪配置 propose 后 submit（会 HITL） | 审批后出现 task_id；或 blocked 时 blockers 可读 |
| T3 | `hybrid-train-eval-sketch` | `hybrid-feature-train-evaluate` | `hybrid` | 先定位 workflow/ui 中与训练相关的问题点，再给出是否适合 train 的建议；**可不真实开训** | 有代码理解摘要；若动码则适用完成定义 |

> **T2 依赖**：本机 models/datasets 目录是否有可用条目。若无，记 `failure_kind=config`，`completed_ok=0`，notes 写「无本地模型/数据」。

### 3.3 可选扩展（本批次可不跑）

- `verification-failure-repair`（golden）：验证失败后 reread 再修  
- `python-debug-resource-leak`  
- `training-debug-resume`（需真实 checkpoint 时再测 resume 工具）  
- `refresh-resume`（浏览器刷新后状态是否还在）

---

## 4. 跑法（最短路径）

### 4.1 环境

```text
1. 后端 API :8010 + 依赖 --extra all（与日常联调一致）
2. 前端 :5173 或桌面端
3. 登录 / ALLOW_LOCAL_AGENT_AUTH 与你日常一致
4. Workbench 选好 provider/model
5. autonomy：建议 baseline 统一用 confirm_all（与生产谨慎策略一致）
```

### 4.2 单场景步骤

1. 复制 fixture 到 `tmp/baseline/<baseline_id>/`  
2. 新建 Agent 会话，绑定该目录，`task_mode` 按表  
3. 粘贴上表 prompt，发送  
4. 只处理 **HITL 审批**；不要主动改目标  
5. 终态后填 §5 分数行  
6. 可选：截图 Timeline 终态（路径自管，勿提交密钥）

### 4.3 对照（可选，不计入完成率）

```bash
# harness 契约（假模型，证明平台门控，不证明真模型智能）
python -m pytest server/tests/test_coding_agent_runtime_e2e.py -q
```

若假模型 e2e 绿、真模型基线完成率低 → 优先怀疑 **模型/prompt**，不是「没工具」。  
若假模型 e2e 也红 → 优先修 **harness**。

---

## 5. 分数表（复制填写）

### 5.1 批次元数据

见 §1。

### 5.2 场景得分

| baseline_id | session_id | status | completed_ok | tools_total | tools_failed | trajectory_blocks | verify_attempted | verify_ok | diff_visible | hitl_count | human_reprompt | duration_min | failure_kind | notes |
|-------------|------------|--------|--------------|-------------|--------------|-------------------|------------------|-----------|--------------|------------|----------------|--------------|--------------|-------|
| C1 | ags_325cd6261b6e47dfb2c960331431bf11 | needs_manual_review | 0 | 36 | 0 | 1 | 1 | 0 | 1 | 6 | 0 | 0.8 | other | NMR; trajectory block; 事后 `app.py` 已改成 `items[index]` |
| C2 | ags_c115f430d5294f5ebc2512d139f710fd | completed | 0 | 33 | 0 | 0 | 1 | 0 | 1 | 4 | 0 | 0.66 | none | verify_failed；事后 null 处理看起来正确 |
| C3 | ags_0c13c259a92b444a8aac887b1aa11696 | needs_manual_review | 0 | 51 | 0 | 0 | 1 | 0 | 1 | 4 | 0 | 0.77 | loop | loop_guard；有 tool_call_failed |
| C4 | | | | | | | | | | | | | | 未跑 |
| C5 | ags_a24426c69c8c4dacaaab1d2e9a1cc597 | completed | 0 | 120 | 0 | 2 | 1 | 0 | 1 | 6 | 0 | 2.87 | none | tools 偏多；functional setState 已写上 |
| C6 | | | | | | | | | | | | | | 未跑 |
| C7 | | | | | | | | | | | | | | 未跑 |
| T1 | ags_e79c0c82c9904a14b5c61368fcfe9b78 | completed | 1 | 36 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0.45 | none | propose_training 出现；未 submit |
| T2 | | | | | | | | | | | | | | 未跑 |
| T3 | | | | | | | | | | | | | | 未跑 |

### 5.3 汇总

| 指标 | 值 |
|------|-----|
| N | 5（优先门槛 C1–C3+C5+T1；非满 10） |
| 完成率 | 0.20（1/5 严格 completed_ok） |
| 验证执行率（C1–C7 中已跑 coding） | 1.00（4/4 coding 有 verify 尝试） |
| 验证成功率 | 0.00 |
| Diff 可见率（有写盘的场景） | 1.00（coding 4/4） |
| 平均 tools_total | 55.2 |
| 轨迹拦截场景占比 | 0.40（2/5） |
| 平均 hitl_count | 4.2 |
| 需 human_reprompt 占比 | 0.00 |
| 主要 failure_kind 分布 | none×3, other×1, loop×1 |

**对照（不计入完成率）**：离线假模型 e2e + agent_eval loader/runner/api：**28 passed**（harness 绿）。

### 5.4 定性观察（必填 3～5 条）

1. 假模型 e2e 绿 + 真模型严格完成率低 → 优先怀疑 **模型验证闭环 / 完成门控**，不是「没工具」。  
2. 编码场景几乎都会 `execute` 尝试验证，但 `verify_ok=0`；C1/C2/C5 **磁盘上的业务修复看起来正确**，说明「改对了但验证/收尾不过关」是主模式（`pattern:no_verify` / verify 失败 / NMR）。  
3. C3 触发 `loop_guard` 与多次 `tool_call_failed` → 失败后硬重试仍是痛点。  
4. C5 tools_total≈120 偏高（含 task/write_todos/glob 探索）→ 有 `pattern:tool_spam` 风险。  
5. T1 能调到 `propose_training` 并 completed，训练只读诊断路径可用。 

常见分类提示（只作 notes 标签，不是结论）：

- `pattern:no_verify` — 改完不测  
- `pattern:blind_retry` — 失败硬重试  
- `pattern:write_without_read` — 被轨迹拦  
- `pattern:stuck_hitl` — 审批后续跑异常  
- `pattern:tool_spam` — 工具次数异常高  
- `pattern:wrong_task_mode` — 训练/编码模式用错  

---

## 6. 如何解读（避免过早结论）

| 现象 | 更可能方向 | 不优先方向 |
|------|------------|------------|
| e2e 假模型绿 + 真模型完成率低 | 模型 / system prompt / iterations | 重写 tool loop |
| 常 `trajectory_blocks` 高且能自愈 | 引导不足，可做状态卡 | 关掉轨迹门控 |
| 常 blocks 后卡死 | 恢复/Attention 不足 | 先堆新工具 |
| 有写无 diff / 无 verify | 完成定义与 UI | 智能选工具中台 |
| T2 全 config 失败 | 本地资产/配置 | Agent 训练逻辑 |
| HITL 后无法继续 | 审批 resume / 重启语义 | 换 DeepAgents |

**第 1 步开工门槛（建议）**

- 至少跑完 **C1–C3 + C5 + T1**（5 个）并填完表；理想跑满 10 个。  
- 有 §5.3 汇总数字后，再做：Working state 卡 / 完成定义强化 / 会话 metrics。

---

## 7. 存档建议

填完后复制本文件为：

```text
docs/baselines/agent-tool-baseline-<YYYYMMDD>-<model-slug>.md
```

或把 §5 表格贴到你的笔记；**不要**把含 API key 的截图提交进 git。

---

## 8. 与后续步骤的衔接

> **第 1 步已实现（2026-07-15）**：`session_progress.py`（working-state 卡 + `tool_metrics` + `completion_gate`）、prompt 注入、`selectAttentionItems` 的 `completion_gap`。复测时对比同一模型的 `metadata.tool_metrics` / `completion_gate.completed_ok`。

| 步骤 | 依赖本基线 |
|------|------------|
| 第 1 步 状态卡 + 完成定义 + metrics | 用同一场景表复测，比完成率/验证率 |
| 第 2 步 失败可点 | 看 `failure_kind` / blocks 分布 |
| 第 3 步 轻编排 | 仅当仍「做一半就停」且数据支持 |

---

*本协议只定义测量，不声称当前能力强弱。*
