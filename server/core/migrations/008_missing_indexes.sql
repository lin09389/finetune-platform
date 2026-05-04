-- 008_missing_indexes.sql
-- 为高频查询字段补充缺失索引，减少全表扫描

-- workflows: 按状态筛选
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);

-- workflow_events: SSE 流式推送按 workflow_id 查询
CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow ON workflow_events(workflow_id, created_at);

-- workflow_artifacts: 按 workflow 查找
CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_workflow ON workflow_artifacts(workflow_id);

-- workflow_reviews: 按 workflow 查找
CREATE INDEX IF NOT EXISTS idx_workflow_reviews_workflow ON workflow_reviews(workflow_id);

-- workflow_action_proposals: 前端轮询 pending_approval 状态
CREATE INDEX IF NOT EXISTS idx_workflow_action_proposals_status ON workflow_action_proposals(status);

-- workflow_action_executions: 按 action_id 和 workflow_id 查找
CREATE INDEX IF NOT EXISTS idx_workflow_action_executions_action ON workflow_action_executions(action_id);
CREATE INDEX IF NOT EXISTS idx_workflow_action_executions_workflow ON workflow_action_executions(workflow_id);

-- chat_agent_runs: 按状态筛选
CREATE INDEX IF NOT EXISTS idx_chat_agent_runs_status ON chat_agent_runs(status);

-- workflow_memory_events: 按 workflow_id 查找
CREATE INDEX IF NOT EXISTS idx_workflow_memory_events_workflow ON workflow_memory_events(workflow_id);

-- digital_team_projects: 按状态和 team 查找
CREATE INDEX IF NOT EXISTS idx_digital_team_projects_status ON digital_team_projects(status);
CREATE INDEX IF NOT EXISTS idx_digital_team_projects_team ON digital_team_projects(team_id);

-- digital_team_tasks: 按状态筛选
CREATE INDEX IF NOT EXISTS idx_digital_team_tasks_status ON digital_team_tasks(status);

-- digital_team_reviews: 按 project 和 task 查找
CREATE INDEX IF NOT EXISTS idx_digital_team_reviews_project ON digital_team_reviews(project_id);
CREATE INDEX IF NOT EXISTS idx_digital_team_reviews_task ON digital_team_reviews(task_id);
