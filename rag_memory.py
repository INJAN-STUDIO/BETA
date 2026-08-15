import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_profile():
    try:
        response = supabase.table("user_profile").select("data").eq("id", "main_user").execute()
        if response.data:
            return response.data[0]["data"]
        return {}
    except Exception as e:
        return {}

def update_user_profile(new_data):
    profile = get_user_profile()
    profile.update(new_data)
    
    # Upsert the profile in Supabase
    supabase.table("user_profile").upsert({
        "id": "main_user",
        "data": profile
    }).execute()

def format_profile_for_system_prompt():
    profile = get_user_profile()
    if not profile:
        return "The user has not provided personal details yet."
    return "User Profile: " + ", ".join([f"{k}: {v}" for k, v in profile.items()])
