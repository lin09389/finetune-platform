-- 012_drop_legacy_tables.sql
-- PR D: 删除 agent_runtime_legacy / workflow_templates / digital_team 对应的所有数据库表
-- 以及清理 chat_agent_runs / chat_agent_run_messages 中的孤儿列。
--
-- 执行前请先运行备份脚本:
--   cd server && python ../scripts/dump_legacy_tables.py
--
-- DROP 顺序: 子表先于父表，以免外键约束（SQLite 默认关闭 FK，但顺序仍为最佳实践）

-- ── workflow_action_executions (FK → workflow_action_proposals, workflows) ──────
DROP TABLE IF EXISTS workflow_action_executions;

-- ── workflow_tool_calls (FK → workflows, workflow_steps) ─────────────────────────
DROP TABLE IF EXISTS workflow_tool_calls;

-- ── workflow_step_logs (FK → workflows) ──────────────────────────────────────────
DROP TABLE IF EXISTS workflow_step_logs;

-- ── workflow_action_proposals (FK → workflows) ───────────────────────────────────
DROP TABLE IF EXISTS workflow_action_proposals;

-- ── workflow_memory_events (FK → workflows) ──────────────────────────────────────
DROP TABLE IF EXISTS workflow_memory_events;

-- ── workflow_memory_entries (FK → workflows) ─────────────────────────────────────
DROP TABLE IF EXISTS workflow_memory_entries;

-- ── workflow_context_snapshots (FK → workflows) ──────────────────────────────────
DROP TABLE IF EXISTS workflow_context_snapshots;

-- ── workflow_context_profiles (FK → workflows) ───────────────────────────────────
DROP TABLE IF EXISTS workflow_context_profiles;

-- ── workflow_reviews (FK → workflows) ────────────────────────────────────────────
DROP TABLE IF EXISTS workflow_reviews;

-- ── workflow_artifacts (FK → workflows) ──────────────────────────────────────────
DROP TABLE IF EXISTS workflow_artifacts;

-- ── workflow_events (FK → workflows) ─────────────────────────────────────────────
DROP TABLE IF EXISTS workflow_events;

-- ── workflow_steps (FK → workflows) ──────────────────────────────────────────────
DROP TABLE IF EXISTS workflow_steps;

-- ── workflows (FK → workflow_templates) ──────────────────────────────────────────
DROP TABLE IF EXISTS workflows;

-- ── workflow_template_steps (FK → workflow_templates) ────────────────────────────
DROP TABLE IF EXISTS workflow_template_steps;

-- ── workflow_template_agents (FK → workflow_templates) ───────────────────────────
DROP TABLE IF EXISTS workflow_template_agents;

-- ── workflow_templates (root) ─────────────────────────────────────────────────────
DROP TABLE IF EXISTS workflow_templates;

-- ── digital_team 子表 ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS digital_team_reviews;
DROP TABLE IF EXISTS digital_team_artifacts;
DROP TABLE IF EXISTS digital_team_events;
DROP TABLE IF EXISTS digital_team_tasks;
DROP TABLE IF EXISTS digital_team_projects;
DROP TABLE IF EXISTS digital_teams;

-- ── 清理孤儿索引（保留表上引用已删除列的索引） ───────────────────────────────────────
DROP INDEX IF EXISTS idx_chat_agent_runs_workflow;

-- ── 清理孤儿列（需 SQLite 3.35.0+，2021-03-12） ──────────────────────────────────
ALTER TABLE chat_agent_runs DROP COLUMN workflow_id;
ALTER TABLE chat_agent_run_messages DROP COLUMN workflow_event_id;
