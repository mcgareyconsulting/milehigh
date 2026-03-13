---
name: create_worktree
description: Create a new git worktree for a feature branch following trunk-based development.
---

Instructions:
1. Ensure the repository is on main.
2. Pull the latest changes from origin.
3. Create a feature branch named feature/<feature-name>.
4. Create a git worktree in ../worktrees/<feature-name>.
5. **CRITICAL: Use absolute paths when reading/writing files in the worktree.** All file operations (Read, Edit, Write, Glob, Grep, Bash) must target `../worktrees/{{feature_name}}/...` or the absolute path `/Users/danielmcgarey/Desktop/mhmw/worktrees/{{feature_name}}/...`
6. When committing changes, explicitly `cd` to the worktree directory before running `git add` and `git commit`.
7. Never make changes in the main repository directory—all changes belong in the worktree.

Shell commands to execute:

git checkout main
git pull origin main
git worktree add ../worktrees/{{feature_name}} -b feature/{{feature_name}}
echo "Worktree created at: $(pwd)/../worktrees/{{feature_name}}"