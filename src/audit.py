"""Audit one business website: read the homepage and a few key pages, merge what they show,
and say what the business is missing (chat, booking, FAQ, form...) as sales opportunities."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from .signals import PageSignals, analyze

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# Which linked pages to read after the homepage, most useful first.
FOLLOW_ORDER = ("contact", "faq", "pricing", "booking", "about")
MAX_HTML = 3_000_000  # bytes; bigger pages are cut, not refused


def normalize_url(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if not parsed.hostname or "." not in parsed.hostname:
        return None
    return raw if parsed.path else raw + "/"


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Final URL and HTML, or None when the page is not HTML or not reachable."""
    try:
        resp = await client.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", "html"):
        return None
    return str(resp.url), resp.text[:MAX_HTML]


async def fetch_home(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    got = await fetch(client, url)
    if got is None and url.startswith("https://"):
        got = await fetch(client, "http://" + url[len("https://") :])
    return got


def merge(pages: list[PageSignals]) -> dict:
    home = pages[0]

    def union(attr: str) -> list[str]:
        return sorted(set().union(*(getattr(p, attr) for p in pages)))

    socials: dict[str, str] = {}
    for p in pages:
        for k, v in p.socials.items():
            socials.setdefault(k, v)
    found = {hint: (home.links.get(hint) or [None])[0] for hint in ("contact", "faq", "pricing", "booking")}
    years = [p.copyright_year for p in pages if p.copyright_year]
    return {
        "title": home.title,
        "description": home.description,
        "emails": union("emails")[:10],
        "phones": union("phones")[:5],
        "socials": socials,
        "contactPageUrl": found["contact"],
        "hasContactForm": any(p.has_form for p in pages),
        "formVendors": union("form_vendors"),
        "hasLiveChat": any(p.chat_vendors for p in pages),
        "chatVendors": union("chat_vendors"),
        # A booking vendor, or a "Book an appointment" link that leads to a booking page.
        "hasOnlineBooking": any(p.booking_vendors for p in pages)
        or (bool(found["booking"]) and any(p.booking_cta for p in pages)),
        "bookingVendors": union("booking_vendors"),
        "hasFaq": bool(found["faq"]) or any(p.faq for p in pages),
        "faqUrl": found["faq"],
        "hasPricingPage": bool(found["pricing"]),
        "pricingUrl": found["pricing"],
        "mobileFriendly": home.viewport,
        "cms": union("cms"),
        "analytics": union("analytics"),
        "copyrightYear": max(years) if years else None,
    }


GENERIC_TITLE = re.compile(r"^(home|homepage|welcome|index|main)$", re.IGNORECASE)


def business_name(title: str, domain: str = "") -> str:
    """The part of the page title that names the business.

    'Home | Hidden Springs Dental' -> 'Hidden Springs Dental'; with the domain, the part that
    looks most like it wins: 'Dentist in Boise, ID | Ustick Dental Office' + ustickdental.com
    -> 'Ustick Dental Office'.
    """
    parts = [p.strip() for p in re.split(r"\s+(?:\||–|—|-|::|·)\s+", title) if p.strip()]
    parts = [p for p in parts if not GENERIC_TITLE.match(p)] or parts
    if not parts:
        return ""
    site = re.sub(r"[^a-z0-9]", "", domain.split(".")[0].lower())
    if site:

        def overlap(part: str) -> int:
            words = re.findall(r"[a-z0-9]+", part.lower())
            return sum(len(w) for w in words if len(w) > 2 and w in site)

        best = max(parts, key=overlap)
        if overlap(best) > 0:
            return best
    return parts[0]


def opportunities(r: dict, now_year: int) -> tuple[list[str], int, str]:
    """Gaps a vendor could pitch, a 0-100 score (higher = more to offer) and a one-line pitch angle."""
    gaps: list[tuple[int, str, str]] = []  # weight, label, pitch
    if not r["hasLiveChat"]:
        gaps.append(
            (
                25,
                "No live chat or AI assistant",
                "visitors with a question after hours have no one to ask, so they call or leave",
            )
        )
    if not r["hasOnlineBooking"]:
        gaps.append((20, "No online booking", "customers can't book without calling during opening hours"))
    if not r["hasFaq"]:
        gaps.append((15, "No FAQ page", "common questions about prices and process still land on the phone"))
    # Many forms are drawn by JavaScript, which plain requests don't run: a contact page
    # without a visible form is not proof that there is no form.
    if not r["hasContactForm"] and not r["contactPageUrl"]:
        gaps.append((15, "No contact form", "there's no simple way to send a question from the website"))
    if not r["https"]:
        gaps.append((10, "Not served over HTTPS", "browsers mark the site as 'Not secure'"))
    if not r["mobileFriendly"]:
        gaps.append((10, "Not mobile-friendly", "the site is hard to use on a phone"))
    if r["copyrightYear"] and r["copyrightYear"] <= now_year - 3:
        gaps.append((5, f"Footer copyright is from {r['copyrightYear']}", "the site may look unmaintained"))
    if not r["analytics"]:
        gaps.append((5, "No analytics", "there's no way to see where visitors come from"))
    gaps.sort(key=lambda g: -g[0])
    score = min(100, sum(g[0] for g in gaps))
    pitch = ""
    if gaps:
        name = r.get("name") or business_name(r.get("title") or "", r["domain"]) or r["domain"]
        pitch = f"{name}: {gaps[0][2]}."
    return [g[1] for g in gaps], score, pitch


async def audit_site(client: httpx.AsyncClient, raw_url: str, max_pages: int = 4, extra: dict | None = None) -> dict:
    url = normalize_url(raw_url)
    base = {"inputUrl": raw_url, **(extra or {})}
    if url is None:
        return {**base, "domain": raw_url, "ok": False, "error": "Not a website address"}
    home = await fetch_home(client, url)
    if home is None:
        host = (urlparse(url).hostname or "").removeprefix("www.")
        return {**base, "url": url, "domain": host, "ok": False, "error": "Website did not respond with a page"}
    final_url, html = home
    pages = [analyze(final_url, html)]

    to_visit: list[str] = []
    for hint in FOLLOW_ORDER:
        for link in pages[0].links.get(hint, [])[:1]:
            if link not in to_visit and link.rstrip("/") != final_url.rstrip("/"):
                to_visit.append(link)
    results = await asyncio.gather(*(fetch(client, u) for u in to_visit[: max(0, max_pages - 1)]))
    pages += [analyze(u, h) for u, h in (r for r in results if r)]

    host = urlparse(final_url).hostname or ""
    report = {
        **base,
        "url": final_url,
        "domain": host.removeprefix("www."),
        "ok": True,
        "pagesRead": len(pages),
        "https": final_url.startswith("https://"),
        **merge(pages),
    }
    gaps, score, pitch = opportunities(report, datetime.now(UTC).year)
    report["opportunities"] = gaps
    report["opportunityScore"] = score
    report["pitchAngle"] = pitch
    return report


def make_client(proxy: str | None = None, timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        follow_redirects=True,
        timeout=timeout,
        proxy=proxy,
        limits=httpx.Limits(max_connections=50),
    )
