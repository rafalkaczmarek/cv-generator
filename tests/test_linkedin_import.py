"""Tests for the LinkedIn data-export importer."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from cv_generator.services.linkedin_import import (
    LinkedInImportError,
    profile_from_linkedin_csv,
    profile_from_linkedin_zip,
)

PROFILE_CSV = (
    "First Name,Last Name,Headline,Summary,Industry,Geo Location,Websites\r\n"
    'Jan,Kowalski,Senior Python Developer,Backend od 10 lat,Software,'
    '"Warszawa, Poland","[PORTFOLIO:https://jan.dev],[OTHER:https://github.com/jankowalski]"\r\n'
)

POSITIONS_CSV = (
    "Company Name,Title,Description,Location,Started On,Finished On\r\n"
    "Acme Corp,Senior Backend Engineer,Praca nad platformą,Warszawa,Jan 2021,\r\n"
    "Beta Sp. z o.o.,Backend Developer,Mikroserwisy,Kraków,Jun 2018,Dec 2020\r\n"
)

EDUCATION_CSV = (
    "School Name,Start Date,End Date,Notes,Degree Name,Field Of Study\r\n"
    "Politechnika Warszawska,2013,2018,,mgr inż.,Informatyka\r\n"
)

SKILLS_CSV = "Name\r\nPython\r\nFastAPI\r\nPython\r\nDocker\r\n"

LANGUAGES_CSV = "Name,Proficiency\r\nPolish,Native or bilingual\r\nEnglish,Full professional\r\n"

CERTIFICATIONS_CSV = (
    "Name,Url,Authority,Started On,License Number\r\n"
    "AWS Certified,https://aws.example/cert,Amazon,Mar 2022,ABC123\r\n"
)

EMAIL_CSV = (
    "Email Address,Confirmed,Primary,Updated On\r\n"
    "old@example.com,Yes,No,2020\r\n"
    "jan@example.com,Yes,Yes,2023\r\n"
)


def _build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("Profile.csv", PROFILE_CSV)
        zf.writestr("Positions.csv", POSITIONS_CSV)
        zf.writestr("Education.csv", EDUCATION_CSV)
        zf.writestr("Skills.csv", SKILLS_CSV)
        zf.writestr("Languages.csv", LANGUAGES_CSV)
        zf.writestr("Certifications.csv", CERTIFICATIONS_CSV)
        zf.writestr("Email Addresses.csv", EMAIL_CSV)
    return buffer.getvalue()


def test_zip_import_maps_all_sections() -> None:
    profile = profile_from_linkedin_zip(_build_zip())

    assert profile.full_name == "Jan Kowalski"
    assert profile.headline == "Senior Python Developer"
    assert str(profile.github_url).rstrip("/") == "https://github.com/jankowalski"
    assert str(profile.website_url).rstrip("/") == "https://jan.dev"

    assert profile.email == "jan@example.com"  # primary wins over the older one

    assert len(profile.experiences) == 2
    current = profile.experiences[0]
    assert current.company == "Acme Corp"
    assert current.start_date == date(2021, 1, 1)
    assert current.is_current is True
    assert current.end_date is None
    past = profile.experiences[1]
    assert past.is_current is False
    assert past.end_date == date(2020, 12, 1)

    assert profile.education[0].institution == "Politechnika Warszawska"
    assert profile.education[0].start_date == date(2013, 1, 1)

    assert profile.skills == ["Python", "FastAPI", "Docker"]  # deduped, order kept
    assert profile.languages == [
        "Polish - Native or bilingual",
        "English - Full professional",
    ]
    assert profile.certifications[0].name == "AWS Certified"
    assert profile.certifications[0].issued == date(2022, 3, 1)


def test_zip_import_handles_folder_prefixed_names() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("Basic_LinkedInDataExport/Profile.csv", PROFILE_CSV)
        zf.writestr("Basic_LinkedInDataExport/Skills.csv", SKILLS_CSV)
    profile = profile_from_linkedin_zip(buffer.getvalue())
    assert profile.full_name == "Jan Kowalski"
    assert "Python" in profile.skills


def test_single_csv_import() -> None:
    profile = profile_from_linkedin_csv("Positions.csv", POSITIONS_CSV)
    assert profile.full_name == "—"  # placeholder, user fills it in
    assert len(profile.experiences) == 2


def test_directory_import(tmp_path) -> None:
    (tmp_path / "Profile.csv").write_text(PROFILE_CSV, encoding="utf-8")
    (tmp_path / "Skills.csv").write_text(SKILLS_CSV, encoding="utf-8")
    profile = profile_from_linkedin_zip(tmp_path)
    assert profile.full_name == "Jan Kowalski"
    assert "FastAPI" in profile.skills


def test_unrecognized_single_csv_raises() -> None:
    with pytest.raises(LinkedInImportError):
        profile_from_linkedin_csv("Connections.csv", "a,b\r\n1,2\r\n")


def test_bad_zip_raises() -> None:
    with pytest.raises(LinkedInImportError):
        profile_from_linkedin_zip(b"not a zip file")


def test_empty_archive_raises() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("Connections.csv", "First Name\r\nX\r\n")
    with pytest.raises(LinkedInImportError):
        profile_from_linkedin_zip(buffer.getvalue())
