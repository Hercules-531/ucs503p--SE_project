from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DIAGRAM_DIR = PROJECT_DIR / "docs" / "diagrams"
NAMES = ("use-case", "class", "sequence", "activity", "component")


def test_every_diagram_has_editable_and_rendered_formats() -> None:
    for name in NAMES:
        source = DIAGRAM_DIR / f"{name}.puml"
        svg = DIAGRAM_DIR / "rendered" / f"{name}.svg"
        png = DIAGRAM_DIR / "rendered" / f"{name}.png"
        assert source.read_text(encoding="utf-8").startswith("@startuml")
        assert source.read_text(encoding="utf-8").rstrip().endswith("@enduml")
        svg_text = svg.read_text(encoding="utf-8")
        assert "<svg" in svg_text
        assert "Syntax Error" not in svg_text
        assert "width=" in svg_text and "height=" in svg_text
        assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
