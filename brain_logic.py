import os
import json
import httpx
import logging
import datetime
from supabase import create_client, Client
from rag_memory import format_profile_for_system_prompt, update_user_profile

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL = "llama-3.3-70b-versatile"

# ---- Tool schema Groq/OpenAI-style function calling ----
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live web for current information: news, prices, "
                "weather, sports scores, facts about recent events, or anything "
                "that could have changed since training. Use this whenever the "
                "user asks about something current, recent, or that you are not "
                "certain about from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


async def perform_google_search(query: str) -> str:
    if not SERPER_API_KEY:
        logger.error("SERPER_API_KEY is missing!")
        return "Search functionality not configured."

    current_date = datetime.datetime.now().strftime("%d %B %Y")
    enhanced_query = f"{query} (as of {current_date})"

    logger.info(f"Researching: {enhanced_query}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": enhanced_query, "gl": "ng", "hl": "en", "num": 3},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("organic", [])
            if not results:
                return "No search results found."

            formatted_results = []
            for r in results[:3]:
                formatted_results.append(
                    f"{r['title']}\nSummary: {r.get('snippet', 'N/A')}\nLink: {r.get('link', 'N/A')}"
                )
            return "\n\n".join(formatted_results)
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return f"Search service error: {str(e)}"


class Brain:
    def load_history(self):
        try:
            response = (
                supabase.table("chat_history")
                .select("*")
                .order("created_at", desc=True)
                .limit(8)
                .execute()
            )
            history = response.data[::-1]
            return [{"role": item["role"], "content": item["content"]} for item in history]
        except Exception as e:
            logger.error(f"Supabase history load failed: {e}")
            return []

    def save_message(self, role, content):
        try:
            supabase.table("chat_history").insert({"role": role, "content": content}).execute()
        except Exception as e:
            logger.error(f"Supabase save failed: {e}")

    async def _call_groq(self, messages, client, allow_tools=True):
        payload = {"model": MODEL, "messages": messages}
        if allow_tools:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"

        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    async def chat(self, user_message):
        history = self.load_history()

        # Check for name update
        if "my name is" in user_message.lower():
            name = user_message.split("my name is")[-1].strip().split(".")[0]
            update_user_profile({"name": name})

        profile_context = format_profile_for_system_prompt()
        system_prompt = (
            "You are B.E.T.A. (Best Everyday Technical Assistant), a helpful AI "
            "assistant. You have access to a web_search tool for anything current, "
            "recent, or uncertain from memory — use it whenever it would help, "
            "don't wait to be asked to 'search'. "
            f"{profile_context} Keep responses concise and use a friendly tone."
        )

        messages = (
            [{"role": "system", "content": system_prompt}]
            + history
            + [{"role": "user", "content": user_message}]
        )

        async with httpx.AsyncClient() as client:
            try:
                data = await self._call_groq(messages, client)

                if "choices" not in data:
                    return {"response": "I couldn't process that right now."}

                message = data["choices"][0]["message"]
                tool_calls = message.get("tool_calls")

                # If the model wants to search, run the tool(s) and let it respond again
                if tool_calls:
                    messages.append(message)
                    for call in tool_calls:
                        if call["function"]["name"] == "web_search":
                            try:
                                args = json.loads(call["function"]["arguments"])
                            except (json.JSONDecodeError, TypeError):
                                args = {}
                            query = args.get("query", user_message)
                            result = await perform_google_search(query)
                        else:
                            result = "Unknown tool."

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": result,
                            }
                        )

                    # Second call: model writes the final answer using the tool result.
                    # allow_tools=False keeps this turn from spiraling into further calls.
                    data = await self._call_groq(messages, client, allow_tools=False)
                    if "choices" not in data:
                        return {"response": "I couldn't process that right now."}
                    message = data["choices"][0]["message"]

                ai_reply = message.get("content") or "I couldn't come up with a response."
                self.save_message("user", user_message)
                self.save_message("assistant", ai_reply)
                return {"response": ai_reply}

            except Exception as e:
                logger.error(f"Groq API error: {e}")
                return {"response": f"System Error: {str(e)}"}


brain = Brain()
