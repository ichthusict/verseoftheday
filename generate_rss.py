import datetime
import email.utils
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

APP_KEY = os.environ["YOUVERSION_APP_KEY"]
NOW = datetime.datetime.now(datetime.timezone.utc)
FEED_URL = "https://ichthusict.github.io/verseoftheday/feed.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

def fetch_votd_item(target_dt: datetime.datetime) -> dict:
    day_of_year = target_dt.timetuple().tm_yday
    req = urllib.request.Request(
        f"https://api.youversion.com/v1/verse_of_the_days/{day_of_year}",
        headers={"X-YVP-App-Key": APP_KEY, "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as resp:
        passage_id = json.loads(resp.read().decode())["passage_id"]

    url = f"https://www.bible.com/nl/bible/1990/{passage_id}.HSV"
    html_req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(html_req) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    reference = passage_id
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        reference = og_title["content"].split("|")[0].split(" - ")[0]
    elif soup.title and soup.title.string:
        reference = soup.title.string.split("|")[0].split(" - ")[0]

    # Verwijder 'HSV' en lege haakjes '()'
    reference = re.sub(r"\(\s*HSV\s*\)|\bHSV\b", "", reference)
    reference = re.sub(r"\(\s*\)", "", reference).strip()

    clean_text = ""
    for meta_attr in [{"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}]:
        tag = soup.find("meta", attrs=meta_attr)
        if tag and tag.get("content"):
            candidate = tag["content"].strip()
            if candidate and "YouVersion" not in candidate and len(candidate) > 10:
                clean_text = candidate
                break

    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    if not clean_text:
        raise RuntimeError(f"Geen verstekst gevonden voor {passage_id} op {url}")

    return {
        "title": f"{reference} (HSV)",
        "link": url,
        "description": clean_text,
        "pubDate": email.utils.format_datetime(target_dt),
        "guid": f"{target_dt.strftime('%Y-%m-%d')}-{passage_id}",
    }

# Bouw lijst van de afgelopen 3 dagen op (zodat er altijd >1 <item> in de feed staat)
items = [fetch_votd_item(NOW - datetime.timedelta(days=offset)) for offset in range(3)]

os.makedirs("docs", exist_ok=True)
open("docs/.nojekyll", "w").close()

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "YouVersion Tekst van de Dag (HSV)"
ET.SubElement(channel, "link").text = items[0]["link"]
ET.SubElement(channel, "description").text = "Dagelijkse bijbeltekst in de Herziene Statenvertaling"
ET.SubElement(channel, "language").text = "nl"
ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(NOW)
ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {
    "href": FEED_URL,
    "rel": "self",
    "type": "application/rss+xml",
})

for it in items:
    item_el = ET.SubElement(channel, "item")
    ET.SubElement(item_el, "title").text = it["title"]
    ET.SubElement(item_el, "link").text = it["link"]
    ET.SubElement(item_el, "description").text = it["description"]
    ET.SubElement(item_el, "pubDate").text = it["pubDate"]
    ET.SubElement(item_el, "guid", isPermaLink="false").text = it["guid"]

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
tree.write("docs/feed.xml", encoding="utf-8", xml_declaration=True)
print(f"Gegenereerd ({len(items)} items): {items[0]['title']} - {items[0]['description']}")
