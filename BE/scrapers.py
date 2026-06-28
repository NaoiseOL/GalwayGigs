import requests
from bs4 import BeautifulSoup

URL = "https://www.songkick.com/metro-areas/29315-ireland-galway"
page = requests.get(URL)

soup = BeautifulSoup(page.content, "html.parser")

gigs = []

event_elements = soup.select("li.event-listings-element")

for event in event_elements:
    date = event.get("title", "")

    artist_tag = event.select_one("p.artists strong")
    artist = artist_tag.get_text(strip=True) if artist_tag else ""

    venue_tag = event.select_one("a.venue-link")
    venue = venue_tag.get_text(strip=True) if venue_tag else ""

    city_tag = event.select_one("span.city-name")
    city = city_tag.get_text(strip=True) if city_tag else ""

    link_tag = event.select_one("a.event-link")
    link = "https://www.songkick.com" + link_tag["href"] if link_tag else ""

    gigs.append({
        "date": date,
        "artist": artist,
        "venue": venue,
        "city": city,
        "link": link,
    })

for gig in gigs:
    print(gig)