# Zenie Code

Local-first agentic coding CLI that can diagnose unfamiliar repositories, manage local AI models, generate candidate patches, verify them in sandboxes, and roll back failed changes.

```text
███████╗███████╗███╗   ██╗██╗███████╗
╚══███╔╝██╔════╝████╗  ██║██║██╔════╝
  ███╔╝ █████╗  ██╔██╗ ██║██║█████╗
 ███╔╝  ██╔══╝  ██║╚██╗██║██║██╔══╝
███████╗███████╗██║ ╚████║██║███████╗
╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝╚══════╝
               C  O  D  E
```

## Install from GitHub

Git intentionally does not execute repository code during `git clone`. This prevents a cloned repository from silently installing software. Zenie therefore provides a one-command clone-and-install flow.

### Windows PowerShell

Replace `mavinstudioart-ux` after publishing:

```powershell
git clone https://github.com/mavinstudioart-ux/zenie-code.git; cd zenie-code; .\install.ps1
```

Or:

```powershell
git clone https://github.com/mavinstudioart-ux/zenie-code.git
cd zenie-code
bootstrap.cmd
```

Open a new PowerShell window, enter a project, then run:

```powershell
zenie
```

### Linux/macOS

```bash
git clone https://github.com/mavinstudioart-ux/zenie-code.git \
  && cd zenie-code \
  && ./install.sh
```

Ensure `~/.local/bin` is in `PATH`, then:

```bash
zenie
```

### Optional Tree-sitter support

Windows:

```powershell
.\install.ps1 -WithTreeSitter
```

Linux/macOS:

```bash
./install.sh --with-tree-sitter
```

## First launch

```powershell
zenie
```

Zenie opens a model wizard:

```text
1. Scan for GGUF models
2. Add llama.cpp model manually
3. Connect to Ollama
4. Connect to LM Studio
5. Connect to an OpenAI-compatible endpoint
6. Connect to LiteLLM
7. Exit
```

Model commands:

```powershell
zenie model list
zenie model scan C:\ai\models
zenie model add llama.cpp
zenie model use qwen-coder
zenie model start qwen-coder
zenie model stop qwen-coder
```

## CLI workflow

```text
zenie ❯ /inspect
zenie ❯ /diagnose aplikasi tidak bisa login
zenie ❯ /hypotheses
zenie ❯ /evidence
zenie ❯ /fix
```

A vague request automatically enters diagnosis mode rather than creating an unsupported patch.

## Main capabilities

- Repository profiling and project-type detection
- Baseline checks and automatic failure reproduction
- Evidence storage and ranked debugging hypotheses
- RepoGraph-based file localization
- Context budgeting for smaller local models
- Multi-candidate patch generation
- Isolated sandbox verification
- Test, static check, and model-verifier scoring
- Permission gates and destructive-command blocking
- Automatic rollback
- Local model registry and llama.cpp startup management

## Configuration

Global configuration:

```text
~/.zenie/config.json
```

Model profiles:

```text
~/.zenie/models.json
```

Repository state:

```text
<project>/.zenie/
├── repo_graph.json
├── memory.jsonl
└── sessions/
```

Add `.zenie/` to projects' `.gitignore`.

## Development

```powershell
git clone https://github.com/mavinstudioart-ux/zenie-code.git
cd zenie-code
.\install.ps1 -Dev
```

Run:

```powershell
python -m pytest
python -m ruff check src tests
python -m build
```

## Release

1. Update version in `pyproject.toml` and `src/zenie_code/__init__.py`.
2. Update `CHANGELOG.md`.
3. Commit and push.
4. Create and push a tag:

```bash
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions builds wheel/source archives and attaches them to a GitHub Release.

## License

MIT
