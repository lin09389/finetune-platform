---
name: "github-project-analyzer"
description: "Analyzes GitHub repositories to learn patterns and provide improvement suggestions. Invoke when user wants to learn from GitHub projects or get upgrade recommendations based on open-source examples."
---

# GitHub Project Analyzer

## When To Use

Use this skill when the user provides or references a GitHub repository and wants to:

- Learn from an open-source project.
- Compare the current codebase with another implementation.
- Extract architecture, testing, CI, packaging, or UX patterns.
- Produce practical upgrade recommendations.

## Workflow

1. Identify the repository, branch, and relevant subsystem.
2. Gather only the files needed for the user’s question: README, manifests, key entry points, tests, and target modules.
3. Compare the external project with the current project’s equivalent structure.
4. Separate directly applicable ideas from ideas that do not fit current constraints.
5. Rank recommendations by impact, risk, and effort.

## Output Shape

Provide a concise report with:

- Repository overview and relevant technologies.
- Architecture or implementation patterns worth borrowing.
- Gaps in the current project.
- High-impact recommendations with concrete implementation notes.
- Risks, migration concerns, and tests to add.

## Guardrails

- Prefer official source files and repository documentation over secondary commentary.
- Do not recommend broad rewrites when a small targeted change solves the problem.
- Keep examples tied to exact files or modules when possible.
- Respect licensing and avoid copying large chunks of code.
