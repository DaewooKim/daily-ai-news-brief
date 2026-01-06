import json
import streamlit as st
from github import Github, GithubException

def get_github_repo():
    """
    Authenticates with GitHub using secrets and returns the Repository object.
    """
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo_name = st.secrets["REPO_NAME"]
        g = Github(token)
        return g.get_repo(repo_name)
    except Exception as e:
        st.error(f"Error connecting to GitHub: {e}")
        return None

def load_data_from_github(filename, default_value):
    """
    Fetches a JSON file from the GitHub repository.
    If the file does not exist, returns the default_value.
    """
    repo = get_github_repo()
    if not repo:
        return default_value

    try:
        branch = st.secrets.get("BRANCH", "main")
        contents = repo.get_contents(filename, ref=branch)
        data = json.loads(contents.decoded_content.decode())
        return data
    except GithubException as e:
        if e.status == 404:
            # File not found, return default value
            return default_value
        else:
            st.error(f"Error loading {filename} from GitHub: {e}")
            return default_value
    except Exception as e:
        st.error(f"Error parsing {filename}: {e}")
        return default_value

def save_data_to_github(filename, data, commit_message):
    """
    Saves data (as JSON) to the GitHub repository.
    Creates the file if it doesn't exist, updates it if it does.
    """
    repo = get_github_repo()
    if not repo:
        return False

    try:
        branch = st.secrets.get("BRANCH", "main")
        json_content = json.dumps(data, indent=2)
        
        try:
            # Try to get existing file
            contents = repo.get_contents(filename, ref=branch)
            repo.update_file(
                path=filename,
                message=commit_message,
                content=json_content,
                sha=contents.sha,
                branch=branch
            )
        except GithubException as e:
            if e.status == 404:
                # File doesn't exist, create it
                repo.create_file(
                    path=filename,
                    message=commit_message,
                    content=json_content,
                    branch=branch
                )
            else:
                raise e
        return True
    except Exception as e:
        st.error(f"Error saving {filename} to GitHub: {e}")
        return False

def load_logs_from_github():
    """Reads logs.json from GitHub."""
    default_logs = {"logs": [], "last_updated": None, "status": "idle"}
    return load_data_from_github("logs.json", default_logs)

def save_logs_to_github(logs_data):
    """Saves logs.json to GitHub."""
    return save_data_to_github("logs.json", logs_data, "Update execution logs")
