# Publishing this repository

1. Create a new public GitHub repository named `zenie-code`.
2. Replace every `mavinstudioart-ux` placeholder:
   - `README.md`
   - `CONTRIBUTING.md`
   - `pyproject.toml`
3. Initialize and push:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial release of Zenie Code"
git remote add origin https://github.com/mavinstudioart-ux/zenie-code.git
git push -u origin main
```

4. In GitHub repository settings:
   - Enable Issues.
   - Enable private vulnerability reporting.
   - Add branch protection for `main`.
   - Require the CI workflow before merging.
5. Create the first release:

```powershell
git tag v1.1.0
git push origin v1.1.0
```
