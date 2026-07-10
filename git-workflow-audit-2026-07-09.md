# Git 工作流审计报告

**审计仓库：** `lin09389/finetune-platform`  
**审计日期：** 2026-07-09  
**审计范围：** 分支策略、提交规范、合并/PR 流程、代码审查、CI/CD 集成

---

## 1. 执行摘要

当前仓库整体处于“**半规范状态**”：

- 近期提交（约最近 30 个）基本已切换到约定式提交（Conventional Commits）。
- CI/CD 已覆盖前后端测试、lint、构建、安全扫描，骨架完整。
- 但存在**高风险操作**：本地 `master` 直接超前远端 10 个 commit，且未经过 PR；这些 commit 改动量极大（196 文件、8,905+/3,159-），同时工作区仍有未提交变更。
- 提交规范历史执行不一致，约 **68%** 符合约定式提交；剩余 32% 为自由格式大写标题，影响 CHANGELOG 和语义化版本自动化。
- 缺少本地钩子（husky/commitlint）、CODEOWNERS、PR 模板，审查流程依赖人工自觉。
- 长期分支 `codex/backup-frontend-rewrite-20260628` 已 11 天未更新，处于悬停状态。

**总体建议：** 立即把当前本地 `master` 的变更迁移为 feature branch + PR，启用分支保护，补齐 commitlint/PR 模板/CODEOWNERS，并拆分后续提交以保持原子性。

---

## 2. 分支策略分析

### 2.1 当前分支快照

| 分支 | 最近提交日期 | 状态 | 说明 |
|------|-------------|------|------|
| `master`（本地） | 2026-07-09 | 领先 `origin/master` 10 个 commit | 直接提交到主干，未走 PR |
| `origin/master` | 2026-07-07 | 远端默认分支 | 与本地分叉于 `479a6ac` |
| `codex/backup-frontend-rewrite-20260628` | 2026-06-28 | 本地未合并分支 | 仅含 1 个 `wip:` 提交，已闲置 11 天 |

### 2.2 问题与风险

| # | 问题 | 风险等级 | 影响评估 |
|---|------|----------|----------|
| 1 | **主干分支直接提交**：本地 `master` 已经领先远端 10 个 commit，且未通过 PR/MR | 🔴 高 | 绕过代码审查，破坏 CI/CD 门禁意义；若误 `push`，将直接触发部署流程；回滚和审计困难 |
| 2 | **分支命名不统一**：既有 `codex/*` 前缀，也有 `master` 主干；无统一语义前缀（如 `feat/`、`fix/`） | 🟡 中 | 难以从分支名判断类型和负责人；仓库规模扩大后难以管理 |
| 3 | **长期未合并分支**：`codex/backup-frontend-rewrite-20260628` 未更新、未合并 | 🟡 中 | 可能包含已过时或冲突代码；占用命名空间，增加认知负担 |
| 4 | **默认分支名为 `master` 而非 `main`** | 🟢 低 | 已配置 CI 兼容 `master`/`main`/`develop`，但建议随主流迁移到 `main` |

### 2.3 建议

1. **立即冻结本地 `master` 直接提交**，将当前 10 个 commit 迁出到 feature branch：
   ```bash
   # 安全做法：基于当前 master 创建 feature branch
   git checkout -b feat/phase0-4-consolidation master
   git push -u origin feat/phase0-4-consolidation

   # 将本地 master 重置到 origin/master（先确保工作区已保存）
   git checkout master
   git fetch origin
   git reset --keep origin/master
   ```
2. **制定分支命名规范**：
   - `feat/<short-desc>` 新功能
   - `fix/<short-desc>` 修复
   - `chore/<short-desc>` 杂项/依赖
   - `docs/<short-desc>` 文档
   - `archive/<desc>-YYYYMMDD` 明确标识备份/归档分支
3. **处理悬停分支**：
   - 若 `codex/backup-frontend-rewrite-20260628` 已无用，直接删除：
     ```bash
     git branch -D codex/backup-frontend-rewrite-20260628
     git push origin --delete codex/backup-frontend-rewrite-20260628
     ```
   - 若需要保留，改名为 `archive/frontend-rewrite-20260628` 并打 tag 归档。
4. **逐步迁移默认分支到 `main`**，并在 GitHub 中设置默认分支。

---

## 3. 提交规范分析

### 3.1 统计（基于 `master` 全历史）

| 指标 | 数值 |
|------|------|
| 总提交数 | 257 |
| Merge 提交 | 4 |
| 符合约定式提交 | 175（68.1%） |
| 不符合约定式提交 | 82（31.9%） |

### 3.2 不符合约定式提交的典型示例

```
f657002 Trim Storybook development dependencies
af1994f Harden backend test environment
1432787 Bound workspace resource usage
733faae Implement governed model release lifecycle
09c5b59 Complete agent workbench usability workflows
5575822 Add loop-guard diagnostics and recovery handling
```

### 3.3 问题与风险

| # | 问题 | 风险等级 | 影响评估 |
|---|------|----------|----------|
| 1 | **约 32% 提交未使用 Conventional Commits** | 🟡 中 | 无法可靠地通过 `conventional-changelog` 生成 CHANGELOG；自动化语义化版本（major/minor/patch）失效 |
| 2 | **Merge Commit 标题不符合规范**（如 `Merge pull request #6...`） | 🟡 中 | 在自动生成 CHANGELOG 时会被忽略或造成噪音 |
| 3 | **部分提交粒度过粗** | 🔴 高 | 例如 `feat(frontend): core runtime + Phase-3 visual + Phase-4 fetch consolidation + capability tiers` 包含多个独立主题；回滚、cherry-pick、bisect 困难 |
| 4 | **存在 `wip:` 提交** | 🟡 中 | 出现在 `codex/backup-frontend-rewrite-20260628` 分支；WIP 不应进入主干历史 |

### 3.4 建议

1. **安装 commitlint + husky**，在本地强制约定式提交：
   ```bash
   # 在项目根目录（client 已有 npm，可直接复用）
   npm install --save-dev @commitlint/{config-conventional,cli} husky lint-staged
   npx husky init
   echo 'npx --no -- commitlint --edit ${1}' > .husky/commit-msg
   ```
   并增加 `commitlint.config.js`：
   ```js
   module.exports = { extends: ['@commitlint/config-conventional'] };
   ```
2. **PR 合并时优先使用 Squash Merge**，并确保 PR 标题符合 Conventional Commits，这样即使分支内提交不规范，合并到主干时也是干净的。
3. **拆分原子提交**：每个 commit 只做一件事，可独立回滚。例如将“前端运行时 + Phase-3 + Phase-4”拆成三个 `feat` 提交。
4. **清理历史**：在合并前使用 `git rebase -i origin/master` 整理分支内的提交，删除或合并 `wip`/`fixup` 提交，并将非规范消息改写为规范格式。强制推送到个人分支时使用：
   ```bash
   git push --force-with-lease
   ```

---

## 4. 合并 / PR 流程分析

### 4.1 当前情况

- 历史中存在 3 条真实的 PR 合并记录（#2、#5、#6），说明曾经使用 PR 流程。
- 但最近 10 个 commit 全部直接提交到本地 `master`，没有 PR 记录。
- 仓库未配置 `.github/CODEOWNERS` 和 PR 模板（仅在 `deepagents_reference` 子目录下有模板，不属于本仓库）。
- 无法从本地判断 GitHub 分支保护是否启用（建议登录 GitHub 仓库设置确认）。

### 4.2 问题与风险

| # | 问题 | 风险等级 | 影响评估 |
|---|------|----------|----------|
| 1 | **最近重大变更未走 PR** | 🔴 高 | 缺少审查、缺少讨论、可能引入安全/稳定性问题；违反项目 AGENTS.md 中“阶段 0 安全”要求 |
| 2 | **无 CODEOWNERS** | 🟡 中 | 无法自动指定关键目录（如 `server/security/`、`server/apps/`）的审查人 |
| 3 | **无 PR 模板** | 🟡 中 | 提交者容易遗漏测试、影响面、回滚计划等关键信息 |
| 4 | **无 PR 标题/描述规范** | 🟡 中 | 合并后的 commit 消息质量不可控 |

### 4.3 建议

1. **在 GitHub 中启用分支保护**（Settings → Branches → `master`/`main`）：
   - 勾选 **Require a pull request before merging**
   - 勾选 **Require status checks to pass**（选择 CI 中 `lint`、`backend-test`、`frontend` 等必要 job）
   - 勾选 **Require code review approval**（建议至少 1 人）
   - 勾选 **Restrict pushes that create files larger than 100MB** 等安全选项
2. **新增 `.github/CODEOWNERS`**，例如：
   ```text
   * @lin09389
   server/security/ @lin09389
   server/apps/ @lin09389
   client/src/agent/ @lin09389
   .github/workflows/ @lin09389
   ```
3. **新增 `.github/PULL_REQUEST_TEMPLATE.md`**，包含变更摘要、测试方式、影响范围、回滚方案等。
4. **禁止直接推送共享分支**。本地开发时：
   ```bash
   git fetch origin
   git checkout -b feat/my-feature origin/master
   # 完成后推送到个人分支并开 PR
   git push -u origin feat/my-feature
   ```

---

## 5. CI/CD 集成分析

### 5.1 工作流文件

- `.github/workflows/ci.yml`：push/PR 到 `main`/`master`/`develop` 时触发。
- `.github/workflows/cd.yml`：push 到 `main`/`master` 或 `v*` tag 时触发部署。

### 5.2 当前 CI 流程（ci.yml）

| Job | 是否必填 | 备注 |
|-----|----------|------|
| `lint` | 是 | 含编码检查、Ruff focused、Ruff full、Black、MyPy |
| `backend-test` | 是 | 单元测试 + smoke 测试 |
| `backend-integration` | 是 | 集成测试 |
| `frontend` | 是 | TypeScript、Lint（允许失败）、Vitest、Build |
| `security` | 否（`continue-on-error: true`） | 使用 `safety` 扫描 |

### 5.3 问题与风险

| # | 问题 | 风险等级 | 影响评估 |
|---|------|----------|----------|
| 1 | **多个关键质量门设置为 `continue-on-error: true`**：Ruff full、Black、MyPy、前端 lint、security | 🔴 高 | 这些检查失败不会阻塞合并，长期会积累代码债务和安全隐患 |
| 2 | **CD 部署步骤为占位符** | 🟡 中 | `deploy-staging`/`deploy-production` 仅 `echo`，未真正部署；可能误导团队认为已上线 |
| 3 | **security job 使用 `pip install safety` 且多个 `|| true` 回退** | 🟡 中 | 安装非项目依赖，且失败时静默通过；应纳入 `pyproject.toml` 并使用 `uv run` |
| 4 | **CD 在 `master` push 时直接触发 staging 部署** | 🟡 中 | 与问题 1 叠加，未经审查的代码可能触发 CD |
| 5 | **缺少 commit message lint 工作流** | 🟢 低 | 无法阻止非规范提交进入主干 |

### 5.4 建议

1. **将阻塞性检查改为必填**：
   - Ruff focused、Black、MyPy、前端 lint 应至少设置为“warning/failure”可切换；建议先设目标为修复后关闭 `continue-on-error`。
2. **Security 纳入项目依赖**：
   ```toml
   [dependency-groups]
   dev = ["safety", ...]
   ```
   或改用 `uv run pip install safety` 并去掉 `|| true` 回退。
3. **CD 部署占位符需补齐**：
   - 如果当前为占位，请在 workflow 中明确标注 `TODO` 或关闭自动触发，避免误判。
   - 正式接入部署目标（如服务器、K8s、Docker Compose）后再启用 `deploy-staging`/`deploy-production`。
4. **增加 PR 级别的 commit-lint 检查**：
   ```yaml
   - name: Lint commit messages
     run: npx commitlint --from=origin/master --to=HEAD
   ```
5. **设置 GitHub Environment 保护规则**：staging/production 需要人工审批和 secrets 保护。

---

## 6. 冲突与长期分支风险

- 当前只有 1 个本地悬停分支，未观察到大量远程未合并分支或频繁冲突。
- 但最近一次未推送的 10 个 commit 改动面极广（196 文件），未来一旦其他成员并行开发，冲突概率极高。
- 建议将大变更拆小、尽早合并，降低长期分支的“大合并”风险。

---

## 7. 立即行动清单（按优先级排序）

| 优先级 | 行动 | 负责人 | 预期收益 |
|--------|------|--------|----------|
| P0 | 将本地 `master` 的 10 个 commit 迁出为 `feat/phase0-4-consolidation`，并开 PR 回 `origin/master` | 当前开发者 | 恢复代码审查、阻止未经审查的 CD |
| P0 | 保存或清理当前工作区 8 个修改文件 + 4 个未跟踪文件 | 当前开发者 | 避免丢失本地变更，保持 master 干净 |
| P0 | 在 GitHub 启用 `master`/`main` 分支保护，要求 PR + 审查 + status check | 仓库管理员 | 防止再次直接推送 |
| P1 | 安装 `commitlint` + `husky`，强制约定式提交 | 当前开发者 | 提升历史可读性，支持自动 CHANGELOG |
| P1 | 新增 `CODEOWNERS` 和 `PULL_REQUEST_TEMPLATE.md` | 仓库管理员 | 规范审查流程，明确责任人 |
| P1 | 将 CI 中的 `continue-on-error` 逐步改为必填（先从 Black/MyPy 开始） | 团队 | 防止代码债务恶化 |
| P1 | 处理 `codex/backup-frontend-rewrite-20260628` 分支（删除或归档） | 当前开发者 | 减少认知负担 |
| P2 | 迁移默认分支到 `main`；同步更新 CI、本地脚本和文档 | 团队 | 与现代 Git 实践对齐 |
| P2 | 引入语义化版本标签（`v0.x.x`）和 release-please/changelog 生成 | 团队 | 自动化版本发布和 CHANGELOG |

---

## 8. 附录：关键数据快照

```textnCurrent branch: master (ahead of origin/master by 10 commits)
Uncommitted: 8 files changed, 301 insertions(+), 17 deletions(-)
Untracked: 4 files
Total commits on master: 257
Conventional commit ratio: 68.1%
Merge commits: 4
Local branches: 2 (master, codex/backup-frontend-rewrite-20260628)
Remote branches: 1 (origin/master)
Tags: 1 (backup/deps-uv-migration-phase1)
Unpushed commit diff: 196 files changed, 8905 insertions(+), 3159 deletions(-)
```

---

*本报告基于仓库本地状态生成，未涉及远程 GitHub 设置（如分支保护、审批规则）。建议结合 GitHub 仓库设置页面逐项确认并配置。*
