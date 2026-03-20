---
name: "github-project-analyzer"
description: "Analyzes GitHub repositories to learn patterns and provide improvement suggestions. Invoke when user wants to learn from GitHub projects or get upgrade recommendations based on open-source examples."
---

# GitHub Project Analyzer

This skill enables AI to analyze GitHub repositories, learn from their source code, and provide actionable improvement suggestions for the current project.

## When to Invoke

Invoke this skill when:
- User wants to learn from a specific GitHub project
- User asks for improvement suggestions based on open-source examples
- User wants to upgrade current project by referencing mature projects
- User provides a GitHub URL and asks for analysis
- User wants to compare current codebase with industry best practices

## Workflow

### Step 1: Repository Information Gathering

1. **Parse GitHub URL** - Extract owner, repo name, and optional branch/path
2. **Fetch Repository Metadata** using GitHub API:
   - Repository description, stars, language, topics
   - Directory structure and file tree
   - README content
   - Recent commits and contributors

3. **Identify Key Files** to analyze:
   - Configuration files (package.json, pyproject.toml, Cargo.toml, etc.)
   - Main entry points (main.py, index.ts, App.tsx, etc.)
   - Core modules and components
   - Architecture patterns (folder structure, naming conventions)

### Step 2: Deep Code Analysis

Analyze the following aspects:

**Architecture & Design Patterns**
- Project structure and module organization
- Design patterns used (MVC, MVVM, Clean Architecture, etc.)
- Dependency injection and inversion of control
- Microservices vs monolithic approach

**Code Quality Indicators**
- Code organization and modularity
- Type safety and static analysis usage
- Error handling patterns
- Testing coverage and strategies
- Documentation quality

**Technology Stack**
- Frameworks and libraries used
- Version compatibility management
- Build and deployment configurations
- CI/CD pipelines

**Performance Optimizations**
- Caching strategies
- Lazy loading patterns
- Database query optimization
- Resource management

**Security Practices**
- Authentication/authorization patterns
- Input validation and sanitization
- Secret management
- Security headers and middleware

### Step 3: Current Project Assessment

Compare with current project:

1. **Identify Gaps** - What's missing in current implementation
2. **Find Strengths** - What current project does well
3. **Detect Anti-patterns** - What should be avoided
4. **Version Analysis** - Outdated dependencies, deprecated patterns

### Step 4: Generate Improvement Report

Provide structured recommendations:

```markdown
## 项目分析报告

### 📊 项目概览
- 项目名称: [name]
- 技术栈: [languages/frameworks]
- 成熟度: [stars/contributors/activity]

### 🏗️ 架构亮点
1. [Pattern/Practice 1]
2. [Pattern/Practice 2]
...

### 💡 可借鉴的改进点

#### 高优先级
- [ ] **[Improvement 1]**: [Description] → [How to implement]
- [ ] **[Improvement 2]**: [Description] → [How to implement]

#### 中优先级
- [ ] **[Improvement 3]**: [Description] → [How to implement]

#### 低优先级
- [ ] **[Improvement 4]**: [Description] → [How to implement]

### 📝 具体实现建议

#### 1. [Feature/Pattern Name]
**参考代码位置**: [file path in GitHub repo]
**当前项目位置**: [file path in current project]

**改进前**:
```language
// current code
```

**改进后**:
```language
// suggested code based on reference
```

**理由**: [Why this change improves the project]

### ⚠️ 注意事项
- [Potential risks or breaking changes]
- [Migration steps if needed]

### 📚 参考资源
- [Relevant documentation links]
- [Related issues or discussions]
```

## Tools Available

Use these tools during analysis:

1. **WebFetch** - Fetch GitHub repository pages and raw files
2. **WebSearch** - Search for related documentation and best practices
3. **SearchCodebase** - Search current project for comparison
4. **Read** - Read current project files for comparison
5. **Glob** - Find files matching patterns in current project

## GitHub API Endpoints

Use these endpoints for repository information:

```
# Repository info
https://api.github.com/repos/{owner}/{repo}

# Contents
https://api.github.com/repos/{owner}/{repo}/contents/{path}

# README
https://api.github.com/repos/{owner}/{repo}/readme

# Tree (file structure)
https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1

# Commits
https://api.github.com/repos/{owner}/{repo}/commits
```

For raw file content:
```
https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
```

## Example Usage

**User**: "分析 https://github.com/modelscope/swift 项目，看看我们的训练模块可以怎么改进"

**AI Response Flow**:
1. Fetch swift repository metadata
2. Analyze training-related code structure
3. Compare with current project's training module
4. Generate improvement suggestions with code examples

## Best Practices

1. **Focus on Relevance** - Only analyze parts relevant to user's request
2. **Provide Context** - Explain why each suggestion is valuable
3. **Be Practical** - Consider current project constraints (team size, timeline, resources)
4. **Show Examples** - Include before/after code comparisons
5. **Prioritize** - Rank improvements by impact and effort

## Language Support

- Respond in the same language as the user's request
- Code comments should match the project's primary language
- Technical terms can remain in English when appropriate
