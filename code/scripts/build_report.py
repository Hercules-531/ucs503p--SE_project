"""Build the PDF from the report's original LaTeX class and editable source."""

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "BharatOS_Software_Engineering_Report.pdf"
SOURCE_FILES = ("bharatos_report.tex", "tietreport.cls", "references.bib")
FIGURES = ("use-case.png", "class.png", "sequence.png", "activity.png", "component.png")


def build(source_dir: Path, output: Path) -> None:
    tools = {name: shutil.which(name) for name in ("pdflatex", "biber")}
    missing = [name for name, path in tools.items() if path is None]
    if missing:
        raise ValueError(f"Install a TeX distribution with {', '.join(missing)} on PATH")

    with TemporaryDirectory(prefix="bharatos-tex-") as temp:
        staging = Path(temp)
        report = staging / "report"
        report.mkdir()
        for filename in SOURCE_FILES:
            shutil.copy2(source_dir / filename, report)

        figure_dir = Path("docs/diagrams/rendered")
        (staging / figure_dir).mkdir(parents=True)
        for filename in FIGURES:
            shutil.copy2(ROOT / figure_dir / filename, staging / figure_dir)

        latex = [
            tools["pdflatex"],
            "-no-shell-escape",
            "-halt-on-error",
            "-file-line-error",
            "-interaction=nonstopmode",
            "bharatos_report.tex",
        ]
        for command in (latex, [tools["biber"], "bharatos_report"], latex, latex):
            subprocess.run(command, cwd=report, check=True)

        log = (report / "bharatos_report.log").read_text(encoding="utf-8", errors="replace")
        incomplete = r"undefined references|undefined citations|Empty bibliography|Rerun to get"
        if re.search(incomplete, log):
            raise ValueError("LaTeX did not resolve all references and bibliography entries")

        output.parent.mkdir(parents=True, exist_ok=True)
        # Stage beside the final PDF so the replacement is atomic even across drives.
        with TemporaryDirectory(prefix=".report-", dir=output.parent) as publish_dir:
            target = Path(publish_dir) / output.name
            shutil.copyfile(report / "bharatos_report.pdf", target)
            target.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "report")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        build(args.source_dir.resolve(), args.output.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Report build failed: {exc}\n")
    print(f"Compiled {args.output.resolve()}")


if __name__ == "__main__":
    main()
