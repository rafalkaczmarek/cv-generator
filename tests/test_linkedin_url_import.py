"""Tests for public LinkedIn profile URL import."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from cv_generator.models import Education, Experience, Profile
from cv_generator.services.linkedin_url_import import (
    LinkedInUrlImportError,
    is_linkedin_profile_url,
    merge_profiles,
    profile_from_linkedin_html,
    profile_from_linkedin_url,
)

SAMPLE_HTML = """
<html>
<head>
<meta property="og:title" content="Jan Kowalski - Senior Python Developer | LinkedIn">
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@type": "ProfilePage",
  "mainEntity": {
    "@type": "Person",
    "name": "Jan Kowalski",
    "description": "Senior Python Developer with 10 years of backend experience.",
    "sameAs": "https://www.linkedin.com/in/jan-kowalski/",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Warszawa",
      "addressCountry": "PL"
    },
    "jobTitle": ["Senior Python Developer", "Backend Developer", ""],
    "knowsLanguage": [
      {"@type": "Language", "name": "Polish"},
      {"@type": "Language", "name": "English"}
    ],
    "alumniOf": [{
      "@type": "EducationalOrganization",
      "name": "Politechnika Warszawska",
      "member": {"@type": "OrganizationRole", "startDate": 2013, "endDate": 2018}
    }],
    "worksFor": [
      {
        "@type": "Organization",
        "name": "Acme Corp",
        "member": {"@type": "OrganizationRole", "startDate": 2021}
      }
    ]
  }
}
</script>
</head>
<body>
<h2>Education</h2>
<h3>Politechnika Warszawska</h3>
<p>Bachelor of Science in Computer Science</p>
<p>2013 - 2018</p>
</body>
</html>
"""

JSON_LD_ONLY_HTML = SAMPLE_HTML.replace(
    """<body>
<h2>Education</h2>
<h3>Politechnika Warszawska</h3>
<p>Bachelor of Science in Computer Science</p>
<p>2013 - 2018</p>
</body>""",
    "<body></body>",
)

EDUCATION_DETAILS_HTML = """
<html><body>
<h2>Education</h2>
<h3 class="[&>*]:mb-0 text-[18px] text-color-text leading-regular font-semibold">
      Politechnika Warszawska</h3>
<p>Bachelor of Science in Computer Science</p>
<p>2013 - 2018</p>
</body></html>
"""

ROLE_NAME_HTML = SAMPLE_HTML.replace(
    '"member": {"@type": "OrganizationRole", "startDate": 2013, "endDate": 2018}',
    '"member": {"@type": "OrganizationRole", "startDate": 2013, "endDate": 2018, '
    '"roleName": "Bachelor of Science in Computer Science"}',
).replace(
    """<body>
<h2>Education</h2>
<h3>Politechnika Warszawska</h3>
<p>Bachelor of Science in Computer Science</p>
<p>2013 - 2018</p>
</body>""",
    "<body></body>",
)

PROJECTS_HTML = """
<html><body>
<h2>Projects</h2>
<h3>Pekao website</h3>
<p>Aug 2019</p>
<p>Implement new frontend features for the Pekao S.A. bank.</p>
<h3>Virtamed cloud</h3>
<p>Oct 2017 - Apr 2019</p>
<p>Implement frontend of the project Virtamed cloud.</p>
<p>(SCRUM, Single Page Application, Angular 5, Jasmine, Webpack, npm)</p>
<h2>Courses</h2>
<p>Angular</p>
<p>Docker/Kubernetes</p>
<h2>Languages</h2>
</body></html>
"""

LODZ_JSON_LD_HEAD = """
<html><head><script type="application/ld+json">{
  "@type":"ProfilePage",
  "mainEntity":{
    "@type":"Person",
    "name":"Rafał Kaczmarek",
    "alumniOf":[{
      "@type":"EducationalOrganization",
      "name":"Lodz University of Technology",
      "member":{"@type":"OrganizationRole","startDate":2011,"endDate":2015}
    }]
  }
}</script></head>
"""

LODZ_HTML_REVERSED_DEGREE = (
    LODZ_JSON_LD_HEAD
    + """<body>
<h2>Education</h2>
<h3>Inżynier (Inż.)</h3>
<p>Politechnika Łódzka</p>
<p>2011 - 2015</p>
</body></html>"""
)

LODZ_HTML_POLISH_SCHOOL = (
    LODZ_JSON_LD_HEAD
    + """<body>
<h2>Wykształcenie</h2>
<h3>Politechnika Łódzka</h3>
<p>Inżynier (Inż.), Informatyka</p>
<p>2011 - 2015</p>
</body></html>"""
)

BROKEN_TAILWIND_PROJECTS_HTML = """
<html><body>
<div>Sign in to view Rafał's full profile</div>
<h2>Activity</h2>
<h3>Interesting post</h3>
<p>Liked by Rafał Kaczmarek</p>
<h2>Projects</h2>
<h3 class="[&>*]:mb-0 text-[18px] text-color-text leading-regular group-hover:underline font-semibold">      Pekao website</h3>
<p class="[&>*]:mb-0 not-first-middot leading-[1.75]">Aug 2019</p>
<p>Implement new frontend features for the Pekao S.A. bank.</p>
<h3 class="[&>*]:mb-0 text-[18px] text-color-text leading-regular group-hover:underline font-semibold">      Virtamed cloud</h3>
<p>Oct 2017 - Apr 2019</p>
<p>Implement frontend of the project Virtamed cloud.</p>
<h2>Courses</h2>
<h3 class="[&>*]:mb-0 text-[18px] text-color-text leading-regular group-hover:underline font-semibold">    Angular</h3>
<h2>Languages</h2>
<h3 class="[&>*]:mb-0 text-[18px] text-color-text leading-regular group-hover:underline font-semibold">    Polish</h3>
<h2>People also viewed</h2>
<h3>Arkadiusz Bednarowski</h3>
<p>S&amp;P Global</p>
<p>226 followers</p>
<p>View Profile</p>
</body></html>
"""

MASKED_HTML = """
<html>
<script type="application/ld+json">
{
  "@type": "ProfilePage",
  "mainEntity": {
    "@type": "Person",
    "name": "Jan Kowalski",
    "description": "Developer",
    "worksFor": [
      {"@type": "Organization", "name": "****** *****"},
      {"@type": "Organization", "name": "Sii Poland"}
    ],
    "jobTitle": ["****** *******", ""]
  }
}
</script>
<body><h2>Projects</h2><h3>Real project</h3><p>Jan 2020</p><p>Visible work.</p></body>
</html>
"""


def test_is_linkedin_profile_url() -> None:
    assert is_linkedin_profile_url("https://www.linkedin.com/in/jan-kowalski/")
    assert is_linkedin_profile_url("https://pl.linkedin.com/in/jan-kowalski")
    assert is_linkedin_profile_url(
        "https://www.linkedin.com/in/jan-kowalski/details/projects/"
    )
    assert not is_linkedin_profile_url("https://example.com/in/jan")


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_profile_from_linkedin_url_uses_projects_page(mock_fetch: object) -> None:
    mock_fetch.side_effect = [SAMPLE_HTML, PROJECTS_HTML]  # type: ignore[attr-defined]

    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")

    assert profile.full_name == "Jan Kowalski"
    assert profile.headline == "Senior Python Developer"
    assert profile.location == "Warszawa, PL"
    assert profile.languages == ["Polish", "English"]
    assert profile.skills == ["Angular", "Docker/Kubernetes"]

    assert len(profile.experiences) == 2
    pekao = profile.experiences[0]
    assert pekao.title == "Pekao website"
    assert pekao.company == "Bank Pekao S.A."
    assert pekao.start_date == date(2019, 8, 1)

    virtamed = profile.experiences[1]
    assert virtamed.title == "Virtamed cloud"
    assert virtamed.end_date == date(2019, 4, 1)
    assert "Angular 5" in virtamed.technologies

    assert len(profile.education) == 1
    assert profile.education[0].institution == "Politechnika Warszawska"
    assert profile.education[0].degree == "Bachelor of Science in Computer Science"
    assert profile.education[0].start_date == date(2013, 1, 1)
    assert profile.education[0].end_date == date(2018, 1, 1)


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_profile_from_linkedin_url_ignores_non_project_h3_sections(mock_fetch: object) -> None:
    mock_fetch.side_effect = [SAMPLE_HTML, BROKEN_TAILWIND_PROJECTS_HTML]  # type: ignore[attr-defined]

    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")

    assert len(profile.experiences) == 2
    assert profile.experiences[0].title == "Pekao website"
    assert profile.experiences[1].title == "Virtamed cloud"
    assert all("text-[18px]" not in exp.title for exp in profile.experiences)
    assert all("*]:mb-0" not in exp.title for exp in profile.experiences)
    assert all(exp.title != "Angular" for exp in profile.experiences)
    assert profile.skills == ["Angular"]
    assert all("*]:mb-0" not in skill for skill in profile.skills)


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_masked_json_ld_experience_is_ignored(mock_fetch: object) -> None:
    mock_fetch.side_effect = [MASKED_HTML, MASKED_HTML]  # type: ignore[attr-defined]
    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")
    assert len(profile.experiences) == 1
    assert profile.experiences[0].title == "Real project"
    assert "*" not in profile.experiences[0].company


def test_merge_profiles_keeps_existing_and_fills_gaps() -> None:
    existing = Profile(
        full_name="Jan Kowalski",
        headline="Mój nagłówek",
        email="jan@example.com",
        experiences=[
            Experience(
                company="Obecna firma",
                title="Lead",
                start_date=date(2024, 1, 1),
                is_current=True,
            )
        ],
        skills=["Python"],
    )
    incoming = Profile(
        full_name="Z LinkedIn",
        headline="Z LinkedIn headline",
        location="Warszawa",
        experiences=[
            Experience(
                company="Bank Pekao S.A.",
                title="Pekao website",
                start_date=date(2019, 8, 1),
            )
        ],
        skills=["Angular", "Python"],
        languages=["Polish"],
    )

    merged = merge_profiles(existing, incoming)

    assert merged.full_name == "Jan Kowalski"
    assert merged.headline == "Mój nagłówek"
    assert merged.location == "Warszawa"
    assert merged.email == "jan@example.com"
    assert len(merged.experiences) == 2
    assert merged.skills == ["Python", "Angular"]
    assert merged.languages == ["Polish"]


def test_invalid_url_raises() -> None:
    with pytest.raises(LinkedInUrlImportError, match="poprawny URL"):
        profile_from_linkedin_url("https://example.com/profile")


def test_profile_from_linkedin_html_parses_saved_page() -> None:
    profile = profile_from_linkedin_html(SAMPLE_HTML + "\n" + PROJECTS_HTML)
    assert profile.full_name == "Jan Kowalski"
    assert profile.experiences[0].title == "Pekao website"
    assert profile.education[0].degree == "Bachelor of Science in Computer Science"
    assert profile.skills == ["Angular", "Docker/Kubernetes"]
    assert str(profile.linkedin_url).rstrip("/").endswith("/in/jan-kowalski")


def test_profile_from_linkedin_html_empty_raises() -> None:
    with pytest.raises(LinkedInUrlImportError, match="pusty"):
        profile_from_linkedin_html("   ")


def test_profile_from_linkedin_html_merges_json_ld_and_polish_school_name() -> None:
    profile = profile_from_linkedin_html(LODZ_HTML_POLISH_SCHOOL)
    assert len(profile.education) == 1
    assert profile.education[0].institution == "Lodz University of Technology"
    assert profile.education[0].degree == "Inżynier (Inż.), Informatyka"
    assert profile.education[0].start_date == date(2011, 1, 1)
    assert profile.education[0].end_date == date(2015, 1, 1)


def test_profile_from_linkedin_html_handles_degree_in_h3() -> None:
    profile = profile_from_linkedin_html(LODZ_HTML_REVERSED_DEGREE)
    assert len(profile.education) == 1
    assert profile.education[0].institution == "Lodz University of Technology"
    assert profile.education[0].degree == "Inżynier (Inż.)"


def test_profile_from_linkedin_html_merges_with_existing_profile() -> None:
    imported = profile_from_linkedin_html(LODZ_HTML_POLISH_SCHOOL)
    existing = Profile(
        full_name="Rafał",
        education=[
            Education(
                institution="Lodz University of Technology",
                degree="",
                start_date=date(2011, 1, 1),
                end_date=date(2015, 1, 1),
            )
        ],
    )
    merged = merge_profiles(existing, imported)
    assert len(merged.education) == 1
    assert merged.education[0].degree == "Inżynier (Inż.), Informatyka"


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_http_999_with_json_ld_is_accepted(mock_fetch: object) -> None:
    mock_fetch.side_effect = [SAMPLE_HTML, PROJECTS_HTML]  # type: ignore[attr-defined]
    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")
    assert profile.full_name == "Jan Kowalski"


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_missing_json_ld_raises(mock_fetch: object) -> None:
    mock_fetch.return_value = "<html><body>login required</body></html>"  # type: ignore[attr-defined]
    with pytest.raises(LinkedInUrlImportError, match="publicznych danych"):
        profile_from_linkedin_url("https://www.linkedin.com/in/private-user/")


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_education_degree_from_details_page_when_main_omits_it(mock_fetch: object) -> None:
    mock_fetch.side_effect = [  # type: ignore[attr-defined]
        JSON_LD_ONLY_HTML,
        PROJECTS_HTML,
        EDUCATION_DETAILS_HTML,
    ]
    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")
    assert profile.education[0].degree == "Bachelor of Science in Computer Science"


@patch("cv_generator.services.linkedin_url_import._fetch_profile_html")
def test_education_degree_from_json_ld_role_name(mock_fetch: object) -> None:
    mock_fetch.side_effect = [ROLE_NAME_HTML, PROJECTS_HTML]  # type: ignore[attr-defined]
    profile = profile_from_linkedin_url("https://www.linkedin.com/in/jan-kowalski/")
    assert profile.education[0].degree == "Bachelor of Science in Computer Science"
