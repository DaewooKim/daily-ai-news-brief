import streamlit as st
import pandas as pd
import datetime
import threading
import time
import plotly.express as px
from utils_github import load_data_from_github, save_data_to_github, load_logs_from_github
from utils_logic import process_news_data

# Page Configuration
st.set_page_config(
    page_title="Daily AI News Brief",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def rerun():
    """
    Wrapper for st.rerun() to support older Streamlit versions.
    """
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


# Constants & Defaults
DEFAULT_CONFIG = {
    "rss_urls": [
        "https://feeds.feedburner.com/TechCrunch/startups", # Example
        "https://www.theverge.com/rss/index.xml" # Example
    ],
    "update_interval_minutes": 180,
    "model": "gpt-4o-mini",
    "days_to_scrape": 3,
    "ai_filter_prompt": "Is this article related to Artificial Intelligence, Machine Learning, or LLMs?"
}
DEFAULT_STATS = {
    "daily_visits": {},
    "scraped_count": {}
}
DEFAULT_NEWS_DATA = []

# --- Session State Initialization ---
if 'is_admin' not in st.session_state:
    st.session_state['is_admin'] = False

# --- Helper Functions ---
def load_all_data():
    """Loads all necessary data from GitHub."""
    news_data = load_data_from_github("news_data.json", DEFAULT_NEWS_DATA)
    config = load_data_from_github("config.json", DEFAULT_CONFIG)
    stats = load_data_from_github("stats.json", DEFAULT_STATS)
    return news_data, config, stats

def update_stats_visit(stats):
    """Updates daily visit stats."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today not in stats["daily_visits"]:
        stats["daily_visits"][today] = 0
    stats["daily_visits"][today] += 1
    save_data_to_github("stats.json", stats, f"Update stats: Visit {today}")
    return stats

# --- Background Scheduler ---
def run_scheduler():
    """
    Background loop to check for updates and perform auto-scraping via remote logging.
    """
    import datetime
    from utils_github import save_logs_to_github
    
    print("DEBUG: Scheduler loop started.")
    while True:
        try:
            # We re-fetch config inside the loop to catch updates
            config = load_data_from_github("config.json", DEFAULT_CONFIG)
            stats = load_data_from_github("stats.json", {"daily_visits": {}, "scraped_count": {}})
            
            enable_auto = config.get("enable_auto_scrape", False)
            interval_sec = config.get("update_interval_minutes", 180) * 60
            
            # Check last run time
            last_run_str = stats.get("last_auto_scrape", "2000-01-01T00:00:00")
            last_run = datetime.datetime.fromisoformat(last_run_str)
            time_since_run = (datetime.datetime.now() - last_run).total_seconds()
            
            print(f"DEBUG: Scheduler Check - Enable: {enable_auto}, Last Run: {last_run_str}, Next Due: {interval_sec - time_since_run:.0f}s")

            if enable_auto and time_since_run > interval_sec:
                # START AUTO-SCRAPE
                print("Scheduler: Starting Auto-Scrape...")

                
                # --- Remote Logging Helper ---
                log_buffer = []
                def remote_logger(msg):
                    print(f"Auto-Scrape: {msg}")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_buffer.append({"timestamp": timestamp, "message": msg})
                    
                    # Flush to GitHub every 5 messages or if critical
                    if len(log_buffer) >= 5 or "Completed" in msg or "Error" in msg:
                        current_logs = {"last_updated": timestamp, "status": "running", "logs": log_buffer[-20:]} # Keep last 20 in buffer for now
                        # Ideally we'd append, but for simplicity we just show recent activity in this demo file
                        save_logs_to_github(current_logs)
                        # We might want to clear buffer partially or keep accumulating?
                        # For a "live view", recreating the whole file with recent logs is safer for concurrency than appending to a massive file.
                
                remote_logger("Starting automatic background collection...")
                
                try:
                    # 1. Load current data
                    news_data = load_data_from_github("news_data.json", [])
                    
                    # 2. Run Processing
                    rss_urls = config.get("rss_urls", DEFAULT_CONFIG["rss_urls"])
                    days_limit = config.get("days_to_scrape", 3)
                    model_name = config.get("openai_model", "gpt-4o-mini")
                    filter_prompt = config.get("ai_filter_prompt", None)
                    
                    updated_news, changes = process_news_data(
                        rss_urls, 
                        news_data, 
                        model_name=model_name,
                        days_limit=days_limit,
                        ai_filter_prompt=filter_prompt,
                        status_callback=remote_logger
                    )
                    
                    # 3. Save Data
                    if changes > 0:
                        save_data_to_github("news_data.json", updated_news, "Auto-Scrape Update")
                        remote_logger(f"Saved {changes} changes to news_data.json")
                    else:
                        remote_logger("No changes found.")
                        
                    # 4. Update Stats
                    stats["last_auto_scrape"] = datetime.datetime.now().isoformat()
                    # Update scraped counts
                    today_str = datetime.date.today().isoformat()
                    if "scraped_count" not in stats: stats["scraped_count"] = {}
                    if today_str not in stats["scraped_count"]: stats["scraped_count"][today_str] = {"Total": 0}
                    # We don't have exact counts per source here easily without refactoring logic return, 
                    # so just incrementing total run count for now or leave it.
                    
                    save_data_to_github("stats.json", stats, "Update stats: Auto-Scrape")
                    
                    remote_logger("Auto-Scrape Finished Successfully.")
                    
                    # Final log save with "idle" status
                    final_logs = {
                        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "idle",
                        "logs": log_buffer[-50:] # Keep last 50
                    }
                    save_logs_to_github(final_logs)
                    
                except Exception as e:
                    remote_logger(f"Error during auto-scrape: {e}")
                    final_error_logs = {
                        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "error",
                        "logs": log_buffer[-20:]
                    }
                    save_logs_to_github(final_error_logs)

        except Exception as e:
            print(f"Scheduler Error: {e}")
            
        time.sleep(60) # Check every minute

# Start Scheduler in a separate thread if not already running
# Note: Streamlit re-runs script on interaction, so we need to be careful not to spawn duplicates.
if not any(t.name == "NewsScheduler" for t in threading.enumerate()):
    t = threading.Thread(target=run_scheduler, name="NewsScheduler", daemon=True)
    t.start()
    print("Background Scheduler Started")

# --- Main App Logic ---

# Load Data
news_data, config, stats = load_all_data()

# Track Visit (Optimistic - don't block load on this write)
if 'visit_logged' not in st.session_state:
    update_stats_visit(stats)
    st.session_state['visit_logged'] = True

# Sidebar
st.sidebar.title("Daily AI News 🤖")

# Date Filter
today = datetime.date.today()
last_week = today - datetime.timedelta(days=7)
date_range = st.sidebar.date_input("Select Date Range", (last_week, today))

# Admin Login
st.sidebar.markdown("---")
show_login = st.sidebar.checkbox("Admin Login")
if show_login:
    password = st.sidebar.text_input("Password", type="password")
    if "ADMIN_PASSWORD" in st.secrets:
        if password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state['is_admin'] = True
            st.sidebar.success("Logged in as Admin")
        elif password:
            st.sidebar.error("Incorrect Password")
    else:
        st.sidebar.warning("ADMIN_PASSWORD not set in secrets.")

# --- Views ---

if st.session_state['is_admin']:
    # ADMIN VIEW
    st.title("Admin Dashboard 🛠️")
    tab1, tab2, tab3 = st.tabs(["Settings", "Manage Articles", "Statistics"])
    
    with tab1:
        st.header("Configuration")
        
        # RSS URLs
        st.subheader("RSS Feeds")
        current_urls = config.get("rss_urls", [])
        new_url = st.text_input("Add New RSS URL")
        if st.button("Add URL"):
            if new_url and new_url not in current_urls:
                current_urls.append(new_url)
                config["rss_urls"] = current_urls
                if save_data_to_github("config.json", config, "Update Config: Add RSS"):
                    st.success("Added URL!")
                    rerun()
                else:
                    st.error("Failed to save to GitHub.")
        
        st.write("Current Feeds:")
        for i, url in enumerate(current_urls):
            col1, col2 = st.columns([4, 1])
            col1.text(url)
            if col2.button("Delete", key=f"del_{i}"):
                current_urls.pop(i)
                config["rss_urls"] = current_urls
                save_data_to_github("config.json", config, "Update Config: Delete RSS")
                rerun()

        st.markdown("---")
        
        # Scheduler & Model
        col_sched, col_model = st.columns(2)
        with col_sched:
            st.subheader("Automation")
            interval = st.number_input("Update Interval (minutes)", 
                                     value=config.get("update_interval_minutes", 180), 
                                     min_value=15)
            
            days_to_scrape = st.slider("Days to Scrape (History)", 1, 7, config.get("days_to_scrape", 3))
            
            enable_auto = st.checkbox("Enable Auto-Scrape (Background)", value=config.get("enable_auto_scrape", False))
            
            if enable_auto:
                # Initialize session state for timer if not exists
                if 'timer_last_run' not in st.session_state:
                     st.session_state['timer_last_run'] = stats.get("last_auto_scrape", "2000-01-01T00:00:00")
                if 'timer_last_poll' not in st.session_state:
                     st.session_state['timer_last_poll'] = 0
                
                # Update if page reloaded with newer data
                config_last_run = stats.get("last_auto_scrape", "2000-01-01T00:00:00")
                if config_last_run > st.session_state['timer_last_run']:
                     st.session_state['timer_last_run'] = config_last_run

                @st.fragment(run_every=1)
                def show_timer(interval_mins):
                     try:
                        last_run_iso = st.session_state['timer_last_run']
                        last_run = datetime.datetime.fromisoformat(last_run_iso)
                        next_run = last_run + datetime.timedelta(minutes=interval_mins)
                        remaining = (next_run - datetime.datetime.now()).total_seconds()
                        
                        if remaining > 0:
                            mins = int(remaining // 60)
                            secs = int(remaining % 60)
                            st.caption(f"⏳ Next run in: **{mins}m {secs}s** (at {next_run.strftime('%H:%M:%S')})")
                        else:
                            st.caption(f"🚀 Status: **Processing Now...** (Due at {next_run.strftime('%H:%M:%S')})")
                            
                            # Poll for completion if overdue
                            now_ts = time.time()
                            if now_ts - st.session_state['timer_last_poll'] > 10: # Poll every 10s
                                st.session_state['timer_last_poll'] = now_ts
                                # Re-fetch stats to see if job finished
                                latest_stats = load_data_from_github("stats.json", {})
                                new_ts = latest_stats.get("last_auto_scrape")
                                if new_ts and new_ts > st.session_state['timer_last_run']:
                                     st.session_state['timer_last_run'] = new_ts
                                     st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun() # Force refresh to reset timer immediately
                                     
                     except Exception as e:
                        st.caption(f"Status: checking... ({e})")

                show_timer(interval)
            
            st.markdown("---")
            st.subheader("AI Filter")
            filter_prompt = st.text_area("Filtering Criteria (AI will skip articles not matching this)", 
                                        value=config.get("ai_filter_prompt", DEFAULT_CONFIG["ai_filter_prompt"]),
                                        height=100)

            if st.button("Save Settings"):
                config["update_interval_minutes"] = interval
                config["days_to_scrape"] = days_to_scrape
                config["ai_filter_prompt"] = filter_prompt
                config["enable_auto_scrape"] = enable_auto
                save_data_to_github("config.json", config, "Update Config: Automation Settings")
                st.success("Saved! Reloading...")
                time.sleep(1)
                rerun()

        # Move Logs and Refresh Button out of columns for full width
        st.markdown("---")
        st.subheader("Control Panel & Logs")

        # Session State for Logs
        if 'refresh_logs' not in st.session_state:
            st.session_state['refresh_logs'] = []

        st.subheader("Manual Controls")
        if st.button("Refresh News Now"):
            # UI Elements for progress
            progress_bar = st.progress(0)
            
            # Reset logs
            st.session_state['refresh_logs'] = []
            st.session_state['log_source'] = "Session (Manual)" # Switch to session view
            
            def update_progress_ui(value):
                progress_bar.progress(min(max(value, 0.0), 1.0))
                
            def update_status_ui(message):
                st.session_state['refresh_logs'].append(message)
                
            # Run Process
            try:
                updated_news, changes = process_news_data(
                    config.get("rss_urls", DEFAULT_CONFIG["rss_urls"]), 
                    news_data, 
                    model_name=config.get("openai_model", "gpt-4o-mini"),
                    days_limit=config.get("days_to_scrape", 3),
                    ai_filter_prompt=config.get("ai_filter_prompt", None),
                    status_callback=update_status_ui,
                    progress_callback=update_progress_ui
                )
                
                if changes > 0:
                    st.success(f"Updated {changes} articles.")
                    save_data_to_github("news_data.json", updated_news, "Update News Data via Admin")
                    time.sleep(1)
                    rerun()
                else:
                    st.info("No new articles found.")
                    
            except Exception as e:
                st.error(f"Error refreshing news: {e}")
                
        st.markdown("---")
        
        # Log Viewer
        col_log_head, col_log_ref = st.columns([4, 1])
        with col_log_head:
            log_source = st.radio("Log Source", ["Session (Manual)", "Auto-Scrape (Persistent)"], horizontal=True, key="log_source")
        with col_log_ref:
            st.write("")
            st.write("")
            if st.button("Refresh Logs"):
                pass # Just reruns to fetch new logs

        log_expander = st.expander("Processing Logs", expanded=True)
        with log_expander:
            if log_source == "Session (Manual)":
                if st.session_state['refresh_logs']:
                    st.code("\n".join(st.session_state['refresh_logs']))
                else:
                    st.info("No session logs. Run 'Refresh News Now' to generate logs.")
            else:
                # Persistent Logs
                logs_data = load_logs_from_github()
                status = logs_data.get("status", "unknown")
                last_updated = logs_data.get("last_updated", "N/A")
                
                st.caption(f"Status: **{status}** | Last Updated: {last_updated}")
                
                entries = logs_data.get("logs", [])
                if entries:
                    # Format: [Time] Message
                    log_lines = [f"[{e.get('timestamp', '')}] {e.get('message', '')}" for e in entries]
                    st.code("\n".join(log_lines))
                else:
                    st.info("No persistent logs found.")



        with col_model:
            st.subheader("AI Model")
            current_model = config.get("model", "gpt-4o-mini")
            available_models = ["gpt-4o-mini", "chatgpt-5-mini", "gemini-3-flash-preview"]
            
            # Ensure current model is in list
            index = 0
            if current_model in available_models:
                index = available_models.index(current_model)
                
            new_model = st.selectbox("Select Model", available_models, index=index)
            if new_model != current_model:
                config["model"] = new_model
                save_data_to_github("config.json", config, f"Update Config: Model to {new_model}")
                st.info("Model updated!")
                rerun()

    with tab2:
        st.header("Manage Articles")
        st.info("Select articles to delete. Warning: This action is irreversible.")
        
        if not news_data:
            st.warning("No articles found.")
        else:
            # Prepare DataFrame
            df = pd.DataFrame(news_data)
            # Ensure 'selected' column exists
            if 'selected' not in df.columns:
                df.insert(0, 'selected', False)

            # --- Manual Table Implementation (Backward Compatibility) ---
            
            # Header
            h_col1, h_col2, h_col3, h_col4 = st.columns([0.5, 3, 5, 2])
            h_col1.markdown("**Sel**")
            h_col2.markdown("**Title**")
            h_col3.markdown("**Summary**")
            h_col4.markdown("**Date**")
            st.markdown("---")

            # Selection State Logic for "Select All"
            # We use a unique key based on the 'select_all_version' to force reset checkboxes if needed, 
            # or just rely on manual checking. 
            if 'selected_ids' not in st.session_state:
                st.session_state['selected_ids'] = set()

            col_sel1, col_sel2 = st.columns([1, 10])
            with col_sel1:
                if st.button("Select All"):
                    st.session_state['selected_ids'] = {item['id'] for item in news_data}
                    st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()
            with col_sel2:
                if st.button("Deselect All"):
                    st.session_state['selected_ids'] = set()
                    st.experimental_rerun() if hasattr(st, 'experimental_rerun') else st.rerun()

            ids_to_delete = []
            
            # Render Rows
            for item in news_data:
                row_col1, row_col2, row_col3, row_col4 = st.columns([0.5, 3, 5, 2])
                
                is_selected = item['id'] in st.session_state['selected_ids']
                
                # Checkbox
                # value=is_selected sets the initial state. 
                # On change, we must update the session_state['selected_ids']
                with row_col1:
                    checked = st.checkbox(f"Select {item['id']}", value=is_selected, key=f"del_{item['id']}", label_visibility="collapsed")
                    if checked:
                        st.session_state['selected_ids'].add(item['id'])
                        if item['id'] not in ids_to_delete:
                            ids_to_delete.append(item['id'])
                    else:
                        if item['id'] in st.session_state['selected_ids']:
                            st.session_state['selected_ids'].remove(item['id'])

                with row_col2:
                    st.markdown(f"**[{item.get('title', 'No Title')}]({item.get('link', '#')})**")
                    st.caption(f"Source: {item.get('source', 'Unknown')}")
                
                with row_col3:
                     # Truncate summary
                     summary_text = item.get('summary', '')
                     if summary_text and len(summary_text) > 100:
                         summary_text = summary_text[:100] + "..."
                     st.text(summary_text)

                with row_col4:
                    st.text(item.get('date', '-'))
                
                st.markdown("<hr style='margin: 0.5em 0;'>", unsafe_allow_html=True)

            total_selected = len(st.session_state['selected_ids'])
            
            st.markdown(f"**Selected: {total_selected} articles**")

            if total_selected > 0:
                if st.button("Delete Selected", type="primary"):
                    st.session_state['confirm_delete'] = True
                
                if st.session_state.get('confirm_delete'):
                    st.warning(f"⚠️ Are you sure you want to delete {total_selected} articles? This cannot be undone.")
                    col_conf1, col_conf2 = st.columns(2)
                    with col_conf1:
                        if st.button("Yes, Delete Completely"):
                            # Filter out deleted
                            # Use session_state set for truth
                            final_ids_to_delete = st.session_state['selected_ids']
                            new_news_list = [item for item in news_data if item.get('id') not in final_ids_to_delete]
                            
                            if save_data_to_github("news_data.json", new_news_list, f"Admin: Deleted {len(final_ids_to_delete)} articles"):
                                st.success(f"Deleted {len(final_ids_to_delete)} articles.")
                                st.session_state['confirm_delete'] = False
                                st.session_state['selected_ids'] = set() # Reset
                                time.sleep(1)
                                rerun()
                            else:
                                st.error("Failed to save changes to GitHub.")
                    with col_conf2:
                        if st.button("Cancel"):
                            st.session_state['confirm_delete'] = False
                            rerun()

    with tab3:
        st.header("Statistics")
        
        # Visits
        visits_data = stats.get("daily_visits", {})
        if visits_data:
            df_visits = pd.DataFrame(list(visits_data.items()), columns=["Date", "Visits"])
            fig_visits = px.line(df_visits, x="Date", y="Visits", title="Daily Visits")
            st.plotly_chart(fig_visits)
        else:
            st.info("No visit data yet.")
            
        # Scraped
        scraped_data = stats.get("scraped_count", {})
        # Simplified handling for nested dict
        flat_scraped = []
        for d, counts in scraped_data.items():
            if isinstance(counts, dict):
                 for source, count in counts.items():
                     flat_scraped.append({"Date": d, "Source": source, "Count": count})
        
        if flat_scraped:
            df_scraped = pd.DataFrame(flat_scraped)
            fig_scraped = px.bar(df_scraped, x="Date", y="Count", color="Source", title="Articles Scraped")
            st.plotly_chart(fig_scraped)
        else:
            st.info("No scraping stats yet.")

else:
    # USER VIEW
    st.title("Daily AI News Brief 📰")
    
    # Auto-Scrape Status Indicator
    enable_auto = config.get("enable_auto_scrape", False)
    if enable_auto:
        last_run_str = stats.get("last_auto_scrape", "2000-01-01T00:00:00")
        try:
            last_run = datetime.datetime.fromisoformat(last_run_str)
            interval_sec = config.get("update_interval_minutes", 180) * 60
            time_since_run = (datetime.datetime.now() - last_run).total_seconds()
            
            # If overdue (running)
            if time_since_run > interval_sec:
                st.markdown("""
                <style>
                @keyframes blink {
                    0% { opacity: 1; }
                    50% { opacity: 0.4; }
                    100% { opacity: 1; }
                }
                .blinking-text {
                    color: red;
                    font-weight: bold;
                    animation: blink 1.5s linear infinite;
                    margin-bottom: 15px;
                }
                </style>
                <div class="blinking-text">⚠️ AI 에이전트가 관련 뉴스를 수집하고 있습니다.</div>
                """, unsafe_allow_html=True)
        except Exception:
             pass

    # Filter Data
    if len(date_range) == 2:
        start_date, end_date = date_range
        # Filter logic: compare string dates
        filtered_news = [
            item for item in news_data 
            if start_date <= datetime.datetime.strptime(item['date'], "%Y-%m-%d").date() <= end_date
        ]
    else:
        filtered_news = news_data

    # Display
    st.markdown(f"**Showing {len(filtered_news)} articles**")
    
    for item in filtered_news:
        with st.container():
            # Customizable Font Sizes via HTML/CSS
            st.markdown(f"<div style='font-size: 16px; font-weight: bold; margin-bottom: 5px;'>{item['title']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 13px; color: #555; margin-bottom: 5px;'>Source: {item['source']} | Time: {item['timestamp']} | <a href='{item['link']}' style='font-size: 14px;' target='_blank'>Read Original</a></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 14px; margin-bottom: 5px;'>{item['summary']}</div>", unsafe_allow_html=True)
            # Custom divider with reduced margin (approx half of standard st.divider)
            st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #f0f2f6;'>", unsafe_allow_html=True)

    if not filtered_news:
        st.info("No news found for the selected date range.")

