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
    passage_id = votd["passage_id"]  # bijv. "ISA.40.8"

# 2. Haal HSV (1990) verspagina op
url = f"https://www.bible.com/nl/bible/1990/{passage_id}.HSV"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}
html_req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(html_req) as resp:
    html = resp.read().decode("utf-8", errors="replace")

soup = BeautifulSoup(html, "html.parser")

# Referentie uit og:title of <title> (bijv. "Jesaja 40:8 HSV")
reference = passage_id
og_title = soup.find("meta", property="og:title")
if og_title and og_title.get("content"):
    reference = og_title["content"].split("|")[0].split(" - ")[0].replace("HSV", "").strip()
elif soup.title and soup.title.string:
    reference = soup.title.string.split("|")[0].split(" - ")[0].replace("HSV", "").strip()

# Methode A: Haal verstekst direct uit og:description / meta description
clean_text = ""
for meta_attr in [{"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}]:
    tag = soup.find("meta", attrs=meta_attr)
    if tag and tag.get("content"):
        candidate = tag["content"].strip()
        # Negeer generieke YouVersion-omschrijvingen
        if candidate and "YouVersion" not in candidate and len(candidate) > 10:
            clean_text = candidate
            break

# Methode B (Fallback): Zoek in Next.js App Router RSC payload (__next_f)
if not clean_text:
    rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
    combined_rsc = "".join(rsc_chunks).encode("utf-8").decode("unicode_escape", errors="ignore")
    # Zoek naar JSON-velden met "text" of "content" rondom passage_id
    m = re.search(r'"content"\s*:\s*"([^"]{15,500})"', combined_rsc)
    if m:
        clean_text = re.sub(r"<[^>]+>", " ", m.group(1))

clean_text = re.sub(r"\s+", " ", clean_text).strip()

if not clean_text:
    meta_dump = [str(m) for m in soup.find_all("meta")]
    print("DEBUG META TAGS:", "\n".join(meta_dump[:15]))
    raise RuntimeError(f"Geen verstekst gevonden voor {passage_id} op {url}")

# 3. Genereer RSS 2.0 XML + .nojekyll
os.makedirs("docs", exist_ok=True)
open("docs/.nojekyll", "w").close()

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
