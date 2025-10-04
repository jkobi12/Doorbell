import os
import io
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, date, time, timedelta

# ============== Helpers ==============
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
REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# ============== Shifts ==============
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
            df = pd.read_csv(LOG_PATH)
            for col in ["timestamp", "name", "username", "badge", "note", "shift"]:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            return pd.DataFrame(columns=["timestamp", "name", "username", "badge", "note", "shift"])
    return pd.DataFrame(columns=["timestamp", "name", "username", "badge", "note", "shift"])

def append_log(row_dict):
    df = load_log().copy()
    df.loc[len(df)] = row_dict
    df.to_csv(LOG_PATH, index=False)
    load_log.clear()

# ============== Admin Auth ==============
DEFAULT_USER = os.getenv("DOORBELL_ADMIN_USER", "admin")
DEFAULT_PASS = os.getenv("DOORBELL_ADMIN_PASS", "doorbell")

def is_authed():
    ss = st.session_state
    return ss.get("is_admin", False)

def show_login_box():
    with st.sidebar:
        st.subheader("Admin Login")
        with st.form("login_form", clear_on_submit=False):
            u = st.text_input("Username", value="", autocomplete="username")
            p = st.text_input("Password", value="", type="password", autocomplete="current-password")
            ok = st.form_submit_button("Sign in")
        if ok:
            if u == DEFAULT_USER and p == DEFAULT_PASS:
                st.session_state.is_admin = True
                st.success("Admin mode enabled.")
            else:
                st.error("Invalid credentials.")
        if st.button("Sign out", use_container_width=True):
            st.session_state.is_admin = False
            st.success("Signed out.")

# ============== PDF/Excel Utilities ==============
def df_to_excel_bytes(df: pd.DataFrame, filename_sheet="Rings") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=filename_sheet)
    buf.seek(0)
    return buf.getvalue()

def make_pdf_bytes(summary_text: str, table_df: pd.DataFrame) -> bytes:
    # Lightweight PDF using reportlab
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "Doorbell Daily Report")
    c.setFont("Helvetica", 10)
    c.drawString(72, height - 90, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Summary text
    text_obj = c.beginText(72, height - 120)
    text_obj.setFont("Helvetica", 11)
    for line in summary_text.splitlines():
        text_obj.textLine(line)
    c.drawText(text_obj)

    # Table (trim if too long)
    data = [list(table_df.columns)] + table_df.astype(str).values.tolist()
    max_rows = 25
    if len(data) > max_rows + 1:
        data = data[: max_rows + 1]
        data.append(["..."] + [""] * (len(table_df.columns) - 1))

    # Draw table manually
    from reportlab.platypus import Table, TableStyle
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
    ]))
    w, h = tbl.wrapOn(c, width-144, height-300)
    tbl.drawOn(c, 72, height - 150 - h)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# ============== Page Setup ==============
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

# Tabs
kiosk_tab, dashboard_tab = st.tabs(["Doorbell", "Dashboard 👀"])

# ---------- Kiosk Tab ----------
with kiosk_tab:
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

    # Session state
    ss = st.session_state
    if "trigger_ring" not in ss: ss.trigger_ring = False
    if "effective_shift" not in ss: ss.effective_shift = current_shift
    if "active_field" not in ss: ss.active_field = "badge_input"
    ss.setdefault("name_input", ""); ss.setdefault("username_input", "")
    ss.setdefault("badge_input", ""); ss.setdefault("note_input", "")
    ss.setdefault("caps_on", False); ss.setdefault("symbols_on", False)

    SPECIALS = {"SPACE": " ", "BACK": "<BACK>", "CLEAR": "<CLEAR>", "CAPS": "<CAPS>", "SYM": "<SYM>"}
    ALPHA_ROWS = [list("1234567890"), list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm")]
    EXTRA_KEYS = ["@", ".", "-", "_", "/"]
    SYMBOL_ROWS = [list("!@#$%^&*()"), list("~`|\\/?"), list("[]{}<>") , list(":;\"'.,+")]
    SYMBOL_EXTRA = ["=", "-", "_", "+"]

    def on_badge_scanned():
        val = ss.get("badge_input", "").strip()
        if len(val) >= 5:
            ss.trigger_ring = True

    def press_key(val: str):
        target_key = ss.active_field  # one of *_input
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

    # Inputs
    left, right = st.columns([1, 1])
    with left:
        st.markdown('<div class="label">Full name</div>', unsafe_allow_html=True)
        st.text_input("Full name", key="name_input", placeholder="Jane Doe", label_visibility="collapsed")
        st.markdown('<div class="label">Username / Login</div>', unsafe_allow_html=True)
        st.text_input("Username / Login", key="username_input", placeholder="jdoe", label_visibility="collapsed")
    with right:
        st.markdown('<div class="label">Scan your badge or type ID</div>', unsafe_allow_html=True)
        st.text_input("Badge ID", key="badge_input", on_change=on_badge_scanned, placeholder="(Scan barcode here)", label_visibility="collapsed")
        st.text_input("Optional note", key="note_input", placeholder="Where to meet, reason, etc.", label_visibility="collapsed")

    # Active field selector
    st.write("")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        if st.toggle("Type: Name", value=(ss.active_field == "name_input")): ss.active_field = "name_input"
    with fc2:
        if st.toggle("Type: Username", value=(ss.active_field == "username_input")): ss.active_field = "username_input"
    with fc3:
        if st.toggle("Type: Badge", value=(ss.active_field == "badge_input")): ss.active_field = "badge_input"
    with fc4:
        if st.toggle("Type: Note", value=(ss.active_field == "note_input")): ss.active_field = "note_input"

    # Keyboard
    st.subheader("On-screen Keyboard")
    mt1, mt2, mt3 = st.columns([1, 1, 6])
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

    # Ring handler
    should_ring = ring_clicked or ss.get("trigger_ring", False)
    _name = ss.get("name_input", ""); _username = ss.get("username_input", "")
    _badge = ss.get("badge_input", ""); _note = ss.get("note_input", "")
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

    # Sidebar (Admin)
    with st.sidebar:
        show_login_box()  # login/logout at top

        st.header("Admin")
        st.caption("Quick utilities for the person managing this station.")
        if is_authed():
            mode = st.radio("Shift mode", ["Auto", "Day", "Night"], index=0)
            if mode == "Auto": ss.effective_shift = detect_shift()
            else: ss.effective_shift = mode
            st.write("Effective shift:", ss.effective_shift)

            if st.button("Clear form fields"):
                for k in ["name_input", "username_input", "badge_input", "note_input"]:
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

    # Live clock tick on kiosk tab
    import time as _time
    _time.sleep(1)
    st.rerun()

# ---------- Dashboard Tab ----------
with dashboard_tab:
    st.subheader("Ring Log Dashboard")
    if not is_authed():
        st.warning("Admin access required. Please sign in from the sidebar.")
    else:
        df = load_log().copy()
        if not df.empty:
            df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["date"] = df["ts"].dt.date
            df["hour"] = df["ts"].dt.strftime("%H:00")
        else:
            df["ts"] = pd.NaT; df["date"] = None; df["hour"] = None

        # Filters
        c1, c2, c3 = st.columns([2,2,2])
        with c1:
            end = date.today(); start = end - timedelta(days=6)
            dr = st.date_input("Date range", value=(start, end))
        with c2:
            shifts = st.multiselect("Shifts", [s[0] for s in SHIFT_DEFS], default=[s[0] for s in SHIFT_DEFS])
        with c3:
            query = st.text_input("Search (name/username/badge/note)", placeholder="Type to filter…")

        # Apply filters
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
                    fdf["name"].astype(str).str.lower().str.contains(q, na=False)
                    | fdf["username"].astype(str).str.lower().str.contains(q, na=False)
                    | fdf["badge"].astype(str).str.lower().str.contains(q, na=False)
                    | fdf["note"].astype(str).str.lower().str.contains(q, na=False)
                )
                fdf = fdf[mask]

        # KPIs
        k1, k2, k3 = st.columns(3)
        with k1: st.metric("Total rings", len(fdf))
        with k2: st.metric("Day shift rings", int((fdf["shift"]=="Day").sum()) if not fdf.empty else 0)
        with k3: st.metric("Night shift rings", int((fdf["shift"]=="Night").sum()) if not fdf.empty else 0)

        st.dataframe(fdf.sort_values("ts", ascending=False).drop(columns=["ts"], errors="ignore"),
                     use_container_width=True)

        # Downloads
        csv_bytes = fdf.drop(columns=["ts"], errors="ignore").to_csv(index=False).encode("utf-8")
        st.download_button("Download filtered CSV", data=csv_bytes,
                           file_name="doorbell_filtered.csv", mime="text/csv")

        # Excel + PDF
        excel_bytes = df_to_excel_bytes(fdf.drop(columns=["ts"], errors="ignore"))
        st.download_button("Download filtered Excel",
                           data=excel_bytes,
                           file_name="doorbell_filtered.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Build a PDF report for the filtered view
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
            # save to reports/ and offer download
            path = os.path.join(REPORT_DIR, filename)
            with open(path, "wb") as f: f.write(pdf_bytes)
            st.success(f"Saved: {path}")
            st.download_button("Download PDF", data=pdf_bytes, file_name=filename, mime="application/pdf")

    st.caption("Tip: use search to quickly find a person or badge. PDF/Excel reflect the current filters.")

