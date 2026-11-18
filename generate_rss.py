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

def extract_api_image(votd_json: dict) -> str:
    # Zoek recursief naar een afbeelding-URL in de YouVersion VOTD JSON-respons
    for key in ("image_url", "image", "images", "media"):
        val = votd_json.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
        if isinstance(val, dict):
            for sub in ("url", "large", "medium", "default", "1280x1280", "1080x1080"):
                if isinstance(val.get(sub), str) and val[sub].startswith("http"):
                    return val[sub]
    # Fallback regex voor eventuele geneste image-URLs in het JSON-object
    m = re.search(r'https://[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?', json.dumps(votd_json))
    return m.group(0) if m else ""

def fetch_votd_item(target_dt: datetime.datetime) -> dict:
    day_of_year = target_dt.timetuple().tm_yday
    req = urllib.request.Request(
        f"https://api.youversion.com/v1/verse_of_the_days/{day_of_year}",
        headers={"X-YVP-App-Key": APP_KEY, "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req) as resp:
        votd = json.loads(resp.read().decode())
        passage_id = votd["passage_id"]
        image_url = extract_api_image(votd)

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

    # Fallback afbeelding uit og:image van bible.com als de API er geen meegaf
    if not image_url:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content", "").startswith("http"):
            image_url = og_img["content"]

    return {
        "title": clean_text,
        "link": url,
        "description": f"{reference} (HSV)",
        "image": image_url,
        "pubDate": email.utils.format_datetime(target_dt),
        "guid": f"{target_dt.strftime('%Y-%m-%d')}-{passage_id}",
    }

items = [fetch_votd_item(NOW - datetime.timedelta(days=offset)) for offset in range(3)]

os.makedirs("docs", exist_ok=True)
open("docs/.nojekyll", "w").close()

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("media", "http://search.yahoo.com/mrss/")
rss = ET.Element("rss", {"version": "2.0"})
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
    if it["image"]:
        ET.SubElement(item_el, "enclosure", {
            "url": it["image"],
            "length": "0",
            "type": "image/jpeg",
        })
        ET.SubElement(item_el, "{http://search.yahoo.com/mrss/}content", {
            "url": it["image"],
            "medium": "image",
        })

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
tree.write("docs/feed.xml", encoding="utf-8", xml_declaration=True)
print(f"Gegenereerd: {items[0]['description']} | Image: {items[0]['image']}")
