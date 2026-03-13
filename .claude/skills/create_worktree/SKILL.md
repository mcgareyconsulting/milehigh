---
name: create_worktree
description: Create a new git worktree for a feature branch following trunk-based development.
---

Instructions:
1. Ensure the repository is on main.
2. Pull the latest changes from origin.
3. Create a feature branch named feature/<feature-name>.
4. Create a git worktree in ../worktrees/<feature-name>.
5. Read/write to/from this worktree and branch.

Shell commands to execute:

git checkout main
git pull origin main
git worktree add ../worktrees/{{feature_name}} -b feature/{{feature_name}}