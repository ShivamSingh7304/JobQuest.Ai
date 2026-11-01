"""Small dependency-free PDF generator for approved tailored resumes."""

from pathlib import Path
from typing import Any


def _pdf_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    return text.encode("latin-1", "replace").decode("latin-1")


def _lines(tailoring: dict[str, Any]) -> list[str]:
    lines = [
        _pdf_text(tailoring.get("target_role", "Tailored Resume")),
        "",
        "PROFESSIONAL SUMMARY",
        _pdf_text(tailoring.get("professional_summary")),
        "",
        "RELEVANT SKILLS",
        _pdf_text(", ".join(tailoring.get("relevant_skills", []))),
        "",
        "EXPERIENCE",
    ]
    for bullet in tailoring.get("experience_bullets", []):
        lines.append("- " + _pdf_text(bullet.get("tailored", bullet)))
    lines.append("")
    lines.append("PROJECTS")
    for bullet in tailoring.get("project_bullets", []):
        lines.append("- " + _pdf_text(bullet.get("tailored", bullet)))
    lines.extend(["", "ADDITIONAL INFORMATION"])
    for item in tailoring.get("additional_relevant_information", []):
        lines.append("- " + _pdf_text(item))
    return lines


def tailored_resume_to_pdf(tailoring: dict[str, Any], path: Path) -> str:
    """Write a simple readable PDF and return its extracted text."""

    lines = _lines(tailoring)
    visible_lines = lines[:44]
    commands = ["BT", "/F1 11 Tf", "50 760 Td"]
    for index, line in enumerate(visible_lines):
        if index:
            commands.append("0 -16 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    path.write_bytes(pdf)
    return "\n".join(line for line in lines if line)
