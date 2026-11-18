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
DAY_OF_YEAR = NOW.timetuple().tm_yday

# 1. Haal passage_id op via YouVersion API
req = urllib.request.Request(
    f"https://api.youversion.com/v1/verse_of_the_days/{DAY_OF_YEAR}",
    headers={"X-YVP-App-Key": APP_KEY, "User-Agent": "Mozilla/5.0"}
)
with urllib.request.urlopen(req) as resp:
    votd = json.loads(resp.read().decode())
    passage_id = votd["passage_id"]  # bijv. "ISA.12.2" of "JHN.3.16-17"

# Bepaal exacte USFM verse-IDs (bijv. "JHN.3.16-17" -> {"JHN.3.16", "JHN.3.17"})
parts = passage_id.split(".")
book_chap = f"{parts[0]}.{parts[1]}"
verse_part = parts[2]
if "-" in verse_part:
    start_v, end_v = map(int, verse_part.split("-"))
    target_usfms = {f"{book_chap}.{v}" for v in range(start_v, end_v + 1)}
else:
    target_usfms = {passage_id}

# 2. Haal HSV (1990) pagina op
url = f"https://www.bible.com/nl/bible/1990/{passage_id}.HSV"
html_req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(html_req) as resp:
    soup = BeautifulSoup(resp.read().decode(), "html.parser")

next_data = json.loads(soup.find("script", id="__NEXT_DATA__").string)
reference = next_data["props"]["pageProps"]["reference"]["human"]

# Filter alleen de doelverzen en verwijder versnummers/voetnoten
verses_text = []
for el in soup.select("[data-usfm]"):
    usfm_list = el.get("data-usfm", "").split("+")
    if any(u in target_usfms for u in usfm_list):
        for sup in el.select("[data-verse-number], .label, .note"):
            sup.decompose()
        verses_text.append(el.get_text(" ", strip=True))

clean_text = re.sub(r"\s+", " ", " ".join(verses_text)).strip()

# 3. Genereer RSS 2.0 XML
os.makedirs("docs", exist_ok=True)
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "YouVersion Tekst van de Dag (HSV)"
ET.SubElement(channel, "link").text = url
ET.SubElement(channel, "description").text = "Dagelijkse bijbeltekst in de Herziene Statenvertaling"
ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(NOW)

item = ET.SubElement(channel, "item")
ET.SubElement(item, "title").text = f"{reference} (HSV)"
ET.SubElement(item, "link").text = url
ET.SubElement(item, "description").text = clean_text
ET.SubElement(item, "pubDate").text = email.utils.format_datetime(NOW)
ET.SubElement(item, "guid", isPermaLink="false").text = f"{NOW.strftime('%Y-%m-%d')}-{passage_id}"

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
tree.write("docs/feed.xml", encoding="utf-8", xml_declaration=True)
print(f"Gegenereerd: {reference} - {clean_text}")
