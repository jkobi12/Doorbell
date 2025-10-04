import streamlit as st
import pandas as pd
from datetime import datetime, time
import numpy as np
import io
import os

# ==============================
# Helpers
# ==============================

def generate_tone(freq=880, duration=0.9, sample_rate=44100, volume=0.4):
    """Return a WAV byte stream for a sine tone (for st.audio)."""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * 2 * np.pi * t) * volume
    tone_int16 = np.int16(tone * 32767)
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(tone_int16.tobytes())
    buf.seek(0)
    return buf.read()

LOG_PATH = "doorbell_log.csv"

# ==============================
# Shift configuration
# ==============================
# Define shifts as (name, start, end) in 24h 'HH:MM'. If end < start it's overnight.
SHIFT_DEFS = [
    ("Day", "06:00", "17:00"),
    ("Night", "17:30", "04:00"),
]

def _t(hhmm: str) -> time:
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
            return pd.DataFrame(columns=["timestamp", "name", "username", "badge", "note", "shift"])
    return pd.DataFrame(columns=["timestamp", "name", "username", "badge", "note", "shift"])

def append_log(row_dict):
    df = load_log().copy()
    df.loc[len(df)] = row_dict
    df.to_csv(LOG_PATH, index=False)
    load_log.clear()  # reset cache

# ==============================
# Page setup
# ==============================
st.set_page_config(page_title="Doorbell | Scan or Type", layout="wide")

st.markdown(
    """
    <style>
    .bigbutton button {font-size: 28px; padding: 20px 0; border-radius: 18px; height:64px;}
    .kbdbox input {font-size: 22px !important; height: 64px;}
    .center {text-align:center}
    .label {font-weight:600; color:#bbb}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔔 Doorbell — ORH3 (Demo)")

# Header with live clock on right
hdr_left, hdr_right = st.columns([3, 1])
with hdr_right:
    now = datetime.now()
    st.markdown(
        f"<div style='text-align:right; font-size:28px; font-weight:700;'>"
        f"{now.strftime('%I:%M:%S %p')}<br><span style='font-size:14px; font-weight:500;'>"
        f"{now.strftime('%A, %b %d, %Y')}</span></div>",
        unsafe_allow_html=True,
    )

current_shift = detect_shift()
st.caption("Scan your badge or enter your info, then press Ring. A tone will play and your entry is logged.")
st.info(f"Current shift: **{current_shift}**  | Day: 06:00–17:00  | Night: 17:30–04:00", icon="🕒")

# ==============================
# Session state init
# ==============================
ss = st.session_state
if "trigger_ring" not in ss:
    ss.trigger_ring = False
if "effective_shift" not in ss:
    ss.effective_shift = current_shift
if "active_field" not in ss:
    ss.active_field = "badge_input"  # default focus for on-screen keyboard
# Widget values (actual single source of truth for inputs)
ss.setdefault("name_input", "")
ss.setdefault("username_input", "")
ss.setdefault("badge_input", "")
ss.setdefault("note_input", "")
# Keyboard modes
ss.setdefault("caps_on", False)
ss.setdefault("symbols_on", False)

# ==============================
# Callbacks
# ==============================
SPECIALS = {"SPACE": " ", "BACK": "<BACK>", "CLEAR": "<CLEAR>", "CAPS": "<CAPS>", "SYM": "<SYM>"}

ALPHA_ROWS = [list("1234567890"), list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm")]
EXTRA_KEYS = ["@", ".", "-", "_", "/"]
SYMBOL_ROWS = [list("!@#$%^&*()"), list("~`|\/?"), list("[]{}<>") , list(":;\"'.,+")]
SYMBOL_EXTRA = ["=", "-", "_", "+"]

def on_badge_scanned():
    val = ss.get("badge_input", "").strip()
    if len(val) >= 5:
        ss.trigger_ring = True

def press_key(val: str):
    target_key = ss.active_field  # one of name_input, username_input, badge_input, note_input
    if val == SPECIALS["CAPS"]:
        ss.caps_on = not ss.caps_on
        return
    if val == SPECIALS["SYM"]:
        ss.symbols_on = not ss.symbols_on
        return

    current = ss.get(target_key, "")
    if val == SPECIALS["BACK"]:
        ss[target_key] = current[:-1]
    elif val == SPECIALS["CLEAR"]:
        ss[target_key] = ""
    else:
        if (not ss.symbols_on) and val.isalpha():
            val = val.upper() if ss.caps_on else val.lower()
        ss[target_key] = current + val

# ==============================
# Inputs
# ==============================
left, right = st.columns([1, 1])
with left:
    st.markdown('<div class="label">Full name</div>', unsafe_allow_html=True)
    st.text_input(
        "Full name",
        key="name_input",
        placeholder="Jane Doe",
        label_visibility="collapsed",
    )
    st.markdown('<div class="label">Username / Login</div>', unsafe_allow_html=True)
    st.text_input(
        "Username / Login",
        key="username_input",
        placeholder="jdoe",
        label_visibility="collapsed",
    )
with right:
    st.markdown('<div class="label">Scan your badge or type ID</div>', unsafe_allow_html=True)
    st.text_input(
        "Badge ID",
        key="badge_input",
        on_change=on_badge_scanned,
        placeholder="(Scan barcode here)",
        label_visibility="collapsed",
    )
    st.text_input(
        "Optional note",
        key="note_input",
        placeholder="Where to meet, reason, etc.",
        label_visibility="collapsed",
    )

# Active field selector
st.write("")
fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    if st.toggle("Type: Name", value=(ss.active_field == "name_input")):
        ss.active_field = "name_input"
with fc2:
    if st.toggle("Type: Username", value=(ss.active_field == "username_input")):
        ss.active_field = "username_input"
with fc3:
    if st.toggle("Type: Badge", value=(ss.active_field == "badge_input")):
        ss.active_field = "badge_input"
with fc4:
    if st.toggle("Type: Note", value=(ss.active_field == "note_input")):
        ss.active_field = "note_input"

# ==============================
# On‑screen keyboard
# ==============================
st.subheader("On‑screen Keyboard")
mt1, mt2, mt3 = st.columns([1, 1, 6])
with mt1:
    st.button(
        "CAPS ON" if ss.caps_on else "Caps",
        key="k_caps",
        use_container_width=True,
        on_click=press_key,
        args=(SPECIALS["CAPS"],),
    )
with mt2:
    st.button(
        "!#1" if not ss.symbols_on else "ABC",
        key="k_sym",
        use_container_width=True,
        on_click=press_key,
        args=(SPECIALS["SYM"],),
    )
with mt3:
    st.button("CLEAR", key="k_clear_top", use_container_width=True, on_click=press_key, args=(SPECIALS["CLEAR"],))

rows = SYMBOL_ROWS if ss.symbols_on else ALPHA_ROWS
for ridx, row in enumerate(rows):
    cols = st.columns(len(row))
    for idx, ch in enumerate(row):
        label = ch.upper() if (not ss.symbols_on and ch.isalpha() and ss.caps_on) else ch
        with cols[idx]:
            st.button(
                label,
                key=f"k_{label}_{ridx}_{idx}",
                use_container_width=True,
                on_click=press_key,
                args=(ch,),
            )

extra = (SYMBOL_EXTRA if ss.symbols_on else EXTRA_KEYS)
cols = st.columns(len(extra) + 2)
for i, ch in enumerate(extra):
    with cols[i]:
        st.button(ch, key=f"k_extra_{ch}_{i}", use_container_width=True, on_click=press_key, args=(ch,))
with cols[len(extra)]:
    st.button("BACK", key="k_back", use_container_width=True, on_click=press_key, args=(SPECIALS["BACK"],))
with cols[len(extra) + 1]:
    st.button("SPACE", key="k_space", use_container_width=True, on_click=press_key, args=(SPECIALS["SPACE"],))

ring_clicked = st.button("🔔 Ring", use_container_width=True)

# ==============================
# Ring handler
# ==============================
should_ring = ring_clicked or ss.get("trigger_ring", False)
_name = ss.get("name_input", "")
_username = ss.get("username_input", "")
_badge = ss.get("badge_input", "")
_note = ss.get("note_input", "")

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
            "shift": ss.get("effective_shift", detect_shift()),
        })
        ss.trigger_ring = False

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

# ==============================
# Sidebar admin
# ==============================
with st.sidebar:
    st.header("Admin")
    st.caption("Quick utilities for the person managing this station.")
    mode = st.radio("Shift mode", ["Auto", "Day", "Night"], index=0)
    if mode == "Auto":
        ss.effective_shift = detect_shift()
    else:
        ss.effective_shift = mode
    st.write("Effective shift:", ss.effective_shift)

    if st.button("Clear form fields"):
        for k in ["name_input", "username_input", "badge_input", "note_input"]:
            ss[k] = ""
        st.rerun()

    if st.button("Reset log (start fresh)"):
        try:
            if os.path.exists(LOG_PATH):
                os.remove(LOG_PATH)
                load_log.clear()
            st.success("Log cleared.")
        except Exception as e:
            st.error(f"Couldn't clear log: {e}")

st.markdown(
    """
---
**Tips**
- Most barcode badge scanners act like a keyboard and end with **Enter**. Focus the *Badge ID* field and scan — the bell will auto-trigger.
- Save this page fullscreen for a kiosk-like experience. Attach speakers for a louder chime.
- Change the title/location text at the top to match your site.
    """
)

# Live clock tick
import time as _time
_time.sleep(1)
st.rerun()
