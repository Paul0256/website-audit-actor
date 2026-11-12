from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.audit import audit_site, business_name, normalize_url, opportunities
from src.signals import analyze, normalize_phone

SITES = Path(__file__).parent / "sites"


def page(name: str) -> str:
    return (SITES / name).read_text()


def mock_client(routes: dict[str, str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="not found", headers={"content-type": "text/html"})
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_analyze_finds_contacts_links_and_tech():
    s = analyze("https://brightsmileboise.com/", page("dental_home.html"))
    assert s.title.startswith("Bright Smile Dental")
    assert s.phones == {"(208) 555-0142"}
    assert s.socials["facebook"] == "https://www.facebook.com/brightsmileboise"
    assert "yelp" in s.socials and "instagram" in s.socials
    assert s.emails == set()  # "info@2x.png" is an image name, not an address
    assert s.cms == {"WordPress"} and s.analytics == {"Google Analytics"}
    assert s.links["contact"] == ["https://brightsmileboise.com/contact/"]
    assert s.links["faq"] == ["https://brightsmileboise.com/faq/"]
    assert s.links["pricing"] == ["https://brightsmileboise.com/insurance-and-financing/"]
    assert s.copyright_year == 2019 and s.viewport and not s.chat_vendors


def test_contact_page_email_form():
    s = analyze("https://brightsmileboise.com/contact/", page("dental_contact.html"))
    assert s.emails == {"office@brightsmileboise.com", "frontdesk@brightsmileboise.com"}
    assert s.has_form


def test_vendors_and_booking():
    s = analyze("https://riversidephysio.com/", page("modern_home.html"))
    assert s.chat_vendors == {"Tawk.to"} and s.booking_vendors == {"Jane"}
    assert s.cms == {"Wix"} and s.analytics == {"Meta Pixel"}
    assert s.copyright_year == 2026 and s.booking_cta


@pytest.mark.parametrize(
    "raw,expected",
    [("example.com", "https://example.com/"), ("http://x.org/a", "http://x.org/a"), ("", None), ("localhost", None)],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_normalize_phone():
    assert normalize_phone("+1 208.555.0142") == "(208) 555-0142"


async def test_full_audit_reads_key_pages_and_scores_gaps():
    base = "https://brightsmileboise.com/"
    client = mock_client(
        {
            base: page("dental_home.html"),
            base + "contact/": page("dental_contact.html"),
            base + "faq/": page("dental_faq.html"),
        }
    )
    async with client:
        r = await audit_site(client, "brightsmileboise.com", max_pages=4, extra={"name": "Bright Smile Dental"})
    assert r["ok"] and r["domain"] == "brightsmileboise.com" and r["pagesRead"] == 3  # pricing page 404s
    assert r["emails"] == ["frontdesk@brightsmileboise.com", "office@brightsmileboise.com"]
    assert r["hasContactForm"] and r["hasFaq"] and not r["hasLiveChat"] and not r["hasOnlineBooking"]
    assert r["opportunities"][:2] == ["No live chat or AI assistant", "No online booking"]
    assert "Footer copyright is from 2019" in r["opportunities"]
    assert r["pitchAngle"].startswith("Bright Smile Dental: visitors with a question after hours")
    assert r["opportunityScore"] == 50


async def test_unreachable_site_is_reported_not_raised():
    async with mock_client({}) as client:
        r = await audit_site(client, "https://gone.example")
    assert r == {
        "inputUrl": "https://gone.example",
        "url": "https://gone.example/",
        "ok": False,
        "error": "Website did not respond with a page",
    }


def test_complete_site_has_nothing_to_pitch():
    r = {
        "hasLiveChat": True,
        "hasOnlineBooking": True,
        "hasFaq": True,
        "hasContactForm": True,
        "https": True,
        "mobileFriendly": True,
        "copyrightYear": 2026,
        "analytics": ["Google Analytics"],
        "domain": "x.com",
    }
    assert opportunities(r, 2026) == ([], 0, "")


def test_business_name_from_title():
    assert business_name("Bright Smile Dental | Family Dentist in Boise") == "Bright Smile Dental"
    assert business_name("Home - Riverside Physio") == "Home"
