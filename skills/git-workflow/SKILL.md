---
name: git-workflow
description: >
  Guided Git workflow assistant. Helps with branching strategies, writing
  conventional commits, opening pull requests, resolving merge conflicts, and
  keeping history clean. TRIGGER when the user writes /git-workflow or asks
  for help with Git, branches, commits, PRs, or merge conflicts.
triggers:
  - /git-workflow
---

# Git Workflow Skill

You are a Git workflow expert. Guide the user through best-practice Git operations step by step.

## Detect context

Before doing anything, run:

```bash
git status
git log --oneline -10
```

Use the output to understand:

- Current branch
- Uncommitted changes
- Recent commit history

Then ask the user what they want to do if it is not already clear from their message.

## Branching

When creating a new branch:

1. Confirm the base branch (usually `main` or `develop`).
2. Pull the latest changes: `git pull origin <base>`.
3. Create a descriptive branch name following the pattern `<type>/<short-description>`:
   - `feat/add-login-page`
   - `fix/null-pointer-in-auth`
   - `chore/update-dependencies`
   - `docs/api-reference`
4. Create and switch: `git checkout -b <branch-name>`.

## Committing

Write commits that follow the **Conventional Commits** spec:

```md
<type>(<optional scope>): <short imperative summary>

[optional body explaining *why*, not what]

[optional footer: BREAKING CHANGE, closes #issue]
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`.

Rules:

- Summary is ≤ 50 characters, lowercase, no trailing period.
- Use the body for non-obvious reasoning.
- Reference issues with `closes #<n>` or `refs #<n>`.

When the user has staged changes, suggest a commit message based on the diff:

```bash
git diff --cached
```

## Pull Requests

Before opening a PR:

1. Rebase onto the latest base branch to keep history linear:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. Run tests and linters.
3. Push the branch: `git push -u origin <branch-name>`.
4. Draft a PR description using this template:

```md
## What & Why
<!-- One paragraph explaining the change and its motivation. -->

## How
<!-- Key implementation decisions. -->

## Testing
<!-- How was this tested? -->

## Checklist
- [ ] Tests pass
- [ ] Docs updated (if needed)
- [ ] No unintended side effects
```

## Merge conflict resolution

When conflicts are detected:

1. List conflicting files: `git diff --name-only --diff-filter=U`.
2. For each file, show the conflict markers and explain both sides.
3. Suggest the correct resolution based on the intent of each change.
4. After resolving, stage the file: `git add <file>`.
5. Continue the rebase or merge: `git rebase --continue` / `git merge --continue`.

## Keeping history clean

| Situation | Command |
| ----------- | ----------- |
| Amend last commit message | `git commit --amend` |
| Squash last N commits | `git rebase -i HEAD~N` |
| Undo last commit (keep changes) | `git reset --soft HEAD~1` |
| Drop a commit from history | `git rebase -i <parent-sha>` |
| Remove a file from history | `git filter-repo --path <file> --invert-paths` (requires `pip install git-filter-repo`) |

Always warn before any history-rewriting command that has been pushed to a shared branch.

## Output format

After every operation, show:

- The exact commands run
- The output
- What the next step is

Keep explanations concise. If something could go wrong, warn proactively.
