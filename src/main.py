"""Apify Actor entry: read the input, audit every website, push one result per site."""

from __future__ import annotations

import asyncio

from apify import Actor

from .audit import audit_site, make_client

CHARGE_EVENT = "site-audited"


class InputError(Exception):
    pass


# Fields kept from a Google Maps Scraper dataset, so the output stays one row per business.
MAPS_FIELDS = {
    "title": "name",
    "phone": "mapsPhone",
    "address": "address",
    "categoryName": "category",
    "totalScore": "rating",
    "reviewsCount": "reviewsCount",
    "url": "mapsUrl",
}


async def collect_targets(actor_input: dict) -> list[tuple[str, dict]]:
    targets: list[tuple[str, dict]] = []
    for item in actor_input.get("websites") or []:
        url = item.get("url") if isinstance(item, dict) else item
        if url:
            targets.append((url, {}))
    dataset_id = (actor_input.get("datasetId") or "").strip()
    if dataset_id:
        try:
            dataset = await Actor.open_dataset(id=dataset_id)
            async for item in dataset.iterate_items():
                site = item.get("website")
                if site:
                    targets.append((site, {new: item.get(old) for old, new in MAPS_FIELDS.items() if item.get(old)}))
        except Exception as exc:  # wrong ID or no access: say so instead of a stack trace
            raise InputError(f"Could not read dataset {dataset_id}: {exc}") from exc
    seen: set[str] = set()
    unique = []
    for url, extra in targets:
        key = url.strip().lower().rstrip("/").removeprefix("https://").removeprefix("http://").removeprefix("www.")
        if key and key not in seen:
            seen.add(key)
            unique.append((url, extra))
    limit = actor_input.get("maxSites")
    return unique[:limit] if limit else unique


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        try:
            targets = await collect_targets(actor_input)
        except InputError as exc:
            await Actor.fail(status_message=str(exc))
            return
        if not targets:
            await Actor.fail(status_message="Add websites or a Google Maps dataset ID.")
            return
        max_pages = max(1, min(int(actor_input.get("maxPagesPerSite", 4)), 8))
        proxy_url = None
        if actor_input.get("proxyConfiguration"):
            proxy = await Actor.create_proxy_configuration(actor_proxy_input=actor_input["proxyConfiguration"])
            proxy_url = await proxy.new_url() if proxy else None

        semaphore = asyncio.Semaphore(max(1, min(int(actor_input.get("maxConcurrency", 10)), 30)))
        done = 0
        stop = asyncio.Event()

        async with make_client(proxy=proxy_url) as client:

            async def run(url: str, extra: dict) -> None:
                nonlocal done
                if stop.is_set():
                    return
                async with semaphore:
                    if stop.is_set():
                        return
                    result = await audit_site(client, url, max_pages=max_pages, extra=extra)
                # Only successful audits are charged; unreachable sites are listed for free.
                charged = await Actor.push_data(result, charged_event_name=CHARGE_EVENT if result["ok"] else None)
                done += 1
                if result["ok"] and charged.event_charge_limit_reached:
                    stop.set()
                if done % 10 == 0:
                    await Actor.set_status_message(f"Audited {done} of {len(targets)} websites")

            await asyncio.gather(*(run(u, e) for u, e in targets))
        await Actor.set_status_message(
            f"Done: {done} of {len(targets)} websites" + (" (stopped at your spending limit)" if stop.is_set() else "")
        )
