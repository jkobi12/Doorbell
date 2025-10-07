# activate_this.py
import os
import io
import sys
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, date, time, timedelta

# ───────────────────────────────────────────────────────────────────────────────
# Paths & constants
# ───────────────────────────────────────────────────────────────────────────────
LOG_PATH = "doorbell_log.csv"
REPORT_DIR = "reports"
PHOTOS_DIR = "photos"
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)

# Shifts (name, start, end) in 24h HH:MM; if end < start => overnight
SHIFT_DEFS = [
    ("Day", "06:00", "17:00"),
    ("Night", "17:30", "04:00"),
]

# Admin creds (override via env vars)
ADMIN_USER = os.getenv("DOORBELL_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("DOORBELL_ADMIN_PASS", "doorbell")

# If True, user must take a photo before they can ring
REQUIRE_PHOTO = False


# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────
def _t(hhmm: str) -> time:
    h, m = map(int, hhmm.split(":"))
    return time(h, m)

def detect_shift(now=None):
    now = now or datetime.now()
    tnow = now.time()
    for name, s, e in SHIFT_DEFS:
        ts, te = _t(s), _t(e)
        if ts <= te:
            if ts <= tnow < te:
                return name
        else:  # overnight
            if (tnow >= ts) or (tnow < te):
                return name
    return "Unscheduled"

def generate_tone(freq=880, duration=0.9, sample_rate=44100, volume=0.4):
    """Return a WAV byte stream for st.audio"""
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

@st.cache_data(show_spinner=False)
def load_log():
    cols = ["timestamp","name","username","badge","note","shift","photo"]
    if os.path.exists(LOG_PATH):
        try:
            df = pd.read_csv(LOG_PATH)
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            return df
        except Exception:
            return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)

def append_log(row_dict: dict):
    df = load_log().copy()
    df.loc[len(df)] = row_dict
    df.to_csv(LOG_PATH, index=False)
    load_log.clear()

def df_to_excel_bytes(df: pd.DataFrame, sheet="Rings") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name=sheet)
    buf.seek(0)
    return buf.getvalue()

def make_pdf_bytes(summary_text: str, table_df: pd.DataFrame) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "Doorbell Report")
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 90, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    t = c.beginText(72, height - 120)
    t.setFont("Helvetica", 11)
    for line in summary_text.splitlines():
        t.textLine(line)
    c.drawText(t)

    data = [list(table_df.columns)] + table_df.astype(str).values.tolist()
    if len(data) > 26:
        data = data[:26]
        data.append(["..."] + [""]*(len(table_df.columns)-1))
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.lightgrey),
        ("GRID",(0,0),(-1,-1), 0.25, colors.grey),
        ("FONT",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1), 8),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),
    ]))
    w,h = tbl.wrapOn(c, width-144, height-300)
    tbl.drawOn(c, 72, height - 150 - h)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


# ───────────────────────────────────────────────────────────────────────────────
# Page config & base UI
# ───────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Doorbell | Scan or Type", layout="wide")
st.markdown("""
<style>
.bigbutton button {font-size: 28px; padding: 20px 0; border-radius: 18px; height:64px;}
.kbdbox input {font-size: 22px !important; height: 64px;}
.center {text-align:center}
.label {font-weight:600; color:#bbb}
.active {border: 2px solid #22c55e; border-radius: 10px; padding: 2px;}
</style>
""", unsafe_allow_html=True)
st.title("🔔 Doorbell — ORH3 (Demo)")

kiosk_tab, dashboard_tab = st.tabs(["Doorbell", "Dashboard 👀"])

# ───────────────────────────────────────────────────────────────────────────────
# Kiosk tab
# ───────────────────────────────────────────────────────────────────────────────
with kiosk_tab:
    # Live clock
    lc1, lc2 = st.columns([3,1])
    with lc2:
        now = datetime.now()
        st.markdown(
            f"<div style='text-align:right; font-size:28px; font-weight:700;'>"
            f"{now.strftime('%I:%M:%S %p')}<br>"
            f"<span style='font-size:14px; font-weight:500;'>{now.strftime('%A, %b %d, %Y')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    current_shift = detect_shift()
    # --- Camera block (smaller size for space) ---
    st.markdown("### Camera")
    cam_col, help_col = st.columns([1.2, 2])

    with cam_col:
        st.markdown(
            """
            <style>
            div[data-testid="stCameraInput"] video {
                width: 160px !important;
                height: 120px !important;
                object-fit: cover;
                border-radius: 10px;
            }
            div[data-testid="stCameraInput"] button {
                font-size: 12px !important;
                padding: 4px 8px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        photo = st.camera_input(
            "Tap **Take photo** to arm camera",
            key="cam_input",
        )
        if photo is not None:
            ss.last_photo_bytes = photo.getvalue()

    with help_col:
        st.caption(
            "When a visitor scans a badge, types their info, and taps **Ring**, "
            "the most recent photo (on the left) is saved automatically. "
            "Camera preview is now compact to save space."
        )

    st.info(f"Current shift: **{current_shift}**  | Day: 06:00–17:00  | Night: 17:30–04:00", icon="🕒")

    # Session state
    ss = st.session_state
    ss.setdefault("trigger_ring", False)
    ss.setdefault("effective_shift", current_shift)
    ss.setdefault("active_field", "badge_input")  # default keyboard target
    ss.setdefault("name_input", ""); ss.setdefault("username_input", "")
    ss.setdefault("badge_input", ""); ss.setdefault("note_input", "")
    ss.setdefault("caps_on", False); ss.setdefault("symbols_on", False)
    ss.setdefault("last_photo_bytes", None)

    # Keep the latest camera photo in session (after user clicks Take photo)
    if photo is not None:
        ss.last_photo_bytes = photo.getvalue()

    # Callbacks & keyboard config
    SPECIALS = {"SPACE":" ", "BACK":"<BACK>", "CLEAR":"<CLEAR>", "CAPS":"<CAPS>", "SYM":"<SYM>"}
    ALPHA_ROWS = [list("1234567890"), list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm")]
    EXTRA_KEYS = ["@", ".", "-", "_", "/"]
    SYMBOL_ROWS = [list("!@#$%^&*()"), list("~`|\\/?"), list("[]{}<>"), list(":;\"'.,+")]
    SYMBOL_EXTRA = ["=", "-", "_", "+"]

    def on_badge_scanned():
        val = ss.get("badge_input", "").strip()
        if len(val) >= 5:
            ss.trigger_ring = True

    def press_key(val: str):
        target_key = ss.active_field
        if val == SPECIALS["CAPS"]:
            ss.caps_on = not ss.caps_on; return
        if val == SPECIALS["SYM"]:
            ss.symbols_on = not ss.symbols_on; return

        current = ss.get(target_key, "")
        if val == SPECIALS["BACK"]:
            ss[target_key] = current[:-1]
        elif val == SPECIALS["CLEAR"]:
            ss[target_key] = ""
        else:
            if (not ss.symbols_on) and val.isalpha():
                val = val.upper() if ss.caps_on else val.lower()
            ss[target_key] = current + val

    def set_target(key_name: str):
        """Set which text input the on-screen keyboard should type into."""
        ss.active_field = key_name

    # Inputs with "Type here" targeting buttons
    left, right = st.columns([1,1])
    with left:
        st.markdown('<div class="label">Full name</div>', unsafe_allow_html=True)
        n1, n2 = st.columns([0.8, 0.2])
        with n1:
            st.text_input("Full name", key="name_input", placeholder="Jane Doe",
                          label_visibility="collapsed")
        with n2:
            st.button("⌨️ Type here", key="t_name", use_container_width=True,
                      on_click=set_target, args=("name_input",))

        st.markdown('<div class="label">Username / Login</div>', unsafe_allow_html=True)
        u1, u2 = st.columns([0.8, 0.2])
        with u1:
            st.text_input("Username / Login", key="username_input", placeholder="jdoe",
                          label_visibility="collapsed")
        with u2:
            st.button("⌨️ Type here", key="t_user", use_container_width=True,
                      on_click=set_target, args=("username_input",))

    with right:
        st.markdown('<div class="label">Scan your badge or type ID</div>', unsafe_allow_html=True)
        b1, b2 = st.columns([0.8, 0.2])
        with b1:
            st.text_input("Badge ID", key="badge_input", on_change=on_badge_scanned,
                          placeholder="(Scan barcode here)", label_visibility="collapsed")
        with b2:
            st.button("⌨️ Type here", key="t_badge", use_container_width=True,
                      on_click=set_target, args=("badge_input",))

        st.markdown('<div class="label">Where to meet, reason, etc.</div>', unsafe_allow_html=True)
        m1, m2 = st.columns([0.8, 0.2])
        with m1:
            st.text_input("Where to meet, reason, etc.", key="note_input",
                          placeholder="Optional note", label_visibility="collapsed")
        with m2:
            st.button("⌨️ Type here", key="t_note", use_container_width=True,
                      on_click=set_target, args=("note_input",))

    # Keyboard target control
    labels = {"name_input":"Name","username_input":"Username","badge_input":"Badge","note_input":"Note"}
    order  = ["name_input","username_input","badge_input","note_input"]
    current_idx = order.index(ss.active_field) if ss.active_field in order else 2
    target = st.radio("Keyboard target", options=order, index=current_idx,
                      format_func=lambda k: labels[k], horizontal=True)
    if target != ss.active_field:
        ss.active_field = target

    # Keyboard UI
    st.subheader("On-screen Keyboard")
    mt1, mt2, mt3 = st.columns([1,1,6])
    with mt1:
        st.button("CAPS ON" if ss.caps_on else "Caps", key="k_caps", use_container_width=True,
                  on_click=press_key, args=(SPECIALS["CAPS"],))
    with mt2:
        st.button("!#1" if not ss.symbols_on else "ABC", key="k_sym", use_container_width=True,
                  on_click=press_key, args=(SPECIALS["SYM"],))
    with mt3:
        st.button("CLEAR", key="k_clear_top", use_container_width=True,
                  on_click=press_key, args=(SPECIALS["CLEAR"],))

    rows = SYMBOL_ROWS if ss.symbols_on else ALPHA_ROWS
    for ridx, row in enumerate(rows):
        cols = st.columns(len(row))
        for idx, ch in enumerate(row):
            label = ch.upper() if (not ss.symbols_on and ch.isalpha() and ss.caps_on) else ch
            with cols[idx]:
                st.button(label, key=f"k_{label}_{ridx}_{idx}", use_container_width=True,
                          on_click=press_key, args=(ch,))

    extra = SYMBOL_EXTRA if ss.symbols_on else EXTRA_KEYS
    cols = st.columns(len(extra)+2)
    for i, ch in enumerate(extra):
        with cols[i]:
            st.button(ch, key=f"k_extra_{ch}_{i}", use_container_width=True,
                      on_click=press_key, args=(ch,))
    with cols[len(extra)]:
        st.button("BACK", key="k_back", use_container_width=True,
                  on_click=press_key, args=(SPECIALS["BACK"],))
    with cols[len(extra)+1]:
        st.button("SPACE", key="k_space", use_container_width=True,
                  on_click=press_key, args=(SPECIALS["SPACE"],))

    ring_clicked = st.button("🔔 Ring", use_container_width=True)

    # Ring handler
    should_ring = ring_clicked or ss.get("trigger_ring", False)
    _name = ss.get("name_input",""); _username = ss.get("username_input","")
    _badge = ss.get("badge_input",""); _note = ss.get("note_input","")
    missing_all = (not _name.strip()) and (not _username.strip()) and (not _badge.strip())

    if should_ring:
        if missing_all:
            st.error("Please provide at least a name, username, or a scanned badge.")
        elif REQUIRE_PHOTO and not ss.get("last_photo_bytes"):
            st.error("Please take a photo before ringing.")
        else:
            # Save photo if captured
            photo_path = ""
            if ss.get("last_photo_bytes"):
                ident = _badge or _username or _name or "visitor"
                ident = "".join(ch for ch in ident if ch.isalnum() or ch in ("-","_"))[:30]
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                photo_path = os.path.join(PHOTOS_DIR, f"{ts}_{ident}.jpg")
                try:
                    with open(photo_path, "wb") as f:
                        f.write(ss.last_photo_bytes)
                except Exception as e:
                    st.warning(f"Photo save failed: {e}")
                    photo_path = ""

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
                "photo": photo_path,
            })
            if photo_path:
                st.image(photo_path, caption="Saved photo", width=220)
            ss.trigger_ring = False

    st.divider()
    with st.expander("Recent rings", expanded=True):
        log_df = load_log()
        if log_df.empty:
            st.info("No rings yet.")
        else:
            st.dataframe(log_df.tail(20), use_container_width=True)
            st.download_button(
                "Download log (CSV)",
                data=log_df.to_csv(index=False).encode("utf-8"),
                file_name="doorbell_log.csv",
                mime="text/csv",
            )

    # Sidebar: Admin
    with st.sidebar:
        st.subheader("Admin Login")
        if not ss.get("is_admin", False):
            with st.form("login_form", clear_on_submit=False):
                u = st.text_input("Username", value="", autocomplete="username")
                p = st.text_input("Password", value="", type="password", autocomplete="current-password")
                ok = st.form_submit_button("Sign in")
            if ok:
                if u == ADMIN_USER and p == ADMIN_PASS:
                    ss.is_admin = True
                    st.success("Admin mode enabled.")
                else:
                    st.error("Invalid credentials.")
        else:
            if st.button("Sign out", use_container_width=True):
                ss.is_admin = False
                st.rerun()

        st.header("Admin")
        st.caption("Quick utilities for the person managing this station.")
        if ss.get("is_admin", False):
            mode = st.radio("Shift mode", ["Auto","Day","Night"], index=0)
            ss.effective_shift = detect_shift() if mode=="Auto" else mode
            st.write("Effective shift:", ss.effective_shift)

            if st.button("Clear form fields"):
                for k in ["name_input","username_input","badge_input","note_input"]:
                    ss[k] = ""
                st.rerun()

            if st.button("Reset log (start fresh)"):
                try:
                    if os.path.exists(LOG_PATH):
                        os.remove(LOG_PATH); load_log.clear()
                    st.success("Log cleared.")
                except Exception as e:
                    st.error(f"Couldn't clear log: {e}")
        else:
            st.info("Sign in to access admin tools.")

    # Live clock tick refresh
    import time as _time
    _time.sleep(1)
    st.rerun()


# ───────────────────────────────────────────────────────────────────────────────
# Dashboard tab (admin only)
# ───────────────────────────────────────────────────────────────────────────────
with dashboard_tab:
    st.subheader("Ring Log Dashboard")
    if not st.session_state.get("is_admin", False):
        st.warning("Admin access required. Please sign in from the sidebar.")
    else:
        df = load_log().copy()
        if not df.empty:
            df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["date"] = df["ts"].dt.date
            df["hour"] = df["ts"].dt.strftime("%H:00")
        else:
            df["ts"] = pd.NaT; df["date"] = None; df["hour"] = None

        c1, c2, c3 = st.columns([2,2,2])
        with c1:
            end = date.today(); start = end - timedelta(days=6)
            dr = st.date_input("Date range", value=(start, end))
        with c2:
            shifts = st.multiselect("Shifts", [s[0] for s in SHIFT_DEFS], default=[s[0] for s in SHIFT_DEFS])
        with c3:
            query = st.text_input("Search (name/username/badge/note)", placeholder="Type to filter…")

        fdf = df.copy()
        if not fdf.empty:
            if isinstance(dr, tuple) and len(dr) == 2:
                s, e = dr
                fdf = fdf[(fdf["date"] >= s) & (fdf["date"] <= e)]
            if shifts:
                fdf = fdf[fdf["shift"].isin(shifts)]
            if query:
                q = query.lower()
                mask = (
                    fdf["name"].astype(str).str.lower().str.contains(q, na=False) |
                    fdf["username"].astype(str).str.lower().str.contains(q, na=False) |
                    fdf["badge"].astype(str).str.lower().str.contains(q, na=False) |
                    fdf["note"].astype(str).str.lower().str.contains(q, na=False)
                )
                fdf = fdf[mask]

        k1, k2, k3 = st.columns(3)
        with k1: st.metric("Total rings", len(fdf))
        with k2: st.metric("Day shift rings", int((fdf["shift"]=="Day").sum()) if not fdf.empty else 0)
        with k3: st.metric("Night shift rings", int((fdf["shift"]=="Night").sum()) if not fdf.empty else 0)

        st.dataframe(fdf.sort_values("ts", ascending=False).drop(columns=["ts"], errors="ignore"),
                     use_container_width=True)

        csv_bytes   = fdf.drop(columns=["ts"], errors="ignore").to_csv(index=False).encode("utf-8")
        excel_bytes = df_to_excel_bytes(fdf.drop(columns=["ts"], errors="ignore"))
        st.download_button("Download filtered CSV", data=csv_bytes,
                           file_name="doorbell_filtered.csv", mime="text/csv")
        st.download_button("Download filtered Excel", data=excel_bytes,
                           file_name="doorbell_filtered.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if st.button("Generate PDF report for filtered view"):
            summary = [
                f"Date range: {dr[0]} to {dr[1]}",
                f"Total rings: {len(fdf)}",
                f"Day shift: {int((fdf['shift']=='Day').sum()) if not fdf.empty else 0}",
                f"Night shift: {int((fdf['shift']=='Night').sum()) if not fdf.empty else 0}",
                f"Generated: {datetime.now().isoformat(timespec='seconds')}",
            ]
            pdf_bytes = make_pdf_bytes("\n".join(summary), fdf.drop(columns=["ts"], errors="ignore"))
            filename = f"report_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            path = os.path.join(REPORT_DIR, filename)
            with open(path, "wb") as f: f.write(pdf_bytes)
            st.success(f"Saved: {path}")
            st.download_button("Download PDF", data=pdf_bytes, file_name=filename, mime="application/pdf")

    st.caption("Tip: use search to quickly find a person or badge. PDF/Excel reflect the current filters.")
