import re
import random
from io import BytesIO
from urllib.request import urlopen, Request

import pandas as pd
import streamlit as st

# =========================
# Config
# =========================
st.set_page_config(page_title="Wheel of Fortune", layout="wide")

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VOWELS = set("AEIOU")

DEFAULT_WHEEL = [
    100, 150, 200, 250, 300, 350, 400, 450, 500,
    550, 600, 650, 700, 750, 800, 900,
    "BANKRUPT", "LOSE A TURN"
]

# Update this to match where the CSV is in your repo
DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/chad-k/GainSeeker-Wheel-of-Fortune/main/"
    "gainseeker_proper_nouns.csv"
)

# Allow doc-style proper nouns (numbers, slashes, dots, hyphens, etc.)
ALLOWED_PUZZLE_RE = re.compile(r"^[A-Za-z0-9\s&\-\./'()]+$")

# =========================
# Helpers
# =========================
def normalize_phrase(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).upper()

def mask_phrase(phrase: str, guessed: set[str]) -> str:
    return "".join(ch if ch not in ALPHABET or ch in guessed else "■" for ch in phrase)

def count_letter(phrase: str, letter: str) -> int:
    return sum(1 for ch in phrase if ch == letter)

def load_puzzles_from_csv_bytes(file_bytes: bytes) -> list[str]:
    try:
        df = pd.read_csv(BytesIO(file_bytes))
    except Exception:
        return []

    if "ProperNounCandidate" in df.columns:
        series = df["ProperNounCandidate"]
    else:
        series = df.iloc[:, 0]

    puzzles = []
    for x in series.dropna().astype(str):
        s = x.strip()
        if not s:
            continue
        if len(s) < 3 or len(s) > 60:
            continue
        if not ALLOWED_PUZZLE_RE.match(s):
            continue
        puzzles.append(normalize_phrase(s))

    # De-dup, preserve order
    seen = set()
    out = []
    for p in puzzles:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

@st.cache_data(show_spinner=False)
def fetch_url_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        return resp.read()

def ensure_state():
    defaults = {
        "puzzles": [],
        "puzzle": "",
        "guessed": set(),
        "round_bank": 0,     # money for current puzzle
        "total_bank": 0,     # cumulative money across puzzles
        "last_spin": None,
        "must_spin": True,
        "message": "Loading words...",
        "lives": 5,
        "csv_url": DEFAULT_CSV_URL,
        "load_error": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def new_round(puzzles: list[str]):
    if not puzzles:
        return
    st.session_state.puzzle = normalize_phrase(random.choice(puzzles))
    st.session_state.guessed = set()
    st.session_state.round_bank = 0
    st.session_state.last_spin = None
    st.session_state.must_spin = True
    # NOTE: Do NOT reset total_bank here
    st.session_state.message = "New puzzle loaded. Spin to start!"

def auto_load_words():
    # Only load once per session unless user forces a retry
    if st.session_state.puzzles:
        return

    url = st.session_state.csv_url
    try:
        data = fetch_url_bytes(url)
        puzzles = load_puzzles_from_csv_bytes(data)
        if not puzzles:
            st.session_state.load_error = (
                "Downloaded the CSV, but found no valid puzzles. "
                "Check the CSV column name (ProperNounCandidate) or contents."
            )
            st.session_state.message = "Failed to load puzzles."
            return

        st.session_state.puzzles = puzzles
        st.session_state.load_error = ""
        new_round(puzzles)
    except Exception as e:
        st.session_state.load_error = f"Could not download CSV from GitHub. Error: {e}"
        st.session_state.message = "Failed to load puzzles."

# =========================
# App
# =========================
ensure_state()
auto_load_words()

st.title("🎡 Wheel of Fortune")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("How to Play")

    with st.expander("📖 How Wheel of Fortune Works", expanded=False):
        st.markdown("""
### 🎯 Objective
Solve the puzzle by guessing letters and earn as much money as possible before you run out of lives.

### 🎡 Turn Flow
1. **Spin**
2. **Guess a consonant** (earns money)
3. **Buy a vowel** (costs money)
4. **Solve** anytime

### 💣 Special Spins
- **BANKRUPT**: Round money → $0
- **LOSE A TURN**: spin again

### ❤️ Lives
Wrong consonant / wrong vowel / wrong solve = lose 1 life.
""")

    st.divider()
    st.header("Data Source (GitHub)")
    st.session_state.csv_url = st.text_input("CSV Raw URL", value=st.session_state.csv_url)

    if st.session_state.load_error:
        st.error(st.session_state.load_error)
        colA, colB = st.columns
