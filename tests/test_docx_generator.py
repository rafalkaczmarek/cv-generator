from __future__ import annotations

from pathlib import Path

from cv_generator.services.docx_generator import ensure_default_template, render_cv


def test_default_template_is_created(tmp_path: Path) -> None:
    template = ensure_default_template(template_dir=tmp_path)
    assert template.exists()
    assert template.suffix == ".docx"
    assert template.stat().st_size > 0


def test_render_cv_produces_docx(sample_tailored_cv, tmp_path: Path) -> None:
    template = ensure_default_template(template_dir=tmp_path / "templates")
    output_path = render_cv(
        sample_tailored_cv,
        template_path=template,
        output_dir=tmp_path / "out",
        filename="result.docx",
    )
    assert output_path.exists()
    assert output_path.name == "result.docx"
    assert output_path.stat().st_size > 0


def test_render_cv_uses_default_filename(sample_tailored_cv, tmp_path: Path) -> None:
    template = ensure_default_template(template_dir=tmp_path / "templates")
    output_path = render_cv(
        sample_tailored_cv,
        template_path=template,
        output_dir=tmp_path / "out",
    )
    assert output_path.name.startswith("cv_jan_kowalski_")
    assert output_path.suffix == ".docx"


def test_ensure_default_template_reuses_existing(tmp_path: Path) -> None:
    first = ensure_default_template(template_dir=tmp_path)
    first.write_bytes(b"custom-template")
    second = ensure_default_template(template_dir=tmp_path)
    assert second == first
    assert second.read_bytes() == b"custom-template"
