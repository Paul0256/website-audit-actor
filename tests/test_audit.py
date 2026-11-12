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
    assert "No contact form found" not in r["opportunities"]
    assert r["pitchAngle"].startswith("Bright Smile Dental: visitors with a question after hours")
    assert r["opportunityScore"] == 50


async def test_unreachable_site_is_reported_not_raised():
    async with mock_client({}) as client:
        r = await audit_site(client, "https://gone.example")
    assert r == {
        "inputUrl": "https://gone.example",
        "url": "https://gone.example/",
        "domain": "gone.example",
        "ok": False,
        "error": "HTTP 404",
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
    assert business_name("Home - Riverside Physio") == "Riverside Physio"
    assert business_name("Home | Hidden Springs Dental", "hiddenspringsdental.com") == "Hidden Springs Dental"
    assert business_name("Dentist in Boise, ID | Ustick Dental Office", "ustickdental.com") == "Ustick Dental Office"
    assert business_name("Boise Bench Dentistry - Dentist in Boise, ID", "boisebenchdentistry.com") == (
        "Boise Bench Dentistry"
    )


def test_hidden_and_obfuscated_emails():
    from src.signals import analyze

    html = (
        '<a href="/cdn-cgi/l/email-protection#4f202929262c2a0f2d2a212c27612c20">[email protected]</a>'
        '<span class="__cf_email__" data-cfemail="4f202929262c2a0f2d2a212c27612c20">x</span>'
        "<p>Write to frontdesk [at] smile-co [dot] com</p>"
    )
    s = analyze("https://x.com/", html)
    assert s.emails == {"office@bench.co", "frontdesk@smile-co.com"}


def test_structured_data_gives_name_email_phone_socials():
    html = """<html><head><title>Dentist in Boise, ID | Boise Bench Dentistry</title>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebSite","name":"x"},
    {"@type":["Dentist","LocalBusiness"],"name":"Boise Bench Dentistry","email":"office@boisebenchdentistry.com",
     "telephone":"+1-208-555-0100","sameAs":["https://www.facebook.com/boisebench"],
     "address":{"@type":"PostalAddress","streetAddress":"1 Main St","addressLocality":"Boise","addressRegion":"ID"}}]}
    </script></head><body></body></html>"""
    s = analyze("https://www.boisebenchdentistry.com/", html)
    assert s.business_name == "Boise Bench Dentistry"
    assert s.emails == {"office@boisebenchdentistry.com"} and s.phones == {"(208) 555-0100"}
    assert s.socials["facebook"] == "https://www.facebook.com/boisebench"
    assert s.address == "1 Main St, Boise, ID"


async def test_blocked_site_says_so():
    def handler(request):
        return httpx.Response(403, text="no", headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r = await audit_site(client, "idahofamilydental.com")
    assert r["ok"] is False and r["error"] == "Blocked by the website (HTTP 403)"


def test_mailto_with_encoded_space():
    html = '<html><body><a href="mailto:%20office@goulet.example">Email us</a></body></html>'
    assert analyze("https://goulet.example/", html).emails == {"office@goulet.example"}


def test_oryx_booking_link_is_booking_not_x_profile():
    html = (
        '<html><body><a href="https://mychart.myoryx.com/online-schedule/index.html">Book</a>'
        '<a href="tel:%20253-999-5503">Call</a><a href="https://x.com/clinic">X</a></body></html>'
    )
    s = analyze("https://clinic.example/", html)
    assert "Oryx" in s.booking_vendors
    assert s.socials.get("x") == "https://x.com/clinic"
    assert s.phones == {"(253) 999-5503"}
