import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")

PASS_THRESHOLD = float(os.getenv("PASS_THRESHOLD", "0.85"))
AUTO_THRESHOLD = float(os.getenv("AUTO_THRESHOLD", "0.6"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

ESCALATE_TAGS: set[str] = set(
    t.strip() for t in os.getenv("ESCALATE_TAGS", "high-stakes,medical,legal").split(",") if t.strip()
)
