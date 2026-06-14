from context.project_scanner import ProjectScanner


def test_parse_dependencies_reads_pyproject_without_requirements(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
dependencies = [
    "fastapi==0.109.0",
    "pypdf>=4,<5",
    "requests[socks]>=2.32; python_version >= '3.11'",
]

[project.optional-dependencies]
gpu = ["bitsandbytes==0.41.3"]
dev = ["pytest==7.4.3"]
""".strip(),
        encoding="utf-8",
    )

    scanner = ProjectScanner(str(tmp_path))
    dependencies = scanner._parse_dependencies()

    assert dependencies["python"] == ["fastapi", "pypdf", "requests"]
    assert dependencies["python_optional"] == {
        "gpu": ["bitsandbytes"],
        "dev": ["pytest"],
    }


def test_parse_dependencies_merges_requirements_and_pyproject(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "fastapi==0.109.0\nhttpx==0.28.1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
dependencies = ["fastapi==0.109.0", "pypdf>=4,<5"]
""".strip(),
        encoding="utf-8",
    )

    scanner = ProjectScanner(str(tmp_path))
    dependencies = scanner._parse_dependencies()

    assert dependencies["python"] == ["fastapi", "httpx", "pypdf"]
