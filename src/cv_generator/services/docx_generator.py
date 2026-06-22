"""Generate the final CV DOCX file from a TailoredCV.

Two responsibilities:
* Create a default `cv_template.docx` with Jinja2 placeholders the first time
  it's needed. Users can replace it with a custom Word template later.
* Render that template with docxtpl against a TailoredCV and save to /output.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from docxtpl import DocxTemplate

from cv_generator.config import get_settings
from cv_generator.models import TailoredCV

_TEMPLATE_NAME = "cv_template.docx"


def ensure_default_template(template_dir: Path | None = None) -> Path:
    """Create the default Word template if it doesn't exist. Return its path."""
    settings = get_settings()
    template_dir = template_dir or settings.app_templates_dir
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / _TEMPLATE_NAME
    if template_path.exists():
        return template_path

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Header — name + headline
    name = doc.add_paragraph()
    name_run = name.add_run("{{ cv.full_name }}")
    name_run.bold = True
    name_run.font.size = Pt(22)
    name_run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    headline = doc.add_paragraph("{{ cv.headline }}")
    headline.runs[0].italic = True
    headline.runs[0].font.size = Pt(12)

    # Contact line
    contact = doc.add_paragraph(
        "{{ cv.email }}{% if cv.phone %} | {{ cv.phone }}{% endif %}"
        "{% if cv.location %} | {{ cv.location }}{% endif %}"
        "{% if cv.linkedin_url %} | {{ cv.linkedin_url }}{% endif %}"
        "{% if cv.github_url %} | {{ cv.github_url }}{% endif %}"
    )
    contact.runs[0].font.size = Pt(10)

    _add_section_title(doc, "Profil")
    doc.add_paragraph("{{ cv.summary }}")

    _add_section_title(doc, "Doświadczenie")
    doc.add_paragraph("{%p for exp in cv.experiences %}")
    p = doc.add_paragraph()
    r = p.add_run("{{ exp.title }} — {{ exp.company }}")
    r.bold = True
    meta = doc.add_paragraph(
        "{{ exp.date_range }}{% if exp.location %} | {{ exp.location }}{% endif %}"
    )
    meta.runs[0].italic = True
    meta.runs[0].font.size = Pt(10)
    doc.add_paragraph("{%p for bullet in exp.bullets %}")
    doc.add_paragraph("{{ bullet }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endfor %}")

    _add_section_title(doc, "Wykształcenie")
    doc.add_paragraph("{%p for line in cv.education_lines %}")
    doc.add_paragraph("{{ line }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    _add_section_title(doc, "Umiejętności")
    doc.add_paragraph("{{ cv.skills | join(', ') }}")

    _add_section_title(doc, "Języki")
    doc.add_paragraph("{{ cv.languages | join(', ') }}")

    _add_section_title(doc, "Certyfikaty")
    doc.add_paragraph("{%p for cert in cv.certifications %}")
    doc.add_paragraph("{{ cert }}", style="List Bullet")
    doc.add_paragraph("{%p endfor %}")

    doc.save(template_path)
    return template_path


def _add_section_title(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)


def render_cv(
    cv: TailoredCV,
    *,
    template_path: Path | None = None,
    output_dir: Path | None = None,
    filename: str | None = None,
) -> Path:
    """Render the CV to a .docx file and return its path."""
    settings = get_settings()
    template_path = template_path or ensure_default_template()
    output_dir = output_dir or settings.app_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_slug = "_".join(cv.full_name.lower().split())
        filename = f"cv_{name_slug}_{stamp}.docx"

    output_path = output_dir / filename
    doc = DocxTemplate(str(template_path))
    doc.render({"cv": cv.model_dump()})
    doc.save(str(output_path))
    return output_path
