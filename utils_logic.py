import feedparser
import datetime
import uuid
import time

def fetch_rss_feed(url):
    """
    Parses an RSS feed and returns a list of entries.
    """
    try:
        feed = feedparser.parse(url)
        return feed.entries
    except Exception as e:
        print(f"Error fetching RSS feed {url}: {e}")
        return []

        print(f"Error fetching RSS feed {url}: {e}")
        return []

import streamlit as st
from openai import OpenAI
from bs4 import BeautifulSoup
import json

def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def process_article_content(title, text, model_name, filter_prompt=None):
    """
    Summarizes and translates the article using OpenAI API.
    Returns (korean_title, korean_summary).
    If filter_prompt is provided and article is not relevant, returns (None, None).
    """
    try:

        api_key = st.secrets.get("OPENAI_API_KEY")
        if not api_key:
            return title, "Error: OPENAI_API_KEY not found in secrets."

        client = OpenAI(api_key=api_key)
        
        # Mapping custom model names
        openai_model = "gpt-4o-mini" # Default fallback
        if "gemini" in model_name.lower():
             return title, "Error: Gemini model support not yet implemented."
        
        if model_name == "chatgpt-5-mini" or model_name == "gpt-5-mini":
            openai_model = "gpt-5-mini"
        else:
            openai_model = model_name

        # Default filter prompt if None
        if not filter_prompt:
             filter_prompt = "Is this article related to Artificial Intelligence, Machine Learning, or LLMs?"

        system_prompt = (
            "You are a helpful assistant. "
            f"First, evaluate if the article matches this criteria: '{filter_prompt}'. "
            "If it DOES NOT match, output JSON: {\"is_relevant\": false}. "
            "If it DOES match: "
            "Translate the news title to Korean. "
            "Provide a concise 4-5 line summary of the article in Korean. "
            "Output strictly in JSON format: {\"is_relevant\": true, \"title\": \"...\", \"summary\": \"...\"}"
        )

        user_prompt = f"Title: {title}\n\nArticle Text:\n{text}"

        def call_ai(model):
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=500,
                response_format={"type": "json_object"}
            )

        try:
            response = call_ai(openai_model)
        except Exception as e:
            # Fallback for gpt-5-mini specific errors or empty content
            print(f"DEBUG: Error with {openai_model}: {e}. Falling back to gpt-4o-mini.")
            openai_model = "gpt-4o-mini"
            response = call_ai(openai_model)

        message = response.choices[0].message
        content = message.content
        finish_reason = response.choices[0].finish_reason
        
        print(f"DEBUG: Model: {openai_model}, Finish Reason: {finish_reason}, Content Len: {len(content) if content else 0}")
        
        if not content or not content.strip():
             # One last try with fallback if not already tried? 
             # For simplicity, if empty here, return error.
             if openai_model != "gpt-4o-mini":
                 print("DEBUG: Empty content. Retrying with gpt-4o-mini.")
                 response = call_ai("gpt-4o-mini")
                 content = response.choices[0].message.content

        if content:
             try:
                 data = json.loads(content)
                 if data.get("is_relevant") is False:
                     print(f"DEBUG: Article '{title}' filtered out as irrelevant.")
                     return None, None
                 
                 return data.get("title", title), data.get("summary", "")
             except json.JSONDecodeError:
                 return title, content # Return raw if JSON fails

        return title, "Error: Empty summary returned by AI."
            
    except Exception as e:
        print(f"Error summarizing with OpenAI: {e}")
        return title, f"Error using AI model: {e}"

def process_news_data(rss_urls, existing_data, model_name="chatgpt-5-mini", days_limit=7, ai_filter_prompt=None, status_callback=None, progress_callback=None):
    """
    Fetches news from RSS URLs.
    - Adds new items.
    - Updates existing items if they have missing or error-state summaries.
    - Filters out items older than days_limit.
    - Uses callbacks for UI updates.
    """
    if status_callback:
        status_callback("Initializing...")
        
    # Create a map of link -> item for easy lookup and update
    existing_items_map = {item['link']: item for item in existing_data}
    new_items_count = 0
    updated_count = 0
    
    current_time_iso = datetime.datetime.now().isoformat()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    now_ts = time.mktime(datetime.datetime.now().timetuple())

    # First pass: Collect all valid entries to calculate total for progress bar
    all_valid_entries = []
    
    if status_callback:
        status_callback("Fetching RSS feeds...")
        
    for url in rss_urls:
        entries = fetch_rss_feed(url)
        for entry in entries:
            link = entry.get('link', '')
            if not link:
                continue
            
            # Date Filter
            published_struct = entry.get('published_parsed') or entry.get('updated_parsed')
            if published_struct:
                published_ts = time.mktime(published_struct)
                # Calculate difference in days
                diff_days = (now_ts - published_ts) / (24 * 3600)
                if diff_days > days_limit:
                    continue
            
            # Add source url to entry for later reference
            entry['source_url'] = url
            all_valid_entries.append(entry)

    total_entries = len(all_valid_entries)
    if status_callback:
        status_callback(f"Found {total_entries} articles within the last {days_limit} days. Starting processing...")
    
    for i, entry in enumerate(all_valid_entries):
        # Update progress
        if progress_callback:
            progress_callback(i / total_entries if total_entries > 0 else 0)
            
        link = entry.get('link')
        original_title = entry.get('title', 'No Title')
        url = entry.get('source_url')

        # Extract best possible text content
        summary_text = entry.get('summary', '') or entry.get('description', '')
        if 'content' in entry:
            c = entry['content']
            if isinstance(c, list) and len(c) > 0:
                summary_text = c[0].get('value', summary_text)
        
        # Clean HTML
        clean_text = clean_html(summary_text)

        # Check if we need to process this item
        should_process = False
        is_new = False
        
        # Heuristic to detect if valid summary is English
        curr_summary = ""
        if link not in existing_items_map:
            is_new = True
            should_process = True
        else:
            # Check if existing item needs repair OR Translation
            curr_item = existing_items_map[link]
            curr_summary = curr_item.get('summary', '')
            
            # Retry if:
            # 1. Empty/Whitespace
            # 2. Error message
            # 3. Starts with English letter (Example: 'T' in 'The...') -> We want Korean
            is_english_summary = (curr_summary and len(curr_summary) > 0 and curr_summary[0].isascii() and "Error" not in curr_summary)
            
            if not curr_summary or not curr_summary.strip() or curr_summary.startswith("Error") or "Error using AI model" in curr_summary or is_english_summary:
                should_process = True
                if status_callback:
                    status_callback(f"Reprocessing: {original_title}")
                print(f"Reprocessing item '{original_title}' (Is English? {is_english_summary})")

        if should_process:
            if not clean_text or len(clean_text) < 20:
                ai_title, ai_summary = original_title, "Content too short to summarize."
                if status_callback:
                    status_callback(f"[SKIP] Content too short: {original_title[:30]}...")
            else:
                # Summarize & Translate
                if status_callback:
                    status_callback(f"[PROCESSING] Analyzing: {original_title}...")
                print(f"Processing item: {original_title}")
                
                ai_title, ai_summary = process_article_content(original_title, clean_text[:4000], model_name, filter_prompt=ai_filter_prompt)

                if ai_title is None and ai_summary is None:
                    # Irrelevant article
                    if status_callback:
                        status_callback(f"[SKIP] Irrelevant (AI Filter): {original_title}")
                    continue
                
                if status_callback:
                     summary_snippet = ai_summary[:50].replace("\n", " ") + "..." if ai_summary else "No summary"
                     status_callback(f"[SUCCESS] Processed: {ai_title}\n  > Summary: {summary_snippet}")

        # Determine Timestamp (Always use feed data if available)
        published_struct = entry.get('published_parsed') or entry.get('updated_parsed')
        if published_struct:
            dt_object = datetime.datetime.fromtimestamp(time.mktime(published_struct))
            item_date_str = dt_object.strftime("%Y-%m-%d")
            item_timestamp_iso = dt_object.isoformat()
        else:
            item_date_str = today_str
            item_timestamp_iso = current_time_iso

        if is_new:
            new_item = {
                "id": str(uuid.uuid4()),
                "date": item_date_str,
                "timestamp": item_timestamp_iso,
                "title": ai_title,
                "source": url,
                "summary": ai_summary,
                "link": link
            }
            existing_items_map[link] = new_item
            new_items_count += 1
            if status_callback and not should_process: # If added but not processed (e.g. short content fallback or something)
                 status_callback(f"[INFO] New item added: {original_title}")
                 
        else:
            # Existing item:
            # 1. Update content IF processed
            if should_process:
                 # Check if filtered out
                 if ai_title is None:
                     # Delete from map? Or just ignore update?
                     pass
                 else:
                     existing_items_map[link]['title'] = ai_title 
                     existing_items_map[link]['summary'] = ai_summary
            
            # 2. ALWAYS update timestamp to match feed (Fix for user issue)
            old_timestamp = existing_items_map[link].get('timestamp', '')
            existing_items_map[link]['timestamp'] = item_timestamp_iso 
            existing_items_map[link]['date'] = item_date_str
            
            # Count update if we re-processed content OR if timestamp changed
            if should_process or old_timestamp != item_timestamp_iso:
                 updated_count += 1
                 if status_callback and old_timestamp != item_timestamp_iso:
                     status_callback(f"[info] Timestamp updated for: {original_title}")

    # Final progress update
    if progress_callback:
        progress_callback(1.0)
    if status_callback:
        status_callback(f"Completed! New: {new_items_count}, Updated: {updated_count}")
    
    # Reconstruct list from map values and sort
    updated_data = list(existing_items_map.values())
    updated_data.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Return total changes (new + updated) so UI knows to refresh
    total_changes = new_items_count + updated_count
    
    return updated_data, total_changes

