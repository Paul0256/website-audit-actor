"""What a page reveals about a business: contacts, chat, booking, forms, FAQ, pricing, tech.

Pure functions over HTML, so they are easy to test and need no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

# Script, iframe or link fragments that identify a live chat or AI assistant vendor.
CHAT_VENDORS = {
    "Intercom": ("widget.intercom.io", "js.intercomcdn.com"),
    "Drift": ("js.driftt.com", "drift.com/include"),
    "Tawk.to": ("embed.tawk.to",),
    "LiveChat": ("cdn.livechatinc.com",),
    "Zendesk": ("static.zdassets.com", "zopim.com"),
    "Crisp": ("client.crisp.chat",),
    "Tidio": ("code.tidio.co",),
    "HubSpot Chat": ("js.usemessages.com", "hubspot-messages-iframe"),
    "Olark": ("static.olark.com",),
    "Freshchat": ("wchat.freshchat.com", "freshworks.com/live-chat"),
    "Facebook Messenger": ("customerchat", "xfbml.customerchat"),
    "Podium": ("connect.podium.com", "podium.com/widget"),
    "Birdeye": ("birdeye.com/embed",),
    "Weave": ("getweave.com", "weavehelp"),
    "Zoho SalesIQ": ("salesiq.zoho",),
    "JivoChat": ("code.jivosite.com", "jivochat"),
    "Chatbase": ("chatbase.co/embed",),
    "Voiceflow": ("cdn.voiceflow.com",),
    "Botpress": ("cdn.botpress.cloud",),
    "Userlike": ("userlike-cdn-widgets",),
    "Chaport": ("app.chaport.com",),
    "Gorgias": ("config.gorgias.chat",),
    "Kommunicate": ("widget.kommunicate.io",),
    "LiveAgent": ("ladesk.com",),
    "Smith.ai": ("smith.ai/chat",),
    "ManyChat": ("widget.manychat.com",),
}

BOOKING_VENDORS = {
    "Calendly": ("calendly.com",),
    "Acuity": ("acuityscheduling.com",),
    "Square Appointments": ("squareup.com/appointments", "square.site/book"),
    "Zocdoc": ("zocdoc.com",),
    "NexHealth": ("nexhealth.com",),
    "LocalMed": ("localmed.com",),
    "Opencare": ("opencare.com",),
    "Setmore": ("setmore.com",),
    "SimplyBook": ("simplybook.me",),
    "Booksy": ("booksy.com",),
    "Vagaro": ("vagaro.com",),
    "Mindbody": ("mindbodyonline.com", "mindbody.io"),
    "Jane": ("janeapp.com", ".jane.app"),
    "Fresha": ("fresha.com",),
    "Schedulicity": ("schedulicity.com",),
    "Appointy": ("appointy.com",),
    "YouCanBookMe": ("youcanbook.me",),
    "Cal.com": ("cal.com/",),
    "Doctible": ("doctible.com",),
    "Flexbook": ("flexbook.me",),
    "Weave Online Scheduling": ("book.getweave.com",),
}

FORM_VENDORS = {
    "Typeform": ("typeform.com",),
    "Jotform": ("jotform.com",),
    "HubSpot Forms": ("js.hsforms.net", "hsforms.com"),
    "Gravity Forms": ("gform_wrapper", "gravityforms"),
    "WPForms": ("wpforms",),
    "Contact Form 7": ("wpcf7",),
    "Google Forms": ("docs.google.com/forms",),
}

CMS = {
    "WordPress": ("wp-content/", "wp-includes/"),
    "Wix": ("static.wixstatic.com", "wix.com"),
    "Squarespace": ("static1.squarespace.com", "squarespace.com"),
    "Shopify": ("cdn.shopify.com",),
    "Webflow": ("webflow.com", "website-files.com"),
    "GoDaddy": ("img1.wsimg.com",),
    "Weebly": ("weebly.com",),
    "Duda": ("multiscreensite.com", "dudaone.com"),
    "Framer": ("framerusercontent.com",),
    "ProSites": ("prosites.com",),
}

ANALYTICS = {
    "Google Analytics": ("googletagmanager.com/gtag/js", "google-analytics.com"),
    "Google Tag Manager": ("googletagmanager.com/gtm.js",),
    "Meta Pixel": ("connect.facebook.net/en_us/fbevents.js", "fbevents.js"),
    "Hotjar": ("static.hotjar.com",),
}

SOCIAL = {
    "facebook": r"facebook\.com/(?!sharer|share\.php|dialog|plugins|tr\b|tr\?)[\w.\-/%]+",
    "instagram": r"instagram\.com/(?!p/|explore)[\w.\-]+",
    "linkedin": r"linkedin\.com/(company|in)/[\w.\-%]+",
    "x": r"(?:twitter|x)\.com/(?!intent|share|home)[\w]+",
    "youtube": r"youtube\.com/(channel/|c/|@|user/)[\w.\-]+",
    "tiktok": r"tiktok\.com/@[\w.\-]+",
    "yelp": r"yelp\.com/biz/[\w\-]+",
}

EMAIL = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", re.IGNORECASE)
# Addresses that are never a business's own contact (tracking, placeholders, image names).
EMAIL_JUNK = re.compile(
    r"(\.(png|jpe?g|gif|svg|webp)$|sentry|wixpress|example\.(com|org)|domain\.com|email\.com|yourdomain|"
    r"@2x|godaddy\.com|squarespace\.com|wordpress\.(com|org)|noreply|no-reply)",
    re.IGNORECASE,
)
US_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")
COPYRIGHT_YEAR = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.IGNORECASE)

# Words in link text or URLs that point at pages worth reading.
PAGE_HINTS = {
    "contact": ("contact", "reach-us", "get-in-touch", "location"),
    "faq": ("faq", "frequently-asked", "questions"),
    "pricing": ("pricing", "prices", "fees", "rates", "cost", "insurance", "financing", "payment"),
    "booking": ("book", "appointment", "schedule", "request"),
    "about": ("about", "team", "our-practice", "meet"),
}
BOOKING_TEXT = re.compile(
    r"\b(book (an |your )?(appointment|online|now|a visit)|request (an )?appointment|schedule (an |your )?(appointment|visit|now|online))\b",
    re.IGNORECASE,
)
FAQ_TEXT = re.compile(r"\b(faq|frequently asked questions)\b", re.IGNORECASE)


def _has(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(n in haystack for n in needles)


def vendors(haystack: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    return sorted(name for name, needles in table.items() if _has(haystack, needles))


@dataclass
class PageSignals:
    url: str
    title: str = ""
    description: str = ""
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    socials: dict[str, str] = field(default_factory=dict)
    chat_vendors: set[str] = field(default_factory=set)
    booking_vendors: set[str] = field(default_factory=set)
    booking_cta: bool = False
    form_vendors: set[str] = field(default_factory=set)
    has_form: bool = False
    faq: bool = False
    cms: set[str] = field(default_factory=set)
    analytics: set[str] = field(default_factory=set)
    viewport: bool = False
    copyright_year: int | None = None
    links: dict[str, list[str]] = field(default_factory=dict)  # hint -> internal URLs
    business_name: str = ""  # from schema.org structured data, the most reliable name
    address: str = ""


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw.strip()


def same_site(url: str, base_host: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.") == base_host.removeprefix("www.")


OBFUSCATED_EMAIL = re.compile(
    r"([a-z0-9._%+\-]+)\s*[\[(]\s*at\s*[\])]\s*([a-z0-9\-]+(?:\s*[\[(]\s*dot\s*[\])]\s*[a-z0-9\-]+)+)", re.IGNORECASE
)


def decode_cloudflare_email(hex_string: str) -> str | None:
    """Cloudflare's "email protection" stores addresses XOR-ed with the first byte."""
    try:
        data = bytes.fromhex(hex_string)
    except ValueError:
        return None
    if len(data) < 2:
        return None
    return bytes(b ^ data[0] for b in data[1:]).decode("utf-8", "ignore")


def hidden_emails(soup: BeautifulSoup, text: str) -> set[str]:
    found: set[str] = set()
    for tag in soup.select("[data-cfemail]"):
        found.add(decode_cloudflare_email(tag["data-cfemail"]) or "")
    for a in soup.find_all("a", href=True):
        if "/cdn-cgi/l/email-protection#" in a["href"]:
            found.add(decode_cloudflare_email(a["href"].split("#", 1)[1]) or "")
    for user, rest in OBFUSCATED_EMAIL.findall(text):
        domain = re.sub(r"\s*[\[(]\s*dot\s*[\])]\s*", ".", rest, flags=re.IGNORECASE)
        found.add(f"{user}@{domain}")
    return {e.lower() for e in found if EMAIL.fullmatch(e or "") and not EMAIL_JUNK.search(e)}


BUSINESS_TYPES = re.compile(
    r"business|dentist|medical|clinic|physician|organization|store|restaurant|"
    r"service|office|practice|salon|spa|attorney|legal|contractor|agent",
    re.IGNORECASE,
)


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "publisher", "provider", "organizer"):
            if key in node:
                yield from _walk(node[key])


def structured_data(soup: BeautifulSoup) -> list[dict]:
    """schema.org entities from JSON-LD blocks that describe a business."""
    found = []
    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.IGNORECASE)}):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        for node in _walk(data):
            kinds = node.get("@type")
            kinds = " ".join(kinds) if isinstance(kinds, list) else str(kinds or "")
            if BUSINESS_TYPES.search(kinds):
                found.append(node)
    return found


def apply_structured_data(s: PageSignals, soup: BeautifulSoup) -> None:
    for node in structured_data(soup):
        name = node.get("name")
        if isinstance(name, str) and name.strip() and not s.business_name:
            s.business_name = name.strip()[:150]
        for key in ("email",):
            email = str(node.get(key) or "").lower().removeprefix("mailto:").strip()
            if EMAIL.fullmatch(email) and not EMAIL_JUNK.search(email):
                s.emails.add(email)
        phone = node.get("telephone")
        if isinstance(phone, str) and re.search(r"\d{3}", phone):
            s.phones.add(normalize_phone(phone))
        same_as = node.get("sameAs") or []
        for link in same_as if isinstance(same_as, list) else [same_as]:
            for social, pattern in SOCIAL.items():
                if social not in s.socials and isinstance(link, str) and re.search(pattern, link, re.IGNORECASE):
                    s.socials[social] = link.split("?")[0]
        addr = node.get("address")
        if isinstance(addr, dict) and not s.address:
            parts = [addr.get(k) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")]
            s.address = ", ".join(str(x).strip() for x in parts if x)


def analyze(url: str, html: str) -> PageSignals:
    s = PageSignals(url=url)
    soup = BeautifulSoup(html, "html.parser")
    low = html.lower()

    if soup.title and soup.title.string:
        s.title = soup.title.string.strip()[:200]
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)})
    if meta and meta.get("content"):
        s.description = meta["content"].strip()[:300]
    s.viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.IGNORECASE)}) is not None

    s.chat_vendors = set(vendors(low, CHAT_VENDORS))
    s.booking_vendors = set(vendors(low, BOOKING_VENDORS))
    s.form_vendors = set(vendors(low, FORM_VENDORS))
    s.cms = set(vendors(low, CMS))
    s.analytics = set(vendors(low, ANALYTICS))

    for form in soup.find_all("form"):
        fields = " ".join(
            (i.get("type") or "") + " " + (i.get("name") or "") for i in form.find_all(["input", "textarea"])
        ).lower()
        if form.find("textarea") or "email" in fields:
            s.has_form = True
            break
    s.has_form = s.has_form or bool(s.form_vendors)

    text = soup.get_text(" ", strip=True)
    s.booking_cta = bool(BOOKING_TEXT.search(text))
    s.faq = bool(FAQ_TEXT.search(text)) and ("?" in text)

    years = [int(y) for y in COPYRIGHT_YEAR.findall(text) if 1995 <= int(y) <= 2100]
    s.copyright_year = max(years) if years else None

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low_href = href.lower()
        if low_href.startswith("mailto:"):
            # Links like "mailto:%20office@..." carry encoded spaces.
            email = unquote(low_href[7:].split("?")[0]).strip()
            if EMAIL.fullmatch(email) and not EMAIL_JUNK.search(email):
                s.emails.add(email)
            continue
        if low_href.startswith("tel:"):
            s.phones.add(normalize_phone(href[4:]))
            continue
        absolute = urljoin(url, href)
        for name, pattern in SOCIAL.items():
            if name not in s.socials and re.search(pattern, absolute, re.IGNORECASE):
                s.socials[name] = absolute.split("?")[0]
        if not same_site(absolute, urlparse(url).hostname or ""):
            continue
        label = (a.get_text(" ", strip=True) + " " + low_href).lower()
        for hint, words in PAGE_HINTS.items():
            if any(w in label for w in words):
                s.links.setdefault(hint, [])
                clean = absolute.split("#")[0]
                if clean not in s.links[hint]:
                    s.links[hint].append(clean)

    for match in EMAIL.findall(text):
        email = match.lower().strip(".")
        if not EMAIL_JUNK.search(email):
            s.emails.add(email)
    s.emails |= hidden_emails(soup, text)
    apply_structured_data(s, soup)
    if not s.business_name:
        og = soup.find("meta", attrs={"property": "og:site_name"})
        if og and og.get("content", "").strip():
            s.business_name = og["content"].strip()[:150]
    if not s.phones:
        for match in US_PHONE.findall(text)[:3]:
            s.phones.add(normalize_phone(match))
    return s
