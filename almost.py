import streamlit as st
import pandas as pd
from datetime import datetime
import numpy as np
import io
import os

# ------------------------------
# Helpers
# ------------------------------

def generate_tone(freq=880, duration=0.9, sample_rate=44100, volume=0.4):
    """Return a WAV byte stream for a sine tone.
    Browsers happily play this via st.audio()."""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * 2 * np.pi * t) * volume
    # Convert to 16-bit PCM WAV in-memory
    tone_int16 = np.int16(tone * 32767)
    import wave
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(tone_int16.tobytes())
    buf.seek(0)
    return buf.read()

LOG_PATH = "doorbell_log.csv"

# ------------------------------
# Shift configuration (customize here)
# ------------------------------
# Define shifts as (name, start, end) in 24h 'HH:MM'. If end < start it is an overnight shift.
SHIFT_DEFS = [
    ("Day", "06:00", "17:00"),       # 6:00 → 17:00
    ("Night", "17:30", "04:00"),     # 17:30 → 04:00 next day
]

from datetime import time

def _t(hhmm:str) -> time:
    hh, mm = map(int, hhmm.split(":"))
    return time(hh, mm)

def detect_shift(now=None):
    now = now or datetime.now()
    tnow = now.time()
    for name, s, e in SHIFT_DEFS:
        ts, te = _t(s), _t(e)
        if ts <= te:  # same-day
            if ts <= tnow < te:
                return name
        else:  # overnight
            if (tnow >= ts) or (tnow < te):
                return name
    return "Unscheduled"

@st.cache_data(show_spinner=False)
def load_log():
    if os.path.exists(LOG_PATH):
        try:
            return pd.read_csv(LOG_PATH)
        except Exception:
            return pd.DataFrame(columns=["timestamp","name","username","badge","note","shift"])
    return pd.DataFrame(columns=["timestamp","name","username","badge","note","shift"])
    return pd.DataFrame(columns=["timestamp","name","username","badge","note"])


def append_log(row_dict):
    df = load_log().copy()
    df.loc[len(df)] = row_dict
    df.to_csv(LOG_PATH, index=False)
    load_log.clear()  # reset cache

# ------------------------------
# UI
# ------------------------------
st.set_page_config(page_title="Doorbell | Scan or Type", layout="wide")

st.markdown(
    """
    <style>
    .bigbutton button {font-size: 28px; padding: 20px 0; border-radius: 18px; height:64px;}
    .kbdbox input {font-size: 22px !important; height: 64px;}
    .center {text-align:center}
    .label {font-weight:600; color:#555}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔔 Doorbell — ORH3 (Demo)")
current_shift = detect_shift()
st.caption(f"Scan your badge or enter your info, then press Ring. A tone will play and your entry is logged.  ")
st.info(f"Current shift: **{current_shift}**  | Day: 06:00–17:00  | Night: 17:30–04:00", icon="🕒")

# Session state for auto-submit and keyboard focus
if "trigger_ring" not in st.session_state:
    st.session_state.trigger_ring = False
if "active_field" not in st.session_state:
    st.session_state.active_field = "badge"  # default where keyboard types into

# storage bound to inputs so virtual keyboard can edit them
for key in ["name","username","badge","note"]:
    st.session_state.setdefault(key, "")


def on_badge_scanned():
    val = st.session_state.get("badge", "").strip()
    if len(val) >= 5:
        st.session_state.trigger_ring = True


# Virtual keyboard helpers
# State for keyboard modes
st.session_state.setdefault("caps_on", False)
st.session_state.setdefault("symbols_on", False)

ALPHA_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
EXTRA_KEYS = ["@", ".", "-", "_", "/"]

SYMBOL_ROWS = [
    list("!@#$%^&*()"),
    list("~`|\/?"),
    list("[]{}<>") ,
    list(":;\"'.,+")
]
SYMBOL_EXTRA = ["=", "-", "_", "+"]

SPECIALS = {"SPACE": " ", "BACK": "<BACK>", "CLEAR": "<CLEAR>", "CAPS": "<CAPS>", "SYM": "<SYM>"}


def press_key(val: str):
    # Mode switching
    if val == SPECIALS["CAPS"]:
        st.session_state.caps_on = not st.session_state.caps_on
        return
    if val == SPECIALS["SYM"]:
        st.session_state.symbols_on = not st.session_state.symbols_on
        return

    target = st.session_state.active_field
    current = st.session_state.get(target, "")
    if val == SPECIALS["BACK"]:
        st.session_state[target] = current[:-1]
    elif val == SPECIALS["CLEAR"]:
        st.session_state[target] = ""
    else:
        # apply CAPS for alphabetic keys only when symbols layer is off
        if (not st.session_state.symbols_on) and val.isalpha():
            val = val.upper() if st.session_state.caps_on else val.lower()
        st.session_state[target] = current + val



left, right = st.columns([1,1])
with left:
    st.markdown('<div class="label">Full name</div>', unsafe_allow_html=True)
    st.text_input("Full name", key="name", placeholder="Jane Doe", label_visibility="collapsed")
    st.markdown('<div class="label">Username / Login</div>', unsafe_allow_html=True)
    st.text_input("Username / Login", key="username", placeholder="jdoe", label_visibility="collapsed")
with right:
    st.markdown('<div class="label">Scan your badge or type ID</div>', unsafe_allow_html=True)
    st.text_input("Badge ID", key="badge", placeholder="(Scan barcode here)", on_change=on_badge_scanned, label_visibility="collapsed")
    st.text_input("Optional note", key="note", placeholder="Where to meet, reason, etc.", label_visibility="collapsed")

# Field focus selector for the on-screen keyboard
st.write("")
fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    if st.toggle("Type: Name", value=(st.session_state.active_field=="name")):
        st.session_state.active_field = "name"
with fc2:
    if st.toggle("Type: Username", value=(st.session_state.active_field=="username")):
        st.session_state.active_field = "username"
with fc3:
    if st.toggle("Type: Badge", value=(st.session_state.active_field=="badge")):
        st.session_state.active_field = "badge"
with fc4:
    if st.toggle("Type: Note", value=(st.session_state.active_field=="note")):
        st.session_state.active_field = "note"

# Render large on-screen keyboard
st.subheader("On‑screen Keyboard")
# Mode toggles row
mt1, mt2, mt3 = st.columns([1,1,6])
with mt1:
    cap_label = "CAPS ON" if st.session_state.caps_on else "Caps"
    if st.button(cap_label, key="k_caps", use_container_width=True):
        press_key(SPECIALS["CAPS"])
with mt2:
    sym_label = "!#1" if not st.session_state.symbols_on else "ABC"
    if st.button(sym_label, key="k_sym", use_container_width=True):
        press_key(SPECIALS["SYM"])
with mt3:
    if st.button("CLEAR", key="k_clear_top", use_container_width=True):
        press_key(SPECIALS["CLEAR"])

# Choose layout based on symbols mode
rows = SYMBOL_ROWS if st.session_state.symbols_on else ALPHA_ROWS
for ridx, row in enumerate(rows):
    cols = st.columns(len(row))
    for idx, ch in enumerate(row):
        # Render uppercase on buttons when caps on (alpha layer only)
        label = ch
        if not st.session_state.symbols_on and ch.isalpha() and st.session_state.caps_on:
            label = ch.upper()
        with cols[idx]:
            if st.button(label, key=f"k_{label}_{ridx}_{idx}", use_container_width=True):
                press_key(ch)
# Extras and actions
extra = (SYMBOL_EXTRA if st.session_state.symbols_on else EXTRA_KEYS) + [" "]
cols = st.columns(len(extra)+2)
for i, ch in enumerate(extra):
    with cols[i]:
        if st.button(ch, key=f"k_extra_{ch}_{i}", use_container_width=True):
            press_key(ch if ch != "SPACE" else SPECIALS["SPACE"])
with cols[len(extra)]:
    if st.button("BACK", key="k_back", use_container_width=True):
        press_key(SPECIALS["BACK"])
with cols[len(extra)+1]:
    if st.button("SPACE", key="k_space", use_container_width=True):
        press_key(SPECIALS["SPACE"])

ring_clicked = st.button("🔔 Ring", use_container_width=True)

# Conditions that trigger the bell: button click OR scanner auto trigger
should_ring = ring_clicked or st.session_state.get("trigger_ring", False)

# Pull current field values from session_state
_name = st.session_state.get("name", "")
_username = st.session_state.get("username", "")
_badge = st.session_state.get("badge", "")
_note = st.session_state.get("note", "")

missing_all = (not _name.strip()) and (not _username.strip()) and (not _badge.strip())

if should_ring:
    if missing_all:
        st.error("Please provide at least a name, username, or a scanned badge.")
    else:
        st.success("Bell rung! Someone will be with you shortly.")
        st.write(":clock1: ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        st.audio(generate_tone(), format="audio/wav")

        append_log({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "name": _name.strip(),
            "username": _username.strip(),
            "badge": _badge.strip(),
            "note": _note.strip(),
            "shift": st.session_state.get("effective_shift", detect_shift()),
        })

        st.session_state.trigger_ring = False

st.divider()

with st.expander("Recent rings", expanded=True):
    log_df = load_log()
    if len(log_df) == 0:
        st.info("No rings yet.")
    else:
        st.dataframe(log_df.tail(20), use_container_width=True)
        st.download_button(
            "Download log (CSV)",
            data=log_df.to_csv(index=False).encode("utf-8"),
            file_name="doorbell_log.csv",
            mime="text/csv",
        )

# Optional: admin clear
with st.sidebar:
    st.header("Admin")
    st.caption("Quick utilities for the person managing this station.")

    # Shift override
    mode = st.radio("Shift mode", ["Auto","Day","Night"], index=0)
    if mode == "Auto":
        st.session_state["effective_shift"] = detect_shift()
    else:
        st.session_state["effective_shift"] = mode
    st.write("Effective shift:", st.session_state["effective_shift"])

    if st.button("Clear form fields"):
        for k in ["badge",]:
            if k in st.session_state:
                st.session_state[k] = ""
        st.rerun()
    if st.button("Reset log (start fresh)"):
        try:
            if os.path.exists(LOG_PATH):
                os.remove(LOG_PATH)
                load_log.clear()
            st.success("Log cleared.")
        except Exception as e:
            st.error(f"Couldn't clear log: {e}")

st.markdown("""
---
**Tips**
- Most barcode badge scanners act like a keyboard and end with **Enter**. Focus the *Badge ID* field and scan — the bell will auto-trigger.
- Save this page fullscreen for a kiosk-like experience. Attach speakers for a louder chime.
- Change the title/location text at the top to match your site.
""")
