---
name: cleanup_worktree
description: Clean up a git worktree after a feature branch has been merged.
---

Instructions:
1. Ensure you are in the root directory of the git repository.
2. Remove the git worktree located at ../worktrees/<feature-name>.
3. Delete the feature branch named feature/<feature-name>.

Shell commands to execute:
git worktree remove ../worktrees/{{feature_name}}
git branch -d feature/{{feature_name}}
