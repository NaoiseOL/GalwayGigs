import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def normalise_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
    return title


def normalise_date(date: str) -> str:
    date = date.strip()
    for fmt in (
        "%a %b %d %Y",
        "%Y-%m-%d",
        "%d %B %Y",
        "%B %d, %Y",
        "%d/%m/%Y",
        "%a %d %b %Y",
    ):
        try:
            return datetime.strptime(date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date.lower().strip()


def dedupe_gigs(gigs: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for gig in gigs:
        key = (
            normalise_title(gig.get("artist", "")),
            normalise_date(gig.get("date", "")),
        )
        if key not in seen:
            seen.add(key)
            unique.append(gig)
    return unique


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

def SongkickScrape():
    gigs = []
    URL = "https://www.songkick.com/metro-areas/29315-ireland-galway"
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, "html.parser")

    for event in soup.select("li.event-listings-element"):
        date = event.get("title", "")

        artist_tag = event.select_one("p.artists strong")
        artist = artist_tag.get_text(strip=True) if artist_tag else ""

        venue_tag = event.select_one("a.venue-link")
        venue = venue_tag.get_text(strip=True) if venue_tag else ""

        city_tag = event.select_one("span.city-name")
        city = city_tag.get_text(strip=True) if city_tag else ""

        link_tag = event.select_one("a.event-link")
        link = "https://www.songkick.com" + link_tag["href"] if link_tag else ""

        gigs.append({"date": date, "artist": artist, "venue": venue, "city": city, "link": link})

    return gigs


def MonroesScrape():
    gigs = []
    URL = "https://monroes.ie/collections/live"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    page = requests.get(URL, headers=headers)
    soup = BeautifulSoup(page.content, "html.parser")

    seen_hrefs = set()
    for a in soup.select("a[href^='/products/']"):
        href = a.get("href", "")
        title = a.get_text(strip=True)

        if not title or href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        date = ""
        for sibling in a.next_siblings:
            if sibling.name == "h6":
                date = sibling.get_text(strip=True)
                break

        gigs.append({
            "artist": title,
            "date":   date,
            "venue":  "Monroe's Live",
            "city":   "Galway",
            "link":   "https://monroes.ie" + href,
        })

    return gigs


def RoisinDubhScrape():
    """
    Roisin Dubh loads events via authenticated API calls.
    We use Playwright to intercept those JSON responses as they fire,
    then parse them directly — no HTML scraping needed.

    API returns two types of responses:
    1. Months list: { success, total, results: [{month, year}, ...] }
    2. Events per month: { success, total, results: [{id, pagetitle, alias,
                           event_date_time, name, prices, ...}, ...] }
    """
    gigs = []
    api_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            # Capture any JSON response from the roisindubh domain
            if "roisindubh.net" in response.url and response.status == 200:
                try:
                    data = response.json()
                    # Only keep responses that have an event results list
                    if isinstance(data.get("results"), list):
                        for item in data["results"]:
                            # Month-list items only have 'month' and 'year' — skip them
                            if "pagetitle" in item:
                                api_results.append(item)
                except Exception:
                    pass

        page.on("response", handle_response)
        page.goto("https://roisindubh.net/listings/", wait_until="networkidle", timeout=30000)
        browser.close()

    for event in api_results:
        title = event.get("pagetitle", "").strip()
        alias = event.get("alias", "")
        raw_date = event.get("event_date_time", "")  # e.g. "2026-06-28T20:00:00"
        venue = event.get("name", "Róisín Dubh").strip()

        # Parse ISO datetime -> clean date string
        try:
            dt = datetime.fromisoformat(raw_date)
            date = dt.strftime("%Y-%m-%d")
        except Exception:
            date = raw_date

        link = f"https://roisindubh.net/listings/{alias}" if alias else "https://roisindubh.net/listings/"

        if title:
            gigs.append({
                "artist": title,
                "date":   date,
                "venue":  venue,
                "city":   "Galway",
                "link":   link,
            })

    return gigs


def EventbriteGalwayScrape():
    gigs = []
    URL = "https://www.eventbrite.ie/d/ireland--galway/music/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)

        try:
            page.wait_for_selector("a[href*='eventbrite.ie/e/']", timeout=10000)
        except Exception:
            pass

        content = page.content()
        browser.close()

    soup = BeautifulSoup(content, "html.parser")

    seen = set()
    for card in soup.select("a[href*='eventbrite.ie/e/']"):
        href = card.get("href", "").split("?")[0]
        if not href or href in seen:
            continue
        seen.add(href)

        container = card.find_parent("li") or card.find_parent("article") or card

        title_tag = container.select_one("h2, h3, .event-card__title, [class*='title']")
        date_tag  = container.select_one("time, p, .event-card__formatted-date, [class*='date']")
        venue_tag = container.select_one(".event-card__venue, [class*='venue'], [class*='location']")

        title = title_tag.get_text(strip=True) if title_tag else ""
        date  = date_tag.get_text(strip=True)  if date_tag  else ""
        venue = venue_tag.get_text(strip=True) if venue_tag else ""

        if title:
            gigs.append({
                "artist": title,
                "date":   date,
                "venue":  venue,
                "city":   "Galway",
                "link":   href,
            })

    return gigs


# ---------------------------------------------------------------------------
# Aggregate entry point
# ---------------------------------------------------------------------------

def get_all_gigs() -> list[dict]:
    all_gigs = (
        SongkickScrape()
        + MonroesScrape()
        + RoisinDubhScrape()
        + EventbriteGalwayScrape()
    )
    return dedupe_gigs(all_gigs)