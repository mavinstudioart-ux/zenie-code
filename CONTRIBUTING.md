# Contributing

## Development setup

Windows:

```powershell
git clone https://github.com/mavinstudioart-ux/zenie-code.git
cd zenie-code
.\install.ps1 -Dev
```

Linux/macOS:

```bash
git clone https://github.com/mavinstudioart-ux/zenie-code.git
cd zenie-code
./install.sh --dev
```

Run checks:

```powershell
python -m compileall -q src tests
python -m pytest
python -m ruff check src tests
```

## Pull requests

- Keep changes focused.
- Add tests for new behavior.
- Do not commit `.zenie/`, model files, API keys, or generated logs.
- Explain user-facing changes in the pull request.
