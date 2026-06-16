from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".swift": "Swift",
}

COMMON_ENTRY_POINTS = [
    "main.py", "app.py", "manage.py", "server.py",
    "src/main.py", "src/app.py",
    "index.js", "server.js", "app.js",
    "src/index.js", "src/main.js", "src/main.ts", "src/main.tsx",
    "src/index.ts", "src/index.tsx",
    "cmd/main.go", "main.go",
    "src/main.rs",
    "public/index.php", "artisan",
]

IMPORTANT_DIR_NAMES = {
    "src", "app", "server", "client", "frontend", "backend", "api",
    "tests", "test", "spec", "config", "configs", "migrations",
    "database", "db", "scripts", "lib", "packages",
}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_toml(path: Path):
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_env_example(root: Path):
    keys = []
    sources = []
    for name in [".env.example", ".env.sample", ".env.template"]:
        path = root / name
        if not path.exists():
            continue
        sources.append(name)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                keys.append(key)
    return sorted(set(keys)), sources


def _package_command(package_manager: str, script: str):
    if package_manager == "npm":
        return f"npm run {script}"
    if package_manager == "pnpm":
        return f"pnpm run {script}"
    if package_manager == "yarn":
        return f"yarn {script}"
    if package_manager == "bun":
        return f"bun run {script}"
    return f"npm run {script}"


def _detect_node(root: Path, profile: dict):
    package_path = root / "package.json"
    if not package_path.exists():
        return

    package = _read_json(package_path)
    scripts = package.get("scripts", {}) or {}
    dependencies = {}
    dependencies.update(package.get("dependencies", {}) or {})
    dependencies.update(package.get("devDependencies", {}) or {})

    if (root / "pnpm-lock.yaml").exists():
        manager = "pnpm"
    elif (root / "yarn.lock").exists():
        manager = "yarn"
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        manager = "bun"
    else:
        manager = "npm"

    frameworks = []
    framework_map = {
        "next": "Next.js",
        "react": "React",
        "vue": "Vue",
        "@angular/core": "Angular",
        "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit",
        "express": "Express",
        "fastify": "Fastify",
        "nestjs": "NestJS",
        "@nestjs/core": "NestJS",
        "vite": "Vite",
        "vitest": "Vitest",
        "jest": "Jest",
    }
    for dependency, label in framework_map.items():
        if dependency in dependencies and label not in frameworks:
            frameworks.append(label)

    commands = profile["commands"]
    for key in ["lint", "test", "build", "typecheck", "check", "start", "dev"]:
        if key in scripts:
            commands[key] = _package_command(manager, key)

    profile["ecosystems"].append("Node.js")
    profile["package_managers"].append(manager)
    profile["frameworks"].extend(frameworks)
    profile["manifests"].append("package.json")
    profile["metadata"]["node_scripts"] = scripts


def _detect_python(root: Path, profile: dict):
    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"

    data = {}
    if pyproject.exists():
        data = _read_toml(pyproject)
        profile["manifests"].append("pyproject.toml")
    if requirements.exists():
        profile["manifests"].append("requirements.txt")
    if setup_py.exists():
        profile["manifests"].append("setup.py")
    if setup_cfg.exists():
        profile["manifests"].append("setup.cfg")

    if not any([pyproject.exists(), requirements.exists(), setup_py.exists(), setup_cfg.exists()]):
        return

    deps_text = ""
    if requirements.exists():
        deps_text += requirements.read_text(encoding="utf-8", errors="replace").lower()
    deps_text += json.dumps(data).lower()

    frameworks = []
    for needle, label in [
        ("django", "Django"),
        ("fastapi", "FastAPI"),
        ("flask", "Flask"),
        ("pytest", "Pytest"),
        ("pydantic", "Pydantic"),
        ("streamlit", "Streamlit"),
    ]:
        if needle in deps_text:
            frameworks.append(label)

    commands = profile["commands"]
    if "test" not in commands and (
        "pytest" in deps_text
        or (root / "pytest.ini").exists()
        or (root / "tests").exists()
    ):
        commands["test"] = "python -m pytest -q"
    commands.setdefault("static", "python -m compileall -q .")

    if (root / "manage.py").exists():
        commands.setdefault("check", "python manage.py check")
        commands.setdefault("start", "python manage.py runserver")
    elif (root / "app.py").exists():
        commands.setdefault("start", "python app.py")
    elif (root / "main.py").exists():
        commands.setdefault("start", "python main.py")

    profile["ecosystems"].append("Python")
    profile["package_managers"].append(
        "Poetry" if "tool" in data and "poetry" in data.get("tool", {})
        else "pip"
    )
    profile["frameworks"].extend(frameworks)


def _detect_other_ecosystems(root: Path, profile: dict):
    commands = profile["commands"]

    if (root / "go.mod").exists():
        profile["ecosystems"].append("Go")
        profile["package_managers"].append("Go modules")
        profile["manifests"].append("go.mod")
        commands.setdefault("test", "go test ./...")
        commands.setdefault("build", "go build ./...")

    if (root / "Cargo.toml").exists():
        profile["ecosystems"].append("Rust")
        profile["package_managers"].append("Cargo")
        profile["manifests"].append("Cargo.toml")
        commands.setdefault("test", "cargo test")
        commands.setdefault("static", "cargo check")
        commands.setdefault("build", "cargo build")

    if (root / "composer.json").exists():
        profile["ecosystems"].append("PHP")
        profile["package_managers"].append("Composer")
        profile["manifests"].append("composer.json")
        composer = _read_json(root / "composer.json")
        scripts = composer.get("scripts", {}) or {}
        if "test" in scripts:
            commands.setdefault("test", "composer test")

    if (root / "pom.xml").exists():
        profile["ecosystems"].append("Java")
        profile["package_managers"].append("Maven")
        profile["manifests"].append("pom.xml")
        commands.setdefault("test", "mvn test")
        commands.setdefault("build", "mvn package -DskipTests")

    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        profile["ecosystems"].append("Java/Kotlin")
        profile["package_managers"].append("Gradle")
        manifest = "build.gradle.kts" if (root / "build.gradle.kts").exists() else "build.gradle"
        profile["manifests"].append(manifest)
        gradle = ".\\gradlew.bat" if (root / "gradlew.bat").exists() else "gradle"
        commands.setdefault("test", f"{gradle} test")
        commands.setdefault("build", f"{gradle} build -x test")


def _detect_ci(root: Path):
    paths = []
    github = root / ".github" / "workflows"
    if github.exists():
        paths.extend(
            path.relative_to(root).as_posix()
            for path in github.glob("*.y*ml")
        )
    for candidate in [
        ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
        ".circleci/config.yml",
    ]:
        if (root / candidate).exists():
            paths.append(candidate)
    return sorted(paths)


def profile_repository(root: Path, files: list[str]):
    language_counts = Counter()
    for rel in files:
        language = LANGUAGE_BY_SUFFIX.get(Path(rel).suffix.lower())
        if language:
            language_counts[language] += 1

    profile = {
        "root": str(root),
        "project_name": root.name,
        "languages": [
            {"name": name, "files": count}
            for name, count in language_counts.most_common()
        ],
        "ecosystems": [],
        "frameworks": [],
        "package_managers": [],
        "manifests": [],
        "entry_points": [],
        "important_directories": [],
        "ci_files": [],
        "environment": {
            "required_keys": [],
            "example_files": [],
        },
        "commands": {},
        "metadata": {},
    }

    _detect_node(root, profile)
    _detect_python(root, profile)
    _detect_other_ecosystems(root, profile)

    for candidate in COMMON_ENTRY_POINTS:
        if (root / candidate).exists():
            profile["entry_points"].append(candidate)

    profile["important_directories"] = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name in IMPORTANT_DIR_NAMES
    )
    profile["ci_files"] = _detect_ci(root)

    env_keys, env_sources = _parse_env_example(root)
    profile["environment"]["required_keys"] = env_keys
    profile["environment"]["example_files"] = env_sources

    profile["ecosystems"] = sorted(set(profile["ecosystems"]))
    profile["frameworks"] = sorted(set(profile["frameworks"]))
    profile["package_managers"] = sorted(set(profile["package_managers"]))
    profile["manifests"] = sorted(set(profile["manifests"]))
    profile["entry_points"] = sorted(set(profile["entry_points"]))

    if profile["frameworks"]:
        profile["project_type"] = " + ".join(profile["frameworks"][:4])
    elif profile["ecosystems"]:
        profile["project_type"] = " + ".join(profile["ecosystems"])
    elif profile["languages"]:
        profile["project_type"] = profile["languages"][0]["name"] + " project"
    else:
        profile["project_type"] = "Unknown project"

    return profile


def format_profile(profile: dict):
    commands = profile.get("commands", {})
    lines = [
        f"Project: {profile.get('project_name')}",
        f"Type: {profile.get('project_type')}",
        "Languages: " + (
            ", ".join(
                f"{item['name']} ({item['files']})"
                for item in profile.get("languages", [])
            ) or "(unknown)"
        ),
        "Frameworks: " + (", ".join(profile.get("frameworks", [])) or "(none detected)"),
        "Package managers: " + (
            ", ".join(profile.get("package_managers", [])) or "(none detected)"
        ),
        "Manifests: " + (", ".join(profile.get("manifests", [])) or "(none)"),
        "Entry points: " + (", ".join(profile.get("entry_points", [])) or "(none detected)"),
        "Important directories: " + (
            ", ".join(profile.get("important_directories", [])) or "(none detected)"
        ),
        "Environment keys: " + (
            ", ".join(profile.get("environment", {}).get("required_keys", []))
            or "(none declared)"
        ),
        "Detected commands:",
    ]
    if commands:
        lines.extend(f"  {name}: {command}" for name, command in commands.items())
    else:
        lines.append("  (none)")
    return "\n".join(lines)
