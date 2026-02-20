import re
import random
from io import BytesIO
from urllib.request import urlopen, Request

import pandas as pd
import streamlit as st

# =========================
# Page setup
# =========================
st.set_page_config(page_title="Wheel of Fortune", layout="wide")

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VOWELS = set("AEIOU")

DEFAULT_WHEEL = [
    100, 150, 200, 250, 300, 350, 400, 450, 500,
    550, 600, 650, 700, 750, 800, 900,
    "BANKRUPT", "LOSE A TURN"
]

# Allow typical documentation-style proper nouns
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

def load_proper_nouns_from_csv_bytes(file_bytes: bytes) -> list[str]:
    try:
        df = pd.read_csv(BytesIO(file_bytes))
    except Exception:
        return []

    # Prefer the column produced by your extractor, else fall back to first column
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

    # de-duplicate
    seen = set()
    out = []
    for p in puzzles:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

@st.cache_data(show_spinner=False)
def fetch_url_bytes(url: str) -> bytes:
    """
    Download bytes from a URL with a User-Agent header (GitHub raw sometimes prefers it).
    Cached to avoid re-downloading on every rerun.
    """
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req) as resp:
        return resp.read()

def ensure_state():
    defaults = {
        "puzzles": [],
        "puzzle": "",
        "guessed": set(),
        "round_bank": 0,
        "total_bank": 0,
        "last_spin": None,
        "must_spin": True,
        "message": "Load words from GitHub to begin.",
        "lives": 5,
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
    st.session_state.message = "New puzzle loaded. Spin to start!"

ensure_state()

# =========================
# UI
# =========================
st.title("🎡 Wheel of Fortune")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("How to Play")

    with st.expander("📖 How Wheel of Fortune Works", expanded=False):
        st.markdown("""
### 🎯 Objective
Solve the puzzle by guessing letters and earn as much money as possible before you run out of lives.

---

### 🎡 Turn Flow
1. **Spin the Wheel**
   - You’ll land on a dollar amount, **BANKRUPT**, or **LOSE A TURN**
   - You must spin before guessing a consonant

2. **Guess a Consonant**
   - If the letter appears, you earn  
     **(# of occurrences) × (spin amount)**
   - If not, you lose **1 life**

3. **Buy a Vowel**
   - Costs the vowel cost shown below (default **$250**)
   - If the vowel is not in the puzzle, you lose **1 life**

4. **Solve the Puzzle**
   - Enter the full phrase at any time
   - A correct solve banks your round money
   - A wrong solve costs **1 life**

---

### 💣 Special Wheel Results
- **BANKRUPT** – Round money goes to **$0**
- **LOSE A TURN** – No penalty, spin again

---

### ❤️ Lives
You lose a life for:
- Wrong consonant
- Wrong vowel
- Incorrect solve

When lives reach **0**, the round ends.

---

### 🏁 Winning
- Reveal all letters, **or**
- Correctly solve the puzzle
""")

    st.divider()
    st.header("Load Words (GitHub)")

    # Default raw URL (you control the CSV location)
    default_csv_url = (
        "https://raw.githubusercontent.com/chad-k/GainSeeker-Wheel-of-Fortune/main/"
        "gainseeker_proper_nouns.csv"
    )

    csv_url = st.text_input("CSV Raw URL", value=default_csv_url)

    if st.button("Load Words from GitHub", use_container_width=True):
        try:
            data = fetch_url_bytes(csv_url)
            nouns = load_proper_nouns_from_csv_bytes(data)
            if nouns:
                st.session_state.puzzles = nouns
                st.success(f"Loaded {len(nouns)} puzzles!")
                st.caption("Sample:")
                st.write(nouns[:10])
                new_round(nouns)
                st.rerun()
            else:
                st.error("Downloaded the CSV, but found no valid puzzles (check CSV columns/content).")
        except Exception as e:
            st.error(f"Could not download/read CSV. Error: {e}")

    st.divider()
    st.header("Game Settings")
    st.session_state.lives = int(st.number_input("Lives", 1, 20, st.session_state.lives))
    vowel_cost = st.number_input("Vowel cost", 50, 500, 250, step=50)
    auto_next = st.checkbox("Auto next puzzle when solved", True)

    st.divider()
    if st.button("New Puzzle", disabled=not st.session_state.puzzles, use_container_width=True):
        new_round(st.session_state.puzzles)
        st.rerun()

# ---------- MAIN GAME ----------
if not st.session_state.puzzle:
    st.info("Click **Load Words from GitHub** in the sidebar to begin.")
    st.stop()

puzzle = st.session_state.puzzle
guessed = st.session_state.guessed

st.subheader("Puzzle")
st.markdown(
    f"<div style='font-size:48px; letter-spacing:4px; font-weight:700; text-align:center;'>"
    f"{mask_phrase(puzzle, guessed)}</div>",
    unsafe_allow_html=True
)

st.write(
    f"**Round:** ${st.session_state.round_bank} | "
    f"**Total:** ${st.session_state.total_bank} | "
    f"**Lives:** {st.session_state.lives}"
)
st.write(f"**Guessed:** {', '.join(sorted(guessed)) if guessed else '(none)'}")
st.info(st.session_state.message)

c1, c2, c3 = st.columns(3)

# ---------- SPIN ----------
with c1:
    if st.button("🎡 SPIN", use_container_width=True):
        if st.session_state.lives <= 0:
            st.session_state.message = "No lives left."
        else:
            result = random.choice(DEFAULT_WHEEL)
            st.session_state.last_spin = result
            if result == "BANKRUPT":
                st.session_state.round_bank = 0
                st.session_state.must_spin = True
                st.session_state.message = "💥 BANKRUPT! Spin again."
            elif result == "LOSE A TURN":
                st.session_state.must_spin = True
                st.session_state.message = "⏭️ LOSE A TURN! Spin again."
            else:
                st.session_state.must_spin = False
                st.session_state.message = f"Spun ${result}. Guess a consonant!"
        st.rerun()

# ---------- GUESS CONSONANT ----------
with c2:
    letter = st.text_input("Consonant", max_chars=1, key="cons").upper().strip()
    if st.button("Guess Consonant", use_container_width=True):
        if not letter or letter not in ALPHABET:
            st.session_state.message = "Enter A–Z."
        elif letter in guessed:
            st.session_state.message = f"{letter} already guessed."
        elif letter in VOWELS:
            st.session_state.message = "That's a vowel."
        elif st.session_state.must_spin:
            st.session_state.message = "Spin first!"
        else:
            guessed.add(letter)
            hits = count_letter(puzzle, letter)
            if hits:
                earned = hits * int(st.session_state.last_spin)
                st.session_state.round_bank += earned
                st.session_state.message = f"✅ {letter} ×{hits} = +${earned}"
            else:
                st.session_state.lives -= 1
                st.session_state.message = f"❌ No {letter}"
            st.session_state.must_spin = True
        st.rerun()

# ---------- BUY VOWEL ----------
with c3:
    vowel = st.text_input("Vowel", max_chars=1, key="vow").upper().strip()
    if st.button(f"Buy Vowel (-${vowel_cost})", use_container_width=True):
        if st.session_state.round_bank < vowel_cost:
            st.session_state.message = "Not enough money."
        elif vowel not in VOWELS:
            st.session_state.message = "Enter A, E, I, O, or U."
        elif vowel in guessed:
            st.session_state.message = f"{vowel} already guessed."
        else:
            st.session_state.round_bank -= vowel_cost
            guessed.add(vowel)
            hits = count_letter(puzzle, vowel)
            if hits == 0:
                st.session_state.lives -= 1
                st.session_state.message = f"❌ No {vowel}"
            else:
                st.session_state.message = f"✅ {vowel} ×{hits}"
        st.rerun()

st.divider()

# ---------- SOLVE ----------
solution = st.text_input("Solve the puzzle", key="solve").strip()
if st.button("Solve", use_container_width=False):
    if normalize_phrase(solution) == puzzle:
        st.session_state.total_bank += st.session_state.round_bank
        st.session_state.message = f"🎉 CORRECT! +${st.session_state.round_bank}"
        for ch in puzzle:
            if ch in ALPHABET:
                guessed.add(ch)
    else:
        st.session_state.lives -= 1
        st.session_state.message = "❌ Wrong answer."
    st.rerun()

# ---------- WIN CHECK ----------
if all((ch not in ALPHABET) or (ch in guessed) for ch in puzzle):
    st.success("✅ PUZZLE SOLVED!")
    if auto_next and st.button("Next Puzzle ▶️"):
        new_round(st.session_state.puzzles)
        st.rerun()
