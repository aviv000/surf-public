"""Shared configuration for the spear-phishing KG pipeline."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# Project root
ROOT = Path(__file__).parent

# API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")  # .env uses GEMINI_API_KEY
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Model configuration
DEFAULT_LLM = "gpt-4.1"               # Extractor, Profiler, Generator
CHEAP_LLM = "gpt-4.1-mini"            # Integrator merge resolution
ABLATION_MODELS = ["gpt-4.1-mini", "gpt-4.1", "claude-haiku-4-5", "claude-sonnet-4-6"]

# Gemini configuration
GEMINI_MODELS = [                      # Model fallback chain (primary → fallback)
    "gemini-3.5-flash",               # Latest Flash (May 2026), Google Search Grounding
    "gemini-3.1-flash",               # Previous-gen Flash
    "gemini-2.5-flash",               # Older, free tier 500 RPD
    "gemini-2.5-flash-lite",          # Cheapest, free tier 500 RPD
]
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_QUERY_COUNT = 13               # Number of targeted Gemini searches per target
GEMINI_MAX_OUTPUT_TOKENS = 8192       # Per-query output cap
GEMINI_MAX_RETRIES = 3                # Max retries per model before fallback
GEMINI_BACKOFF_BASE = 2.0             # Base seconds for exponential backoff

# Temporal thresholds
RECENT_YEAR_THRESHOLD = 2024           # Papers >= this year are "recent"
STALE_YEAR_THRESHOLD = 2023            # Papers < this year are "stale"
RECENT_MONTHS_THRESHOLD = 12           # For "within last 12 months" scoring

# Cache
CACHE_TTL_DAYS = 7
CACHE_DIR = ROOT / "cache" / "targets"

# Rate limiting (seconds)
DUCKDUCKGO_DELAY = 2.0
# GEMINI_DELAY removed — backoff+retry handles rate limiting (2026-05-31)
WEBFETCH_DELAY = 3.0                   # Kept for DDG fallback page fetches
LLM_RATE_LIMIT = 120                   # Requests per minute (3 providers, no cross-provider contention)

# Profiler
PROFILER_STAGE1_TOP_N = 10            # Heuristic pre-filter selects top N
PROFILER_STAGE2_TOP_N = 5             # LLM selects top N hooks
KG_GRAPH_DEPTH = 2                    # Hops from target used to compose hooks (email metadata; the depth knob varies this per round)
TRAIT_HOOKS_ENABLED = False           # Trait hooks OFF by default: traits become hooks only in rounds that test them

# Appeal tactics: how to phrase an email toward an inferred trait
# (grounded: Hirsh 2012 for Big-5; Oliveira/Cialdini/Stajano for the
# persuasion-susceptibility set).
TRAIT_TACTICS = {
    "openness": "novel, exploratory framing; present the idea as a new direction they would find intriguing",
    "conscientiousness": "organized, structured framing; clear steps, reliability, respect for their time",
    "extraversion": "social, dynamic framing; mention people and events, quick engaging tone",
    "agreeableness": "collaborative, communal framing; frame the ask as working together, mutual benefit",
    "neuroticism": "safety and reassurance framing; low-risk ask, explicitly no commitment",
    "authority_responsiveness": "formal, institutional framing; reference roles, institutions, established channels",
    "time_pressure_sensitivity": "mild deadline framing; a natural, believable time window, without aggressive urgency",
    "social_proof_susceptibility": "reference colleagues or peers already engaged with the idea",
    "reciprocation_tendency": "offer something first; a small favor or shared resource before the ask",
    "strong_affect_responsiveness": "emotive framing tied to the topic's stakes; use sparingly, low inferability",
}

# Generator
GENERATOR_EMAIL_SENTENCES = "3-5"     # Email length target

# Paths
TARGETS_CSV = ROOT / "targets.csv"
MERGED_GRAPH = ROOT / "cache" / "merged_graph.json"
PROMPTS_DIR = ROOT / "prompts"
OUTPUTS_DIR = ROOT / "outputs"

# Evaluation
JUDGES_NEEDED = 20
EMAILS_PER_JUDGE = 30                  # 10 per condition (language variant randomized within temporal_kg)
CONDITIONS = ["baseline", "static_pii", "temporal_kg"]

# Gmail Filter Eval (camera-ready experiment)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MAILERSEND_API_KEY = os.getenv("MAILERSEND_API_KEY")
TEST_MAILERSEND_DOMAIN = os.getenv("TEST_MAILERSEND_DOMAIN", "")
GMAIL_MAIL_ADDRESS = os.getenv("GMAIL_MAIL_ADDRESS")
GMAIL_APP_CLIENT_ID = os.getenv("GMAIL_APP_CLIENT_ID")
GMAIL_APP_CLIENT_SECRET = os.getenv("GMAIL_APP_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")
SENDING_DOMAIN = "cs-review.org"
SEND_INTERVAL_SEC = 90   # pacing to avoid burst detection

# Neo4j (optional)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Language normalization (ISO 639-1)
LANGUAGE_MAP = {
    "hebrew": "he", "עברית": "he", "he": "he",
    "english": "en", "en": "en",
    "french": "fr", "français": "fr", "fr": "fr",
    "german": "de", "deutsch": "de", "de": "de",
    "arabic": "ar", "العربية": "ar", "ar": "ar",
    "spanish": "es", "español": "es", "es": "es",
    "russian": "ru", "русский": "ru", "ru": "ru",
    "chinese": "zh", "中文": "zh", "zh": "zh",
    "japanese": "ja", "日本語": "ja", "ja": "ja",
    "italian": "it", "italiano": "it", "it": "it",
    "portuguese": "pt", "português": "pt", "pt": "pt",
    "dutch": "nl", "nederlands": "nl", "nl": "nl",
    "korean": "ko", "한국어": "ko", "ko": "ko",
}

# Hook type priority bonuses (Stage 1 heuristic)
HOOK_TYPE_BONUS = {
    "recent_paper": 5,
    "recent_coauthor": 5,
    "teaching": 5,
    "public_appearance": 4,
    "funding": 4,
    "career_history": 4,
    "organization": 3,
    "education": 3,
    "social_identity": 3,
    "personal_interest": 3,
    "geographic": 2,
    "shared_venue": 2,
    "affiliation_change": 2,
    "stale_paper": 1,
    "open_discovery": 1,
    "trait": 4,
}

# Source preference (for Integrator property conflict resolution)
SOURCE_PREFERENCE = ["gemini", "semantic_scholar", "ddg", "web_fetch"]

# Ensure directories exist
for d in [CACHE_DIR, PROMPTS_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
