import re
import random
from io import BytesIO
from urllib.request import urlopen, Request
from pathlib import Path
from datetime import datetime

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

DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/chad-k/GainSeeker-Wheel-of-Fortune/main/"
    "gainseeker_proper_nouns.csv"
)

ALLOWED_PUZZLE_RE = re.compile(r"^[A-Za-z0-9\s&\-\./'()]+$")

HIGHSCORE_PATH = Path("highscores.csv")  # local persists; Streamlit Cloud may reset on redeploy

# =========================
# Helpers
# =========================
def normalize_phrase(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).upper()

def mask_phrase(phrase: str, guessed_set: set[str]) -> str:
    return "".join(ch if ch not in ALPHABET or ch in guessed_set else "■" for ch in phrase)

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

    # de-dup preserve order
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
        "guessed_list": [],      # store as list (stable)
        "round_bank": 0,
        "total_bank": 0,
        "last_spin": None,
        "must_spin": True,
        "message": "Loading words...",
        "lives": 5,
        "csv_url": DEFAULT_CSV_URL,
        "load_error": "",
        "last_earned": 0,
        "player_name": "Player 1",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def new_round(puzzles: list[str]):
    if not puzzles:
        return
    st.session_state.puzzle = normalize_phrase(random.choice(puzzles))
    st.session_state.guessed_list = []
    st.session_state.round_bank = 0
    st.session_state.last_spin = None
    st.session_state.must_spin = True
    st.session_state.last_earned = 0
    st.session_state.message = "New puzzle loaded. Spin to start!"

def auto_load_words():
    if st.session_state.puzzles:
        return

    try:
        data = fetch_url_bytes(st.session_state.csv_url)
        puzzles = load_puzzles_from_csv_bytes(data)
        if not puzzles:
            st.session_state.load_error = "Downloaded CSV, but no valid puzzles found."
            st.session_state.message = "Failed to load puzzles."
            return
        st.session_state.puzzles = puzzles
        st.session_state.load_error = ""
        new_round(puzzles)
    except Exception as e:
        st.session_state.load_error = f"Could not download CSV. Error: {e}"
        st.session_state.message = "Failed to load puzzles."

def read_highscores() -> pd.DataFrame:
    if not HIGHSCORE_PATH.exists():
        return pd.DataFrame(columns=["name", "score", "timestamp"])
    try:
        df = pd.read_csv(HIGHSCORE_PATH)
        if not set(["name", "score", "timestamp"]).issubset(df.columns):
            return pd.DataFrame(columns=["name", "score", "timestamp"])
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame(columns=["name", "score", "timestamp"])

def write_highscore(name: str, score: int):
    name = (name or "Player 1").strip()[:40]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = pd.DataFrame([{"name": name, "score": int(score), "timestamp": ts}])

    df = read_highscores()
    df = pd.concat([df, row], ignore_index=True)
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df.to_csv(HIGHSCORE_PATH, index=False)

def top_highscores(n: int = 10) -> pd.DataFrame:
    df = read_highscores()
    if df.empty:
        return df
    return df.sort_values("score", ascending=False).head(n).reset_index(drop=True)

# =========================
# App
# =========================
ensure_state()
auto_load_words()

st.title("🎡 Wheel of Fortune")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("How to Play")
    with st.expander("📖 How it works", expanded=False):
        st.markdown("""
- You **only earn money** by guessing a **consonant** that appears in the puzzle.
- Spin → guess consonant → keep going until you miss.
- Buy vowels (costs money) and solve anytime.
- When lives hit **0**, it’s **Game Over**.
""")

    st.divider()
    st.header("Player")
    st.session_state.player_name = st.text_input("Name", value=st.session_state.player_name)

    st.divider()
    st.header("High Scores (Top 10)")
    hs = top_highscores(10)
    if hs.empty:
        st.caption("No highscores yet. Cash out or lose to record one.")
    else:
        st.dataframe(hs, use_container_width=True, hide_index=True)

    st.divider()
    st.header("Data Source (GitHub)")
    st.session_state.csv_url = st.text_input("CSV Raw URL", value=st.session_state.csv_url)

    if st.session_state.load_error:
        st.error(st.session_state.load_error)
        if st.button("Retry Load", use_container_width=True):
            st.session_state.puzzles = []
            st.session_state.puzzle = ""
            st.session_state.load_error = ""
            st.cache_data.clear()
            st.rerun()
    else:
        st.success(f"Loaded {len(st.session_state.puzzles)} puzzles.")
        with st.expander("Preview"):
            st.write(st.session_state.puzzles[:25])

    st.divider()
    st.header("Game Settings")

    # Clamp for Streamlit widget safety (lives can be 0 in-game)
    lives_for_widget = max(1, int(st.session_state.lives))
    st.session_state.lives = int(
        st.number_input("Lives (starting)", min_value=1, max_value=20, value=lives_for_widget)
    )

    vowel_cost = st.number_input("Vowel cost", min_value=50, max_value=500, value=250, step=50)
    auto_next = st.checkbox("Auto next puzzle when solved", True)

    st.divider()
    if st.button("New Puzzle", disabled=not st.session_state.puzzles, use_container_width=True):
        new_round(st.session_state.puzzles)
        st.rerun()

    if st.button("Reset Total Money", use_container_width=True):
        st.session_state.total_bank = 0
        st.rerun()

# ---------- MAIN GAME ----------
if not st.session_state.puzzle:
    st.info("No puzzle loaded. Check the GitHub CSV URL in the sidebar.")
    st.stop()

puzzle = st.session_state.puzzle
guessed_set = set(st.session_state.guessed_list)

# Metrics (always visible)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Round Money", f"${st.session_state.round_bank}")
m2.metric("Total Money", f"${st.session_state.total_bank}")
m3.metric("Current Spin", str(st.session_state.last_spin) if st.session_state.last_spin is not None else "—")
m4.metric("Last Earned", f"${st.session_state.last_earned}")

st.subheader("Puzzle")
st.markdown(
    f"<div style='font-size:52px; letter-spacing:4px; font-weight:800; text-align:center;'>"
    f"{mask_phrase(puzzle, guessed_set)}</div>",
    unsafe_allow_html=True
)
st.caption(f"Guessed: {', '.join(sorted(guessed_set)) if guessed_set else '(none)'}")
st.info(st.session_state.message)

# ---------- GAME OVER GATE ----------
if st.session_state.lives <= 0:
    st.error("💀 GAME OVER — Out of lives.")
    st.write(f"Final Total: **${st.session_state.total_bank}**")

    colA, colB = st.columns(2)
    with colA:
        if st.button("🏁 Record High Score", use_container_width=True):
            write_highscore(st.session_state.player_name, st.session_state.total_bank)
            st.success("Saved!")
            st.rerun()
    with colB:
        if st.button("🔄 Start New Game", use_container_width=True):
            # New game: reset total + start puzzle
            st.session_state.total_bank = 0
            st.session_state.lives = 5
            new_round(st.session_state.puzzles)
            st.rerun()

    st.stop()

# Gameplay controls
c1, c2, c3, c4 = st.columns(4)

# SPIN
with c1:
    if st.button("🎡 SPIN", use_container_width=True):
        result = random.choice(DEFAULT_WHEEL)
        st.session_state.last_spin = result
        st.session_state.last_earned = 0

        if result == "BANKRUPT":
            st.session_state.round_bank = 0
            st.session_state.must_spin = True
            st.session_state.message = "💥 BANKRUPT! Round money reset. Spin again."
        elif result == "LOSE A TURN":
            st.session_state.must_spin = True
            st.session_state.message = "⏭️ LOSE A TURN! Spin again."
        else:
            st.session_state.must_spin = False
            st.session_state.message = f"Spun ${result}. Guess a consonant!"
        st.rerun()

# GUESS CONSONANT
with c2:
    letter = st.text_input("Consonant", max_chars=1, key="cons").upper().strip()
    if st.button("Guess Consonant", use_container_width=True):
        if not letter or letter not in ALPHABET:
            st.session_state.message = "Enter A–Z."
        elif letter in guessed_set:
            st.session_state.message = f"{letter} already guessed."
        elif letter in VOWELS:
            st.session_state.message = "That's a vowel. Buy it instead."
        elif st.session_state.must_spin:
            st.session_state.message = "Spin first!"
        elif not isinstance(st.session_state.last_spin, int):
            st.session_state.message = "Spin a dollar amount first!"
        else:
            guessed_set.add(letter)
            st.session_state.guessed_list = sorted(guessed_set)

            hits = count_letter(puzzle, letter)
            if hits > 0:
                earned = hits * int(st.session_state.last_spin)
                st.session_state.round_bank = int(st.session_state.round_bank) + int(earned)
                st.session_state.last_earned = int(earned)
                st.session_state.message = f"✅ {letter} appears {hits} time(s). +${earned}"
            else:
                st.session_state.last_earned = 0
                st.session_state.lives = max(0, int(st.session_state.lives) - 1)
                st.session_state.message = f"❌ No {letter}. Lives: {st.session_state.lives}"

            st.session_state.must_spin = True

        st.rerun()

# BUY VOWEL
with c3:
    vowel = st.text_input("Vowel", max_chars=1, key="vow").upper().strip()
    if st.button(f"Buy Vowel (-${vowel_cost})", use_container_width=True):
        if st.session_state.round_bank < vowel_cost:
            st.session_state.message = f"Not enough money (need ${vowel_cost})."
        elif not vowel or vowel not in VOWELS:
            st.session_state.message = "Enter A, E, I, O, or U."
        elif vowel in guessed_set:
            st.session_state.message = f"{vowel} already guessed."
        else:
            st.session_state.round_bank = int(st.session_state.round_bank) - int(vowel_cost)

            guessed_set.add(vowel)
            st.session_state.guessed_list = sorted(guessed_set)

            hits = count_letter(puzzle, vowel)
            st.session_state.last_earned = 0

            if hits == 0:
                st.session_state.lives = max(0, int(st.session_state.lives) - 1)
                st.session_state.message = f"❌ No {vowel}. Lives: {st.session_state.lives}"
            else:
                st.session_state.message = f"✅ {vowel} appears {hits} time(s)."

        st.rerun()

# CASH OUT (record score anytime)
with c4:
    if st.button("🏁 Cash Out (Save Score)", use_container_width=True):
        write_highscore(st.session_state.player_name, st.session_state.total_bank)
        st.session_state.message = "Saved your current total to High Scores."
        st.rerun()

st.divider()

# SOLVE
solution = st.text_input("Solve the puzzle", key="solve").strip()
if st.button("Solve"):
    if normalize_phrase(solution) == puzzle:
        st.session_state.total_bank = int(st.session_state.total_bank) + int(st.session_state.round_bank)
        st.session_state.message = (
            f"🎉 CORRECT! Banked ${st.session_state.round_bank}. Total = ${st.session_state.total_bank}"
        )
        # reveal all letters
        for ch in puzzle:
            if ch in ALPHABET:
                guessed_set.add(ch)
        st.session_state.guessed_list = sorted(guessed_set)
    else:
        st.session_state.lives = max(0, int(st.session_state.lives) - 1)
        st.session_state.message = f"❌ Wrong answer. Lives: {st.session_state.lives}"
    st.rerun()

# WIN CHECK
solved = all((ch not in ALPHABET) or (ch in guessed_set) for ch in puzzle)
if solved:
    st.success("✅ PUZZLE SOLVED!")
    if auto_next and st.button("Next Puzzle ▶️"):
        new_round(st.session_state.puzzles)
        st.rerun()
