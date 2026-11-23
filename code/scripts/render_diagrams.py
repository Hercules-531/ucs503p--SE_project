"""Render the repository's PlantUML sources through the official PlantUML server."""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

import httpx

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "docs" / "diagrams"
OUTPUT_DIR = SOURCE_DIR / "rendered"
DIAGRAMS = ("use-case", "class", "sequence", "activity", "component")
SERVER = "https://www.plantuml.com/plantuml"


def encode_six_bit(value: int) -> str:
    if value < 10:
        return chr(48 + value)
    value -= 10
    if value < 26:
        return chr(65 + value)
    value -= 26
    if value < 26:
        return chr(97 + value)
    value -= 26
    if value == 0:
        return "-"
    if value == 1:
        return "_"
    return "?"


def append_three_bytes(first: int, second: int, third: int) -> str:
    values = (
        first >> 2,
        ((first & 0x03) << 4) | (second >> 4),
        ((second & 0x0F) << 2) | (third >> 6),
        third & 0x3F,
    )
    return "".join(encode_six_bit(value & 0x3F) for value in values)


def plantuml_encode(source: str) -> str:
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    compressed = compressor.compress(source.encode("utf-8")) + compressor.flush()
    encoded: list[str] = []
    index = 0
    while index < len(compressed):
        remaining = len(compressed) - index
        first = compressed[index]
        second = compressed[index + 1] if remaining > 1 else 0
        third = compressed[index + 2] if remaining > 2 else 0
        block = append_three_bytes(first, second, third)
        encoded.append(block if remaining >= 3 else block[: remaining + 1])
        index += 3
    return "".join(encoded)


def validate_output(format_name: str, payload: bytes, name: str) -> None:
    if format_name == "svg":
        text = payload.decode("utf-8", errors="replace")
        if "<svg" not in text or "Syntax Error" in text or "Error line" in text:
            raise ValueError(f"PlantUML reported an error while rendering {name}.puml")
        if "width=" not in text or "height=" not in text:
            raise ValueError(f"Rendered SVG for {name} has no dimensions")
    elif not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Rendered PNG for {name} has an invalid signature")


def render_diagram(client: httpx.Client, name: str) -> None:
    source_path = SOURCE_DIR / f"{name}.puml"
    source = source_path.read_text(encoding="utf-8")
    encoded = plantuml_encode(source)
    for format_name in ("svg", "png"):
        response = client.get(f"{SERVER}/{format_name}/{encoded}")
        response.raise_for_status()
        validate_output(format_name, response.content, name)
        output_path = OUTPUT_DIR / f"{name}.{format_name}"
        output_path.write_bytes(response.content)
        print(f"rendered {output_path.relative_to(PROJECT_DIR)}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            for name in DIAGRAMS:
                render_diagram(client, name)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"diagram rendering failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
