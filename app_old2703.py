import os
import re
import urllib.parse
from datetime import datetime, date
from io import BytesIO
from pathlib import Path

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
st.write(st.secrets["gsheets"]["spreadsheet_name"])
st.write(st.secrets["gcp_service_account"]["client_email"])
from google.oauth2.service_account import Credentials
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Monitoring Disposisi",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = APP_DIR / "uploads"
DISP_DIR = UPLOAD_DIR / "disposisi"
OUT_DIR = UPLOAD_DIR / "output"

STATUS_OPTIONS = ["Not Yet Started", "On Progress", "Review", "Done", "Cancel", "Blocked"]
APPROVAL_OPTIONS = ["Pending Approval", "Approved", "Rejected"]

DEFAULT_USERS = [
    ("admin", "admin123", "admin"),
    ("atasan", "atasan123", "atasan"),
]

USERS_HEADERS = ["username", "password", "role", "display_name", "active"]
TASKS_HEADERS = [
    "id",
    "judul",
    "tim",
    "pic_list",
    "wa_pic",
    "deadline",
    "progress",
    "status",
    "instruksi",
    "instruksi_file",
    "output_file",
    "catatan",
    "update_terakhir",
    "created_at",
    "approval_status",
    "approved_by",
    "approved_at",
]
AUDIT_HEADERS = ["id", "task_id", "user", "action", "timestamp"]

st.markdown(
    """
<style>
:root{
  --ink:#0f172a;
  --muted:#64748b;
  --card:#ffffff;
  --line:#e5e7eb;
  --accent:#f97316;
  --navy:#0b3a4a;
  --bg:#f6f8fb;
}
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  background: var(--bg) !important;
  color: var(--ink) !important;
}
[data-testid="stSidebar"] { background: #ffffff !important; }
.block-container { padding-top: 1rem; padding-bottom: 1.4rem; max-width: 1280px; }
.h-title{font-size:clamp(1.4rem, 2vw, 2.2rem); font-weight:900; color:var(--ink); margin:0;}
.h-sub{color:var(--muted); margin:4px 0 14px 0; font-size:13px;}
.card{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:12px 14px; box-shadow:0 4px 12px rgba(15,23,42,.04); }
.kpi-row{display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin-top:8px;}
.kpi{background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px;}
.kpi .k{color:var(--muted); font-size:12px}
.kpi .v{color:var(--ink); font-size:24px; font-weight:900; margin-top:4px}
.section-title{font-weight:900; color:var(--ink); margin:0 0 8px 0; font-size:16px;}
.small{color:var(--muted); font-size:12px}
.deadline-pill{ display:inline-block; padding:6px 10px; border-radius:999px; font-size:15px; font-weight:900; border:1px solid #fed7aa; background:#fff7ed; color:#9a3412; }
.deadline-pill.overdue{ border-color:#fecaca; background:#fef2f2; color:#b91c1c; }
.deadline-pill.safe{ border-color:#dbeafe; background:#eff6ff; color:#1d4ed8; }
.mobile-note{ color:var(--muted); font-size:12px; margin-top:4px; }
@media (max-width: 768px) {
  .block-container {padding-left: .7rem; padding-right: .7rem;}
  .kpi-row{grid-template-columns:repeat(2, minmax(0,1fr));}
  .section-title{font-size:14px;}
  .deadline-pill{font-size:16px; padding:8px 12px;}
  div[data-testid="stHorizontalBlock"]{ flex-direction: column; }
}
</style>
""",
    unsafe_allow_html=True,
)

def ensure_dirs():
    DISP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def safe_name(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[^a-zA-Z0-9_\- ]+", "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80] if text else "item"

def normalize_wa(wa: str) -> str:
    wa = re.sub(r"\D+", "", (wa or "").strip())
    if wa.startswith("08"):
        wa = "62" + wa[1:]
    return wa

def save_file(file_obj, folder: Path, task_id: int, judul: str, prefix: str) -> str:
    if file_obj is None:
        return ""
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = Path(file_obj.name).suffix.lower()
    fname = f"{task_id:05d}_{safe_name(judul)}_{ts}_{prefix}{ext}"
    path = folder / fname
    with open(path, "wb") as f:
        f.write(file_obj.getbuffer())
    return str(path)

def split_pics(pic_text: str) -> list[str]:
    raw = str(pic_text or "").replace(";", ",")
    items = [x.strip() for x in raw.split(",") if x.strip()]
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

def pics_to_text(pics: list[str]) -> str:
    return ", ".join(split_pics(",".join(pics)))

def pic_contains(pic_text: str, username: str) -> bool:
    return username.strip().lower() in [x.lower() for x in split_pics(pic_text)]

@st.cache_resource
def get_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes,
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_spreadsheet():
    client = get_gsheet_client()
    return client.open(st.secrets["gsheets"]["spreadsheet_name"])

def get_ws(title: str):
    ss = get_spreadsheet()
    try:
        return ss.worksheet(title)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=title, rows=1000, cols=40)

def ensure_headers(ws, headers: list[str]) -> None:
    current = ws.row_values(1)
    if current != headers:
        ws.clear()
        ws.update("A1", [headers])

def read_sheet(sheet_name: str, headers: list[str]) -> pd.DataFrame:
    ws = get_ws(sheet_name)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=headers)
    if values[0] != headers:
        ensure_headers(ws, headers)
        return pd.DataFrame(columns=headers)
    rows = values[1:]
    if not rows:
        return pd.DataFrame(columns=headers)
    padded = [row + [""] * (len(headers) - len(row)) for row in rows]
    return pd.DataFrame(padded, columns=headers)

def write_sheet(sheet_name: str, df: pd.DataFrame, headers: list[str]) -> None:
    ws = get_ws(sheet_name)
    out = df.copy()
    for h in headers:
        if h not in out.columns:
            out[h] = ""
    out = out[headers].fillna("")
    values = [headers] + out.astype(str).values.tolist()
    ws.clear()
    ws.update("A1", values)

def init_storage() -> None:
    ensure_dirs()
    ensure_headers(get_ws("users"), USERS_HEADERS)
    ensure_headers(get_ws("tasks"), TASKS_HEADERS)
    ensure_headers(get_ws("audit_log"), AUDIT_HEADERS)

    users_df = read_sheet("users", USERS_HEADERS)
    if users_df.empty:
        seed_df = pd.DataFrame([
            {"username": u, "password": p, "role": r, "display_name": u.title(), "active": "1"}
            for u, p, r in DEFAULT_USERS
        ])
        write_sheet("users", seed_df, USERS_HEADERS)
    else:
        existing = set(users_df["username"].astype(str).str.strip().tolist())
        additions = []
        for u, p, r in DEFAULT_USERS:
            if u not in existing:
                additions.append({"username": u, "password": p, "role": r, "display_name": u.title(), "active": "1"})
        if additions:
            users_df = pd.concat([users_df, pd.DataFrame(additions)], ignore_index=True)
            write_sheet("users", users_df, USERS_HEADERS)

@st.cache_data(ttl=15)
def load_users() -> pd.DataFrame:
    return read_sheet("users", USERS_HEADERS).fillna("")

@st.cache_data(ttl=15)
def load_tasks() -> pd.DataFrame:
    df = read_sheet("tasks", TASKS_HEADERS)
    if df.empty:
        return df
    for col in ["progress", "id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["deadline_dt"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["deadline"] = df["deadline_dt"].dt.date
    df["status"] = df["status"].replace("", "Not Yet Started")
    df["approval_status"] = df["approval_status"].replace("", "Pending Approval")
    df["days_left"] = (pd.to_datetime(df["deadline"], errors="coerce") - pd.to_datetime(date.today())).dt.days
    df["days_left"] = df["days_left"].fillna(999).astype(int)
    return df.sort_values(["deadline_dt", "id"], ascending=[True, True]).reset_index(drop=True)

@st.cache_data(ttl=15)
def load_audit() -> pd.DataFrame:
    df = read_sheet("audit_log", AUDIT_HEADERS)
    if df.empty:
        return df
    for col in ["id", "task_id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df

def save_users(df: pd.DataFrame) -> None:
    write_sheet("users", df, USERS_HEADERS)
    load_users.clear()

def save_tasks(df: pd.DataFrame) -> None:
    save_df = df.copy().drop(columns=["deadline_dt", "days_left"], errors="ignore")
    write_sheet("tasks", save_df, TASKS_HEADERS)
    load_tasks.clear()

def append_audit(task_id: int, user: str, action: str) -> None:
    audit_df = load_audit()
    next_id = 1 if audit_df.empty else int(audit_df["id"].max()) + 1
    new_row = pd.DataFrame([{
        "id": next_id,
        "task_id": task_id,
        "user": user,
        "action": action,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }])
    audit_df = pd.concat([audit_df, new_row], ignore_index=True)
    write_sheet("audit_log", audit_df, AUDIT_HEADERS)
    load_audit.clear()

def get_user_role(username: str, password: str):
    df = load_users()
    if df.empty:
        return None
    row = df[
        (df["username"].astype(str).str.strip() == username.strip())
        & (df["password"].astype(str) == password)
        & (df["active"].astype(str) != "0")
    ]
    if row.empty:
        return None
    return str(row.iloc[0]["role"])

def add_task(judul, tim, pic_list, wa_pic, deadline, instruksi, disp_file):
    df = load_tasks()
    task_id = 1 if df.empty else int(df["id"].max()) + 1
    disp_path = save_file(disp_file, DISP_DIR, task_id, judul, "disposisi") if disp_file is not None else ""
    new_row = pd.DataFrame([{
        "id": task_id,
        "judul": judul,
        "tim": tim,
        "pic_list": pics_to_text(pic_list),
        "wa_pic": wa_pic,
        "deadline": str(deadline),
        "progress": 0,
        "status": "Not Yet Started",
        "instruksi": instruksi,
        "instruksi_file": disp_path,
        "output_file": "",
        "catatan": "",
        "update_terakhir": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "approval_status": "Pending Approval",
        "approved_by": "",
        "approved_at": "",
    }])
    df = pd.concat([df.drop(columns=["deadline_dt", "days_left"], errors="ignore"), new_row], ignore_index=True)
    save_tasks(df)
    append_audit(task_id, st.session_state.username, "create task")
    return task_id

def update_task(task_id: int, progress: int, status: str, catatan: str, out_file):
    df = load_tasks()
    idx = df.index[df["id"] == task_id]
    if len(idx) == 0:
        return False
    i = idx[0]
    out_path = str(df.at[i, "output_file"] or "")
    judul = str(df.at[i, "judul"])
    if out_file is not None:
        out_path = save_file(out_file, OUT_DIR, task_id, judul, "output")
    df.at[i, "progress"] = int(progress)
    df.at[i, "status"] = status
    df.at[i, "catatan"] = catatan
    df.at[i, "output_file"] = out_path
    df.at[i, "update_terakhir"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if status in ["Done", "Review"]:
        df.at[i, "approval_status"] = "Pending Approval"
        df.at[i, "approved_by"] = ""
        df.at[i, "approved_at"] = ""
    save_tasks(df)
    append_audit(task_id, st.session_state.username, "update task")
    return True

def set_approval(task_id: int, approval_status: str):
    df = load_tasks()
    idx = df.index[df["id"] == task_id]
    if len(idx) == 0:
        return False
    i = idx[0]
    df.at[i, "approval_status"] = approval_status
    df.at[i, "approved_by"] = st.session_state.username
    df.at[i, "approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if approval_status == "Approved" and str(df.at[i, "status"]) != "Done":
        df.at[i, "status"] = "Done"
        df.at[i, "progress"] = 100
    save_tasks(df)
    append_audit(task_id, st.session_state.username, f"approval: {approval_status}")
    return True

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    export_df = df.copy().drop(columns=["deadline_dt", "days_left"], errors="ignore")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="tasks")
    buf.seek(0)
    return buf.getvalue()

def login_view():
    st.markdown('<div class="h-title">Monitoring Bahan Pimpinan</div>', unsafe_allow_html=True)
    st.markdown('<div class="h-sub">Silakan login untuk mengakses dashboard.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        username = st.text_input("Username")
    with c2:
        password = st.text_input("Password", type="password")
    if st.button("Login", use_container_width=True):
        role = get_user_role(username.strip(), password)
        if role:
            st.session_state.logged_in = True
            st.session_state.username = username.strip()
            st.session_state.role = role
            st.rerun()
        st.error("Username/password salah.")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

init_storage()
st_autorefresh(interval=30000, key="auto_refresh")

if not st.session_state.logged_in:
    login_view()
    raise SystemExit

role = st.session_state.role
username = st.session_state.username
users_df = load_users()
tasks_df = load_tasks()

st.markdown('<div class="h-title">Monitoring Bahan Pimpinan</div>', unsafe_allow_html=True)
st.markdown('<div class="h-sub">Dashboard monitoring, tindak lanjut PIC, dan final approval atasan.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.write(f"**Login:** {username}")
    st.write(f"**Role:** {role}")
    st.caption("Tampilan dibuat konsisten tanpa dark mode, dan lebih ramah di mobile.")
    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    st.divider()

    if role in ["admin", "atasan"]:
        st.header("➕ Input Bahan")
        judul = st.text_input("Judul Bahan")
        tim = st.selectbox("Nama Tim", ["Tulodong", "PDSIA", "Pusat", "Lainnya"])
        pic_list = st.multiselect(
            "PIC yang ditugaskan",
            sorted(users_df.loc[users_df["role"] == "pic", "username"].astype(str).tolist()),
            help="Bisa memilih lebih dari 2 PIC.",
        )
        wa_pic = st.text_input("Nomor WA PIC (opsional)")
        deadline = st.date_input("Deadline", value=date.today())
        instruksi = st.text_area("Arahan singkat / catatan disposisi", height=110)
        disp_file = st.file_uploader("Upload file disposisi", type=["docx", "pdf", "xlsx", "pptx", "ppt"], key="disp_file")
        wa_norm = normalize_wa(wa_pic)
        msg = (
            "[DISPOSISI BAHAN PAPARAN]\n"
            f"Judul: {judul or '-'}\n"
            f"PIC: {', '.join(pic_list) if pic_list else '-'}\n"
            f"Deadline: {deadline}\n"
            f"Arahan: {(instruksi.strip() if instruksi.strip() else '-')}\n\n"
            "Mohon update progres dan unggah output di dashboard. Terima kasih."
        )
        if wa_norm:
            st.link_button("Buka WhatsApp", "https://wa.me/" + wa_norm + "?text=" + urllib.parse.quote(msg), use_container_width=True)
        if st.button("Tambah Disposisi", use_container_width=True):
            if not judul.strip():
                st.error("Judul bahan wajib diisi.")
            elif not pic_list:
                st.error("Minimal pilih 1 PIC.")
            elif deadline < date.today():
                st.error("Deadline tidak boleh lebih kecil dari hari ini.")
            else:
                task_id = add_task(judul.strip(), tim, pic_list, wa_norm, deadline, instruksi.strip(), disp_file)
                st.success(f"Disposisi ditambahkan (ID {task_id}).")
                st.rerun()

    st.divider()
    st.header("✍️ Update PIC")
    if tasks_df.empty:
        st.info("Belum ada disposisi.")
    else:
        if role == "pic":
            my_df = tasks_df[tasks_df["pic_list"].apply(lambda x: pic_contains(x, username))].copy()
        else:
            who = st.selectbox("Filter PIC", ["Semua"] + sorted({p for val in tasks_df["pic_list"].tolist() for p in split_pics(val)}))
            my_df = tasks_df if who == "Semua" else tasks_df[tasks_df["pic_list"].apply(lambda x: pic_contains(x, who))].copy()
        if my_df.empty:
            st.warning("Tidak ada tugas untuk PIC ini.")
        else:
            labels = my_df["id"].astype(str) + " - " + my_df["judul"]
            picked = st.selectbox("Pilih disposisi", labels.tolist())
            task_id = int(picked.split(" - ")[0])
            row = my_df[my_df["id"] == task_id].iloc[0]
            overdue_cls = "overdue" if int(row["days_left"]) < 0 else ("safe" if int(row["days_left"]) > 3 else "")
            st.markdown(f"<div class='deadline-pill {overdue_cls}'>Deadline: {row['deadline']}</div>", unsafe_allow_html=True)
            st.caption("PIC: " + (row["pic_list"] if row["pic_list"] else "-"))
            st.info(row["instruksi"] if str(row["instruksi"]).strip() else "(Tidak ada arahan)")
            if str(row["instruksi_file"]).strip() and os.path.exists(str(row["instruksi_file"])):
                with open(str(row["instruksi_file"]), "rb") as f:
                    st.download_button("Unduh file disposisi", f, file_name=os.path.basename(str(row["instruksi_file"])), use_container_width=True)
            prog = st.slider("Progress (%)", 0, 100, int(row["progress"]), step=5)
            current_status = row["status"] if row["status"] in STATUS_OPTIONS else "Not Yet Started"
            status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current_status))
            catatan = st.text_area("Catatan PIC", value=str(row["catatan"] or ""), height=90)
            out_file = st.file_uploader("Upload output akhir", type=["pptx", "ppt", "docx", "xlsx", "pdf"], key=f"out_{task_id}")
            if st.button("Simpan Update PIC", use_container_width=True):
                if update_task(task_id, prog, status, catatan.strip(), out_file):
                    st.success("Update tersimpan.")
                    st.rerun()

    if role in ["admin", "atasan"] and not tasks_df.empty:
        st.divider()
        st.header("✅ Final Approval")
        pending_df = tasks_df[tasks_df["approval_status"] == "Pending Approval"].copy()
        if pending_df.empty:
            st.info("Tidak ada bahan yang menunggu approval.")
        else:
            labels = pending_df["id"].astype(str) + " - " + pending_df["judul"]
            picked = st.selectbox("Pilih bahan untuk approval", labels.tolist(), key="approval_pick")
            task_id = int(picked.split(" - ")[0])
            row = pending_df[pending_df["id"] == task_id].iloc[0]
            st.caption("PIC: " + row["pic_list"])
            st.caption("Status saat ini: " + row["status"])
            overdue_cls = "overdue" if int(row["days_left"]) < 0 else ("safe" if int(row["days_left"]) > 3 else "")
            st.markdown(f"<div class='deadline-pill {overdue_cls}'>Deadline: {row['deadline']}</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("Approve", use_container_width=True):
                set_approval(task_id, "Approved")
                st.success("Bahan disetujui.")
                st.rerun()
            if c2.button("Reject", use_container_width=True):
                set_approval(task_id, "Rejected")
                st.warning("Bahan ditolak / perlu perbaikan.")
                st.rerun()

if tasks_df.empty:
    st.info("Belum ada data disposisi.")
    raise SystemExit

default_df = tasks_df.copy()
if role == "pic":
    default_df = tasks_df[tasks_df["pic_list"].apply(lambda x: pic_contains(x, username))].copy()

st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Rangkuman Status</div>', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="kpi-row">
      <div class="kpi"><div class="k">Total bahan</div><div class="v">{len(default_df) if role == 'pic' else len(tasks_df)}</div></div>
      <div class="kpi"><div class="k">On Progress</div><div class="v">{int((default_df['status'] == 'On Progress').sum()) if not default_df.empty else 0}</div></div>
      <div class="kpi"><div class="k">Belum mulai</div><div class="v">{int((default_df['status'] == 'Not Yet Started').sum()) if not default_df.empty else 0}</div></div>
      <div class="kpi"><div class="k">Selesai</div><div class="v">{int((default_df['status'] == 'Done').sum()) if not default_df.empty else 0}</div></div>
    </div>
    <div class="mobile-note">Auto-refresh 30 detik • tampilan awal untuk PIC menampilkan tugas miliknya saja.</div>
    """,
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Filter Tampilan", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if role == "pic":
            scope = st.selectbox("Tampilan Awal", ["Tugas Saya", "Semua Bahan"])
        else:
            scope = "Semua Bahan"
            st.text_input("Tampilan Awal", value="Semua Bahan", disabled=True)
    with c2:
        status_filter = st.selectbox("Status", ["Semua"] + STATUS_OPTIONS)
    with c3:
        approval_filter = st.selectbox("Approval", ["Semua"] + APPROVAL_OPTIONS)
    with c4:
        keyword = st.text_input("Cari judul / instruksi")

view_df = tasks_df.copy()
if role == "pic" and scope == "Tugas Saya":
    view_df = view_df[view_df["pic_list"].apply(lambda x: pic_contains(x, username))].copy()
if status_filter != "Semua":
    view_df = view_df[view_df["status"] == status_filter]
if approval_filter != "Semua":
    view_df = view_df[view_df["approval_status"] == approval_filter]
if keyword.strip():
    key = keyword.strip().lower()
    view_df = view_df[
        view_df["judul"].astype(str).str.lower().str.contains(key, na=False)
        | view_df["instruksi"].astype(str).str.lower().str.contains(key, na=False)
    ]

st.subheader("📋 Monitoring Disposisi")
if view_df.empty:
    st.info("Tidak ada data yang sesuai filter.")
else:
    export_cols = ["id", "judul", "tim", "pic_list", "deadline", "progress", "status", "approval_status", "approved_by", "approved_at", "instruksi", "catatan", "update_terakhir"]
    st.download_button(
        "Ekspor Excel",
        data=to_excel_bytes(view_df[[c for c in export_cols if c in view_df.columns]].copy()),
        file_name="monitoring_disposisi.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    for _, r in view_df.sort_values(["deadline_dt", "id"]).iterrows():
        overdue_cls = "overdue" if int(r["days_left"]) < 0 else ("safe" if int(r["days_left"]) > 3 else "")
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(
                f"""
                <div class="card" style="margin-bottom:10px;">
                    <div class="section-title">{r['judul']}</div>
                    <div class="small">Tim: {r['tim'] or '-'} • PIC: {r['pic_list'] or '-'}</div>
                    <div style="margin:8px 0 8px 0;"><span class="deadline-pill {overdue_cls}">Deadline: {r['deadline']}</span></div>
                    <div class="small">Status: <b>{r['status']}</b> • Progress: <b>{int(r['progress'])}%</b></div>
                    <div class="small">Approval: <b>{r['approval_status']}</b></div>
                    <div class="small" style="margin-top:6px;">Instruksi: {r['instruksi'] if str(r['instruksi']).strip() else '-'}</div>
                    <div class="small">Catatan: {r['catatan'] if str(r['catatan']).strip() else '-'}</div>
                    <div class="small">Update terakhir: {r['update_terakhir'] or '-'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            out_path = str(r.get("output_file", "") or "").strip()
            if out_path and os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    st.download_button("Unduh Output", f, file_name=os.path.basename(out_path), mime="application/octet-stream", key=f"dl_{int(r['id'])}", use_container_width=True)
            else:
                st.button("Belum ada output", disabled=True, use_container_width=True, key=f"empty_{int(r['id'])}")

st.markdown("---")
colA, colB = st.columns(2)
with colA:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Distribusi Tugas per PIC</div>', unsafe_allow_html=True)
    rows = []
    for _, row in view_df.iterrows():
        for p in split_pics(row["pic_list"]):
            rows.append({"PIC": p, "Status": row["status"], "TaskID": row["id"]})
    pic_df = pd.DataFrame(rows)
    if pic_df.empty:
        st.info("Belum ada data PIC.")
    else:
        agg = pic_df.groupby(["PIC", "Status"])["TaskID"].count().reset_index(name="Jumlah")
        fig = px.bar(
            agg,
            x="PIC",
            y="Jumlah",
            color="Status",
            barmode="stack",
            color_discrete_map={
                "Not Yet Started": "#ef4444",
                "On Progress": "#f59e0b",
                "Review": "#8b5cf6",
                "Done": "#22c55e",
                "Cancel": "#94a3b8",
                "Blocked": "#111827",
            },
        )
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
with colB:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Jumlah Bahan per Triwulan</div>', unsafe_allow_html=True)
    tmp = view_df.copy()
    tmp["quarter"] = pd.to_datetime(tmp["deadline"], errors="coerce").dt.to_period("Q").astype(str)
    quarter_df = tmp.groupby("quarter")["id"].count().reset_index(name="Jumlah")
    if quarter_df.empty:
        st.info("Belum ada data triwulan.")
    else:
        fig_q = px.bar(quarter_df, x="quarter", y="Jumlah")
        fig_q.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_q, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">Tren Bulanan Penyusunan Bahan</div>', unsafe_allow_html=True)
tmp = view_df.copy()
tmp["month_year"] = pd.to_datetime(tmp["deadline"], errors="coerce").dt.strftime("%b %Y")
month_df = tmp.groupby("month_year")["id"].count().reset_index(name="Jumlah")
if month_df.empty:
    st.info("Belum ada data bulanan.")
else:
    fig_m = px.line(month_df, x="month_year", y="Jumlah", markers=True)
    fig_m.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_m, use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)
