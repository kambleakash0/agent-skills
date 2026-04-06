# Security Policy

## Supported versions

| Version | Supported |
| :--- | :--- |
| Latest release | Yes |
| Older releases | Best effort |

## Reporting a vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public issue.** Instead, email **kambleakash0@gmail.com** with:

- A description of the vulnerability.
- Steps to reproduce it.
- The affected skill or MCP server.
- Any potential impact you've identified.

You should receive an acknowledgment within 72 hours. I'll work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

This policy covers:

- The MCP servers (`ast-editor`, `notebook-editor`) and their dependencies.
- The agent skills (prompt injection risks, unintended tool invocations, etc.).
- The installation and configuration instructions (supply chain concerns).

## Security considerations for MCP servers

- **ast-editor** reads and writes files on disk using absolute paths provided by the calling agent. It does not sandbox file access — the agent's permission model is the boundary.
- **notebook-editor** can execute arbitrary Python code in Jupyter kernels via `execute_cell` / `execute_all_cells`. Users should treat kernel execution with the same caution as running code in a terminal.

## Disclosure timeline

Once a vulnerability is confirmed, I aim to release a fix within 7 days for critical issues and 30 days for lower-severity issues. A security advisory will be published on GitHub after the fix is available.
