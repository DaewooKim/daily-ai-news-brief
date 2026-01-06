
import feedparser
import time
import datetime

url = "https://techcrunch.com/feed/"
print(f"Fetching {url}...")
feed = feedparser.parse(url)

print(f"Found {len(feed.entries)} entries.")

target_title_snippet = "Groq"

for entry in feed.entries:
    if target_title_snippet.lower() in entry.title.lower():
        print("--- Found Target Article ---")
        print(f"Title: {entry.title}")
        print(f"Link: {entry.link}")
        print(f"Published (Raw): {entry.get('published')}")
        print(f"Published Parsed: {entry.get('published_parsed')}")
        print(f"Updated (Raw): {entry.get('updated')}")
        print(f"Updated Parsed: {entry.get('updated_parsed')}")
        
        if entry.get('published_parsed'):
             dt = datetime.datetime.fromtimestamp(time.mktime(entry.get('published_parsed')))
             print(f"Computed Date: {dt}")
        else:
             print("Computed Date: None (Fallback would occur)")
        break
