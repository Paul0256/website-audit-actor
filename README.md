# Local Business Website Audit & Contacts

Turn a list of business websites into **qualified leads**: for every site you get the
contact details **and what the business is missing**, so you know what to pitch before
you write a single email.

Built for agencies and freelancers who sell **AI chat assistants, online booking,
websites, SEO or automation** to local businesses: dentists, clinics, salons, gyms,
law firms, contractors.

## What you get for every website

| Field | Example |
|---|---|
| `emails`, `phones`, `socials` | `office@brightsmile.com`, `(208) 555-0142`, Facebook, Instagram, Yelp, LinkedIn |
| `hasLiveChat`, `chatVendors` | `false` / `["Intercom"]`: 25+ vendors (Intercom, Drift, Tawk.to, LiveChat, Zendesk, Tidio, HubSpot, Podium, Birdeye, Weave…) |
| `hasOnlineBooking`, `bookingVendors` | `true` / `["Zocdoc"]`: 20+ vendors (Calendly, Acuity, Square, Zocdoc, NexHealth, Jane, Vagaro, Mindbody…) |
| `hasContactForm`, `hasFaq`, `hasPricingPage` | with the page URLs |
| `https`, `mobileFriendly`, `copyrightYear` | is the site secure, phone-ready, maintained? |
| `cms`, `analytics` | WordPress, Wix, Squarespace, Shopify… / Google Analytics, GTM, Meta Pixel |
| **`opportunities`** | `["No live chat or AI assistant", "No online booking", "Footer copyright is from 2019"]` |
| **`opportunityScore`** | 0–100: how much there is to offer this business |
| **`pitchAngle`** | *"Bright Smile Dental: visitors with a question after hours have no one to ask, so they call or leave."* |

Sort by `opportunityScore`, filter by `hasLiveChat = false`, and your outreach list is ready.

## Use it with Google Maps Scraper

1. Run **Google Maps Scraper** for e.g. "dentist in Boise, ID".
2. Paste its **dataset ID** into this Actor's *Google Maps Scraper dataset ID* field.
3. Every business with a website is audited, and its name, address, category and rating
   stay in the same row.

Or paste any list of websites (with or without `https://`).

## How it works

- Reads the homepage and up to 3 key pages it links to: contact, FAQ, pricing/insurance,
  booking, about (set *Pages per website*, 1–8).
- Plain HTTP requests, no browser: fast and cheap. Chat and booking widgets are detected
  from the scripts and links in the page.
- Unreachable sites are listed with the reason and are **not charged**.

## Pricing

Pay per result: you are charged only for websites that were audited successfully.

## Limits

- Sites built entirely in JavaScript may show fewer emails than a browser would.
- A widget loaded only after a click or by a tag manager can be missed.
- Only public pages are read. Use the results according to the laws that apply to you
  (e.g. CAN-SPAM, GDPR) when contacting businesses.

## Output example

```json
{
  "name": "Bright Smile Dental",
  "domain": "brightsmileboise.com",
  "emails": ["frontdesk@brightsmileboise.com", "office@brightsmileboise.com"],
  "phones": ["(208) 555-0142"],
  "hasLiveChat": false,
  "hasOnlineBooking": false,
  "hasFaq": true,
  "hasContactForm": true,
  "cms": ["WordPress"],
  "copyrightYear": 2019,
  "opportunities": ["No live chat or AI assistant", "No online booking", "Footer copyright is from 2019"],
  "opportunityScore": 50,
  "pitchAngle": "Bright Smile Dental: visitors with a question after hours have no one to ask, so they call or leave."
}
```

Questions or a custom version (other signals, AI-written first lines, CRM export)?
Open an issue on this Actor's page.
