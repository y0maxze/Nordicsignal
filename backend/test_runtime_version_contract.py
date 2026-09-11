from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_render_python_is_pinned_to_ci_minor_line():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    render_match = re.search(r"key:\s*PYTHON_VERSION\s*\n\s*value:\s*[\"']?(\d+\.\d+\.\d+)", render)
    ci_match = re.search(r"python-version:\s*[\"']?(\d+\.\d+)", ci)

    assert render_match, "Render must pin PYTHON_VERSION to a fully qualified version"
    assert ci_match, "CI must declare its Python major/minor"
    assert ".".join(render_match.group(1).split(".")[:2]) == ci_match.group(1)
    assert render_match.group(1) == "3.12.14"
