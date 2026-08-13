import os
import json

# Persistent storage for user facts
PROFILE_FILE = "user_profile.json"

def get_user_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, 'r') as f:
            return json.load(f)
    return {}

def update_user_profile(new_data):
    profile = get_user_profile()
    profile.update(new_data)
    with open(PROFILE_FILE, 'w') as f:
        json.dump(profile, f, indent=2)

def format_profile_for_system_prompt():
    profile = get_user_profile()
    if not profile:
        return "The user has not provided personal details yet."
    return "User Profile: " + ", ".join([f"{k}: {v}" for k, v in profile.items()])
