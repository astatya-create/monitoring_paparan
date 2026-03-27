from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from typing import Any

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
import time

st.set_page_config(page_title="Monitoring Disposisi Bahan Pimpinan", layout="wide", initial_sidebar_state="expanded")

BASE_DIR = Path(__file__).resolve().parent
SEED_USERS_FILE = BASE_DIR / "seed_users.py"
LOGO_PATH = BASE_DIR / "logo_kemenperin.png"

STATUS_OPTIONS = ["Not Yet Started", "On Progress", "Done"]
APPROVAL_OPTIONS = ["Pending Approval", "Approved", "Rejected"]
ROLE_OPTIONS = ["admin", "atasan", "pic"]
KANTOR_OPTIONS = ["Tulodong", "Gatsu"]
JENIS_OPTIONS = ["Kabinet", "Legislatif", "Instansi", "Lain-lain"]
DEFAULT_SEED_USERS = [("admin", "admin123", "admin"), ("atasan", "atasan123", "atasan")]

USERS_HEADERS = ["username", "password", "role", "display_name", "active"]
BAHAN_HEADERS = [
    "id","tgl_disposisi","nama_bahan","pic_list","kantor","jenis_bahan","instruksi","deadline",
    "status","progress","keterangan","file_surat","file_paparan","file_narasi",
    "approval_status","approved_by","approved_at","created_at","updated_at",
]
AUDIT_HEADERS = ["id", "bahan_id", "user", "action", "timestamp"]


def file_to_base64(file_path: Path) -> str:
    import base64
    with file_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def normalize_link(value: str | None) -> str:
    return str(value).strip() if value else ""


def is_url(value: str | None) -> bool:
    return bool(value) and str(value).strip().lower().startswith(("http://", "https://"))


def split_pic_list(value: str | None) -> list[str]:
    raw = str(value or "").replace(";", ",")
    items = [x.strip() for x in raw.split(",") if x.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def join_pic_list(items: list[str]) -> str:
    return ", ".join(split_pic_list(",".join(items)))


def user_is_in_pic_list(username: str, pic_list: str) -> bool:
    return username.strip().lower() in [x.lower() for x in split_pic_list(pic_list)]


def _extract_seed_users_from_ast(node: ast.AST) -> list[tuple[str, str, str]]:
    users: list[tuple[str, str, str]] = []
    for subnode in ast.walk(node):
        if isinstance(subnode, ast.Assign):
            for target in subnode.targets:
                if isinstance(target, ast.Name) and target.id == "users":
                    value = subnode.value
                    if isinstance(value, (ast.List, ast.Tuple)):
                        for item in value.elts:
                            if not isinstance(item, (ast.List, ast.Tuple)) or len(item.elts) != 3:
                                continue
                            parts: list[str] = []
                            for elt in item.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    parts.append(elt.value)
                            if len(parts) == 3:
                                users.append((parts[0].strip(), parts[1], parts[2].strip().lower()))
    return users


def load_seed_users() -> list[tuple[str, str, str]]:
    if not SEED_USERS_FILE.exists():
        return DEFAULT_SEED_USERS
    try:
        tree = ast.parse(SEED_USERS_FILE.read_text(encoding="utf-8"))
        parsed = _extract_seed_users_from_ast(tree)
        cleaned = [u for u in parsed if u[0] and u[1] and u[2] in ROLE_OPTIONS]
        return cleaned or DEFAULT_SEED_USERS
    except Exception:
        return DEFAULT_SEED_USERS


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


@st.cache_resource
def get_worksheet_map():
    ss = get_spreadsheet()
    return {ws.title: ws for ws in ss.worksheets()}


def reset_worksheet_cache() -> None:
    get_worksheet_map.clear()


def get_ws(title: str):
    ws_map = get_worksheet_map()
    if title in ws_map:
        return ws_map[title]
    ss = get_spreadsheet()
    ws = ss.add_worksheet(title=title, rows=1000, cols=40)
    reset_worksheet_cache()
    return ws


def ensure_headers(ws, headers: list[str]) -> None:
    values = ws.get_all_values()
    if not values or values[0] != headers:
        ws.clear()
        ws.update("A1", [headers])


def _read_sheet_once(sheet_name: str, headers: list[str]) -> pd.DataFrame:
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


def read_sheet(sheet_name: str, headers: list[str]) -> pd.DataFrame:
    for attempt in range(3):
        try:
            return _read_sheet_once(sheet_name, headers)
        except APIError as e:
            if "429" in str(e) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise


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
    reset_worksheet_cache()


def init_storage() -> None:
    ensure_headers(get_ws("users"), USERS_HEADERS)
    ensure_headers(get_ws("bahan"), BAHAN_HEADERS)
    ensure_headers(get_ws("audit_log"), AUDIT_HEADERS)

    users_df = read_sheet("users", USERS_HEADERS)
    if users_df.empty:
        seed_df = pd.DataFrame([{
            "username": u, "password": p, "role": r, "display_name": u.title(), "active": "1"
        } for u, p, r in load_seed_users()])
        write_sheet("users", seed_df, USERS_HEADERS)


@st.cache_data(ttl=300)
def load_users() -> pd.DataFrame:
    df = read_sheet("users", USERS_HEADERS)
    return df.fillna("") if not df.empty else df


@st.cache_data(ttl=90)
def load_bahan() -> pd.DataFrame:
    df = read_sheet("bahan", BAHAN_HEADERS)
    if df.empty:
        return df
    df = df.fillna("")
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int)
    df["tgl_disposisi"] = pd.to_datetime(df["tgl_disposisi"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["tahun"] = df["tgl_disposisi"].dt.year
    tri_map = {1: "I", 2: "I", 3: "I", 4: "II", 5: "II", 6: "II", 7: "III", 8: "III", 9: "III", 10: "IV", 11: "IV", 12: "IV"}
    df["triwulan"] = df["tgl_disposisi"].dt.month.map(tri_map)
    today = pd.Timestamp(datetime.now().date())
    df["days_to_deadline"] = (df["deadline"] - today).dt.days
    return df.sort_values(["tgl_disposisi", "id"], ascending=[False, False]).reset_index(drop=True)


@st.cache_data(ttl=180)
def load_audit() -> pd.DataFrame:
    df = read_sheet("audit_log", AUDIT_HEADERS)
    if df.empty:
        return df
    df = df.fillna("")
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    df["bahan_id"] = pd.to_numeric(df["bahan_id"], errors="coerce").fillna(0).astype(int)
    return df


def save_users(df: pd.DataFrame) -> None:
    write_sheet("users", df, USERS_HEADERS)
    load_users.clear()


def save_bahan(df: pd.DataFrame) -> None:
    export_df = df.copy()
    for col in ["tgl_disposisi", "deadline"]:
        if col in export_df.columns:
            export_df[col] = pd.to_datetime(export_df[col], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for extra in ["tahun", "triwulan", "days_to_deadline"]:
        export_df = export_df.drop(columns=[extra], errors="ignore")
    write_sheet("bahan", export_df, BAHAN_HEADERS)
    load_bahan.clear()


def append_audit(bahan_id: int, user: str, action: str) -> None:
    df = load_audit()
    next_id = 1 if df.empty else int(df["id"].max()) + 1
    new_row = pd.DataFrame([{"id": next_id, "bahan_id": bahan_id, "user": user, "action": action, "timestamp": datetime.now().isoformat(timespec="seconds")}])
    df = pd.concat([df, new_row], ignore_index=True)
    write_sheet("audit_log", df, AUDIT_HEADERS)
    load_audit.clear()


def clear_all_data_cache() -> None:
    load_users.clear()
    load_bahan.clear()
    load_audit.clear()


def authenticate(username: str, password: str) -> str | None:
    df = load_users()
    if df.empty:
        return None
    row = df[
        (df["username"].astype(str).str.strip() == username.strip()) &
        (df["password"].astype(str) == password) &
        (df["active"].astype(str) != "0")
    ]
    if row.empty:
        return None
    return str(row.iloc[0]["role"]).lower()


def get_pic_users() -> list[str]:
    df = load_users()
    if df.empty:
        return []
    return sorted(df[df["role"].astype(str).str.lower() == "pic"]["username"].astype(str).tolist())


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    from io import BytesIO
    export_df = df.copy()
    for col in export_df.columns:
        if pd.api.types.is_datetime64_any_dtype(export_df[col]):
            export_df[col] = export_df[col].dt.strftime("%Y-%m-%d")
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Daftar Bahan")
    buffer.seek(0)
    return buffer.getvalue()


def logout() -> None:
    st.session_state.clear()
    st.rerun()


def inject_dashboard_css() -> None:
    st.markdown("""
        <style>
        [data-testid="stAppViewContainer"] { background: #f3f6fa !important; }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0e4160 0%, #09344d 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        [data-testid="stSidebar"] * { color: #c7d0da !important; }
        [data-testid="stSidebar"] label { color: #d4dbe4 !important; font-weight: 600; }
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stDateInput input,
        [data-testid="stSidebar"] .stTextArea textarea,
        [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] > div {
            background: rgba(255,255,255,0.95) !important;
            color: #17355c !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stDownloadButton > button {
            background: linear-gradient(180deg, #2da8d8 0%, #1a7fb4 100%) !important;
            color: white !important; border: none !important; border-radius: 12px !important; font-weight: 800 !important;
        }
        .header-card { background: #ffffff; border: 1px solid #dbe4ef; border-radius: 16px; padding: 18px 22px; margin-bottom: 20px; box-shadow: 0 4px 14px rgba(15, 39, 71, 0.06);}
        .header-row { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
        .header-left { display: flex; align-items: center; gap: 14px; min-width: 0; }
        .header-title { color: #14213d; font-size: 30px; font-weight: 900; line-height: 1.08; margin: 0; text-transform: uppercase; }
        .header-subtitle { color: #1d5b84; font-size: 16px; margin-top: 4px; font-weight: 800; letter-spacing: .08em; }
        .header-user { text-align: right; color: #14213d; font-weight: 800; font-size: 16px; border-left: 1px solid #dbe4ef; padding-left: 22px; min-width: 200px; }
        .kpi-card { background: white; border-radius: 18px; padding: 18px 20px; border: 1px solid #e5e7eb; box-shadow: 0 4px 18px rgba(15, 39, 71, 0.05); margin-bottom: 10px; min-height: 108px; }
        .kpi-label { color: #7b8ca6; font-size: 12px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
        .kpi-value { color: #0f172a; font-size: 30px; font-weight: 900; margin-top: 8px; }
        .section-title { color: #0f4d73; font-size: 18px; font-weight: 900; margin: 12px 0 8px; text-transform: uppercase; letter-spacing: .03em; }
        .table-card { background: white; border: 1px solid #e5e7eb; border-radius: 18px; padding: 16px 16px; box-shadow: 0 4px 18px rgba(15, 39, 71, 0.05); margin-top: 18px; }
        .badge { display: inline-block; padding: 5px 10px; border-radius: 999px; background: #0f4d73; color: #ffffff; font-size: 12px; font-weight: 800; }
        .table-head { color: #64748b; font-size: 13px; font-weight: 900; text-transform: uppercase; letter-spacing: .04em; padding-bottom: 4px; }
        .status-pill, .approval-pill { display: inline-block; padding: 5px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; }
        .status-notyet { background: #fee2e2; color: #b91c1c; }
        .status-progress { background: #fef3c7; color: #92400e; }
        .status-done { background: #dcfce7; color: #166534; }
        .approval-pending { background: #e0f2fe; color: #075985; }
        .approval-approved { background: #dcfce7; color: #166534; }
        .approval-rejected { background: #fee2e2; color: #b91c1c; }
        .deadline-alert { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: #fee2e2; color: #b91c1c; font-size: 15px; font-weight: 900; margin-top: 6px; }
        .deadline-safe { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-size: 15px; font-weight: 900; margin-top: 6px; }
        .mini-text { font-size: 14px; color: #64748b; line-height: 1.35; margin: 3px 0; }
        .meta-text { font-size: 15px; color: #475569; line-height: 1.4; margin: 4px 0; font-weight: 600; }
        .pic-text { font-size: 15px; color: #334155; line-height: 1.35; margin: 3px 0; font-weight: 700; }
        .row-title { margin-bottom: 4px; line-height: 1.25; color: #14213d; font-size: 18px; }
        @media (max-width: 768px) {
            .header-row { flex-direction: column; align-items: flex-start; gap: 10px; }
            .header-user { border-left: none; padding-left: 0; min-width: auto; text-align: left; }
            .header-title { font-size: 22px; }
            .header-subtitle { font-size: 13px; }
            .kpi-value { font-size: 24px; }
            .kpi-card { min-height: auto; padding: 16px; }
            .table-card { padding: 12px 10px; border-radius: 16px; }
            .table-head { font-size: 12px; }
            .deadline-alert, .deadline-safe { font-size: 17px; padding: 8px 12px; }
            .meta-text { font-size: 16px; }
            .pic-text { font-size: 16px; }
            .row-title { font-size: 17px; }
            .mini-text { font-size: 13px; }
            div[data-testid="stHorizontalBlock"] { flex-direction: column; gap: 8px; }
            div[data-testid="stButton"] > button,
            div[data-testid="stDownloadButton"] > button {
                width: 100%;
                min-height: 42px;
                border-radius: 12px !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)


def render_login() -> None:
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none; }
        header, footer { visibility: hidden; }
        [data-testid="stAppViewContainer"] { background: #ffffff !important; }
        .login-wrap { max-width: 420px; margin: 5vh auto 0 auto; text-align: center; }
        .login-title { color: #0f172a; font-size: 28px; line-height: 1.15; font-weight: 900; margin: 8px 0 4px 0; }
        .login-subtitle { color: #64748b; font-size: 14px; margin-bottom: 18px; }
        .login-label { text-align: left; color: #17355c; font-size: 13px; font-weight: 800; margin: 8px 0 4px; }
        .stTextInput input { border-radius: 10px !important; background: #f1f5f9 !important; border: 1px solid #e2e8f0 !important; }
        .stButton > button { background: #0f4d73 !important; color: white !important; border: none !important; border-radius: 12px !important; font-weight: 800 !important; padding: .7rem 1rem !important; }
        </style>
    """, unsafe_allow_html=True)
    left, center, right = st.columns([2.2, 2, 2.2])
    with center:
        st.markdown("<div class='login-wrap'>", unsafe_allow_html=True)
        if LOGO_PATH.exists():
            logo_b64 = file_to_base64(LOGO_PATH)
            st.markdown(f"""<div style="text-align:center; margin-bottom: 10px;"><img src="data:image/png;base64,{logo_b64}" width="280"></div>""", unsafe_allow_html=True)
        st.markdown("<div class='login-title'>Dashboard Monitoring<br>Disposisi Bahan Pimpinan</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-subtitle'>Silakan masuk ke akun Anda</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-label'>Username</div>", unsafe_allow_html=True)
        username = st.text_input("Username", label_visibility="collapsed", placeholder="")
        st.markdown("<div class='login-label'>Password</div>", unsafe_allow_html=True)
        password = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="")
        if st.button("MASUK"):
            role = authenticate(username, password)
            if role:
                st.session_state.user = username.strip()
                st.session_state.role = role.lower()
                st.rerun()
            st.error("Username atau password salah.")
        st.markdown("</div>", unsafe_allow_html=True)


@st.dialog("Ganti Password")
def change_password_dialog() -> None:
    st.markdown("### Ganti Password")
    current_password = st.text_input("Password Saat Ini", type="password", key="cp_current")
    new_password = st.text_input("Password Baru", type="password", key="cp_new")
    confirm_password = st.text_input("Konfirmasi Password Baru", type="password", key="cp_confirm")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Simpan Password", use_container_width=True, key="cp_save"):
            username = st.session_state.get("user", "")
            role = authenticate(username, current_password)
            if not role:
                st.error("Password saat ini salah."); return
            if not new_password:
                st.error("Password baru wajib diisi."); return
            if len(new_password) < 6:
                st.error("Password baru minimal 6 karakter."); return
            if new_password != confirm_password:
                st.error("Konfirmasi password tidak sama."); return
            users_df = load_users().copy()
            idx = users_df.index[users_df["username"] == username]
            users_df.at[idx[0], "password"] = new_password
            save_users(users_df)
            st.success("Password berhasil diperbarui.")
            st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True, key="cp_cancel"):
            st.rerun()


@st.dialog("Tambah Bahan")
def tambah_bahan_dialog() -> None:
    daftar_pic = get_pic_users()
    if not daftar_pic:
        st.warning("Belum ada user PIC. Tambahkan user PIC dulu di Kelola User.")
        return
    st.markdown("### Tambah Bahan Baru")
    nama = st.text_input("Nama Bahan", key="tb_nama_bahan")
    col1, col2 = st.columns(2)
    with col1:
        tgl_disposisi = st.date_input("Tanggal Disposisi", key="tb_tgl_disposisi")
    with col2:
        deadline = st.date_input("Deadline", key="tb_deadline")
    col3, col4 = st.columns(2)
    with col3:
        kantor = st.selectbox("Kantor", KANTOR_OPTIONS, key="tb_kantor")
    with col4:
        jenis = st.selectbox("Jenis Bahan", JENIS_OPTIONS, key="tb_jenis")
    pic_selected = st.multiselect("PIC yang Ditugaskan", daftar_pic, default=[], key="tb_pic_list", help="Bisa memilih lebih dari 2 PIC.")
    instruksi = st.text_area("Keywords / Instruksi", height=120, key="tb_instruksi")
    file_surat_link = st.text_input("Link OneDrive Surat / Disposisi", key="tb_file_surat_link", placeholder="https://...")
    file_paparan_link = st.text_input("Link OneDrive Paparan", key="tb_file_paparan_link", placeholder="https://...")
    file_narasi_link = st.text_input("Link OneDrive Narasi", key="tb_file_narasi_link", placeholder="https://...")
    if st.button("Simpan", use_container_width=True, key="tb_simpan_btn"):
        if not nama.strip():
            st.error("Nama bahan wajib diisi."); return
        if not pic_selected:
            st.error("Minimal pilih 1 PIC."); return
        df_bahan = load_bahan()
        duplicate = df_bahan[(df_bahan["nama_bahan"].astype(str).str.strip().str.lower() == nama.strip().lower()) & (pd.to_datetime(df_bahan["deadline"], errors="coerce").dt.date == deadline)]
        if not duplicate.empty:
            st.error("Agenda dengan nama bahan dan deadline tersebut sudah ada."); return
        next_id = 1 if df_bahan.empty else int(df_bahan["id"].max()) + 1
        new_row = pd.DataFrame([{
            "id": next_id, "tgl_disposisi": str(tgl_disposisi), "nama_bahan": nama.strip(), "pic_list": join_pic_list(pic_selected),
            "kantor": kantor, "jenis_bahan": jenis, "instruksi": instruksi, "deadline": str(deadline),
            "status": "Not Yet Started", "progress": 0, "keterangan": "", "file_surat": normalize_link(file_surat_link),
            "file_paparan": normalize_link(file_paparan_link), "file_narasi": normalize_link(file_narasi_link),
            "approval_status": "Pending Approval", "approved_by": "", "approved_at": "",
            "created_at": datetime.now().isoformat(timespec="seconds"), "updated_at": datetime.now().isoformat(timespec="seconds"),
        }])
        export_df = df_bahan.copy()
        for extra in ["tahun", "triwulan", "days_to_deadline"]:
            export_df = export_df.drop(columns=[extra], errors="ignore")
        export_df = pd.concat([export_df, new_row], ignore_index=True)
        save_bahan(export_df)
        append_audit(next_id, st.session_state.user, "create bahan")
        st.success("Bahan berhasil ditambahkan.")
        st.rerun()


@st.dialog("Edit Bahan Paparan")
def edit_dialog(edit_id: int) -> None:
    df_edit = load_bahan()
    df_edit = df_edit[df_edit["id"] == edit_id]
    if df_edit.empty:
        st.error("Data tidak ditemukan."); return
    row = df_edit.iloc[0]
    current_status = row["status"] if row["status"] in STATUS_OPTIONS else STATUS_OPTIONS[0]
    status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current_status))
    progress = 100 if status == "Done" else st.slider("Progress (%)", 0, 100, int(row["progress"] or 0))
    if status == "Done":
        st.caption("Progress otomatis 100% jika status Done.")
    keterangan = st.text_area("Keterangan", str(row["keterangan"] or ""))
    instruksi = st.text_area("Keywords / Instruksi", str(row["instruksi"] or ""), height=120)
    daftar_pic = get_pic_users()
    pic_list = st.multiselect("PIC yang Ditugaskan", daftar_pic, default=split_pic_list(str(row["pic_list"])))
    st.markdown("#### Link OneDrive Dokumen")
    file_surat_link = st.text_input("Link OneDrive Surat / Disposisi", value=str(row["file_surat"] or ""), placeholder="https://...")
    file_paparan_link = st.text_input("Link OneDrive Paparan", value=str(row["file_paparan"] or ""), placeholder="https://...")
    file_narasi_link = st.text_input("Link OneDrive Narasi", value=str(row["file_narasi"] or ""), placeholder="https://...")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Simpan", use_container_width=True):
            bahan_df = load_bahan().copy()
            idx = bahan_df.index[bahan_df["id"] == edit_id]
            i = idx[0]
            bahan_df.at[i, "status"] = status
            bahan_df.at[i, "progress"] = progress
            bahan_df.at[i, "keterangan"] = keterangan
            bahan_df.at[i, "instruksi"] = instruksi
            bahan_df.at[i, "pic_list"] = join_pic_list(pic_list)
            bahan_df.at[i, "file_surat"] = normalize_link(file_surat_link)
            bahan_df.at[i, "file_paparan"] = normalize_link(file_paparan_link)
            bahan_df.at[i, "file_narasi"] = normalize_link(file_narasi_link)
            bahan_df.at[i, "approval_status"] = "Pending Approval" if status == "Done" else bahan_df.at[i, "approval_status"]
            bahan_df.at[i, "approved_by"] = "" if status == "Done" else bahan_df.at[i, "approved_by"]
            bahan_df.at[i, "approved_at"] = "" if status == "Done" else bahan_df.at[i, "approved_at"]
            bahan_df.at[i, "updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_bahan(bahan_df)
            append_audit(edit_id, st.session_state.user, "update bahan")
            st.success("Data berhasil diupdate."); st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True):
            st.rerun()


@st.dialog("Final Approval")
def approval_dialog(bahan_id: int) -> None:
    df = load_bahan()
    row_df = df[df["id"] == bahan_id]
    if row_df.empty:
        st.error("Data tidak ditemukan."); return
    row = row_df.iloc[0]
    st.markdown(f"### Approval: {row['nama_bahan']}")
    st.write(f"PIC: {row['pic_list']}")
    st.write(f"Status saat ini: {row['status']}")
    st.write(f"Progress: {int(row['progress'])}%")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Approve", use_container_width=True):
            bahan_df = load_bahan().copy()
            idx = bahan_df.index[bahan_df["id"] == bahan_id]
            i = idx[0]
            bahan_df.at[i, "approval_status"] = "Approved"
            bahan_df.at[i, "approved_by"] = st.session_state.user
            bahan_df.at[i, "approved_at"] = datetime.now().isoformat(timespec="seconds")
            bahan_df.at[i, "status"] = "Done"
            bahan_df.at[i, "progress"] = 100
            bahan_df.at[i, "updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_bahan(bahan_df)
            append_audit(bahan_id, st.session_state.user, "approve bahan")
            st.success("Bahan berhasil disetujui."); st.rerun()
    with c2:
        if st.button("Reject", use_container_width=True):
            bahan_df = load_bahan().copy()
            idx = bahan_df.index[bahan_df["id"] == bahan_id]
            i = idx[0]
            bahan_df.at[i, "approval_status"] = "Rejected"
            bahan_df.at[i, "approved_by"] = st.session_state.user
            bahan_df.at[i, "approved_at"] = datetime.now().isoformat(timespec="seconds")
            bahan_df.at[i, "updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_bahan(bahan_df)
            append_audit(bahan_id, st.session_state.user, "reject bahan")
            st.warning("Bahan ditolak / perlu perbaikan."); st.rerun()


@st.dialog("Link Dokumen")
def show_link_dialog(title: str, url: str) -> None:
    st.markdown(f"### {title}")
    st.write("Dokumen disimpan di OneDrive.")
    st.link_button("Buka Dokumen", url, use_container_width=True)
    st.code(url, language=None)
    if st.button("Tutup", use_container_width=True):
        st.rerun()


def render_user_admin() -> None:
    if st.session_state.role != "admin":
        return
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Menu Admin", ["Tambah User", "Kelola User"])
    users_df = load_users()
    if menu == "Tambah User":
        st.sidebar.subheader("Tambah User")
        username = st.sidebar.text_input("Username Baru")
        password = st.sidebar.text_input("Password Baru", type="password")
        role = st.sidebar.selectbox("Role", ROLE_OPTIONS)
        display_name = st.sidebar.text_input("Nama Tampilan", value="")
        if st.sidebar.button("Simpan User", use_container_width=True):
            if not username.strip() or not password:
                st.sidebar.error("Username dan password wajib diisi.")
            elif username.strip() in users_df["username"].astype(str).tolist():
                st.sidebar.error("Username sudah digunakan.")
            else:
                new_user = pd.DataFrame([{
                    "username": username.strip(), "password": password, "role": role,
                    "display_name": display_name.strip() or username.strip().title(), "active": "1",
                }])
                users_df = pd.concat([users_df, new_user], ignore_index=True)
                save_users(users_df)
                st.sidebar.success("User berhasil ditambahkan."); st.rerun()
    else:
        if users_df.empty:
            st.sidebar.info("Belum ada user."); return
        selected = st.sidebar.selectbox("Pilih User", users_df["username"].astype(str).tolist())
        user_data = users_df[users_df["username"] == selected].iloc[0]
        new_password = st.sidebar.text_input("Password Baru (opsional)", type="password")
        new_role = st.sidebar.selectbox("Role", ROLE_OPTIONS, index=ROLE_OPTIONS.index(str(user_data["role"]).lower()))
        new_display_name = st.sidebar.text_input("Nama Tampilan", value=str(user_data.get("display_name", "")))
        active_flag = st.sidebar.selectbox("Aktif", ["1", "0"], index=0 if str(user_data.get("active", "1")) != "0" else 1)
        col1, col2 = st.sidebar.columns(2)
        if col1.button("Update", use_container_width=True):
            idx = users_df.index[users_df["username"] == selected]
            i = idx[0]
            if new_password:
                users_df.at[i, "password"] = new_password
            users_df.at[i, "role"] = new_role
            users_df.at[i, "display_name"] = new_display_name.strip() or selected.title()
            users_df.at[i, "active"] = active_flag
            save_users(users_df)
            st.sidebar.success("User berhasil diupdate."); st.rerun()
        if col2.button("Hapus", use_container_width=True):
            if selected == st.session_state.user:
                st.sidebar.error("Tidak bisa menghapus akun sendiri.")
            else:
                users_df = users_df[users_df["username"] != selected]
                save_users(users_df)
                st.sidebar.success("User berhasil dihapus."); st.rerun()


def sort_bahan_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sorted_df = df.copy()
    sorted_df["status_normalized"] = sorted_df["status"].fillna("").astype(str).str.strip().str.lower()
    today = pd.Timestamp(datetime.now().date())
    def priority_bucket(status: str) -> int:
        if status in ["on progress", "proses", "process"]:
            return 0
        if status in ["not yet started", "belum mulai", "not_started", "not started"]:
            return 1
        return 2
    sorted_df["priority_bucket"] = sorted_df["status_normalized"].apply(priority_bucket)
    sorted_df["deadline_missing"] = sorted_df["deadline"].isna().astype(int)
    sorted_df["days_to_deadline"] = (sorted_df["deadline"] - today).dt.days
    sorted_df["days_to_deadline_filled"] = sorted_df["days_to_deadline"].fillna(999999)
    sorted_df = sorted_df.sort_values(by=["priority_bucket", "deadline_missing", "days_to_deadline_filled", "tgl_disposisi", "id"], ascending=[True, True, True, False, False], na_position="last")
    return sorted_df.drop(columns=["status_normalized", "priority_bucket", "deadline_missing", "days_to_deadline_filled"], errors="ignore")


def render_header() -> None:
    logo_html = f'<img src="data:image/png;base64,{file_to_base64(LOGO_PATH)}" width="108">' if LOGO_PATH.exists() else ""
    role_name = "Administrator" if str(st.session_state.role).lower() == "admin" else str(st.session_state.role).title()
    st.markdown(f"""
        <div class="header-card">
            <div class="header-row">
                <div class="header-left">
                    {logo_html}
                    <div>
                        <div class="header-title">Dashboard Monitoring Disposisi Penyusunan Bahan Pimpinan</div>
                        <div class="header-subtitle">PDSIA Gatsu &amp; Tulodong</div>
                    </div>
                </div>
                <div class="header-user">{role_name}<br>{str(st.session_state.user).upper()}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_kpi(df: pd.DataFrame) -> None:
    total = len(df)
    done = int((df["status"] == "Done").sum())
    on_progress = int((df["status"] == "On Progress").sum())
    not_started = int((df["status"] == "Not Yet Started").sum())
    approval_pending = int((df["approval_status"] == "Pending Approval").sum())
    all_pics = {pic for val in df["pic_list"].astype(str).tolist() for pic in split_pic_list(val)}
    total_pic = len(all_pics)
    cards = [
        ("TOTAL PAPARAN", total, "#17355c"),
        ("BELUM MULAI", not_started, "#ef4444"),
        ("DALAM PROSES", on_progress, "#f59e0b"),
        ("SELESAI", done, "#22c55e"),
        ("MENUNGGU APPROVAL", approval_pending, "#0ea5e9"),
        ("PIC AKTIF", total_pic, "#06b6d4"),
    ]
    cols = st.columns(len(cards))
    for col, (label, value, color) in zip(cols, cards):
        with col:
            st.markdown(f"""<div class="kpi-card" style="border-left: 6px solid {color};"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>""", unsafe_allow_html=True)


def render_charts(df: pd.DataFrame, tahun_pilih: int) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="section-title">Komposisi Jenis Bahan ({tahun_pilih})</div>', unsafe_allow_html=True)
        jenis = df["jenis_bahan"].fillna("Unknown").value_counts().reset_index()
        jenis.columns = ["jenis_bahan", "jumlah"]
        fig = px.pie(jenis, names="jenis_bahan", values="jumlah", hole=0.58)
        fig.update_traces(textinfo="percent+label"); fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown(f'<div class="section-title">Distribusi Bahan per PIC ({tahun_pilih})</div>', unsafe_allow_html=True)
        pic_rows = []
        for _, row in df.iterrows():
            for pic in split_pic_list(row["pic_list"]):
                pic_rows.append({"PIC": pic, "status": row["status"]})
        df_pic = pd.DataFrame(pic_rows)
        if df_pic.empty:
            st.info("Belum ada data PIC.")
        else:
            beban = df_pic.groupby("PIC").agg(Total=("status", "count"), Done=("status", lambda s: (s == "Done").sum()), In_Progress=("status", lambda s: (s == "On Progress").sum())).reset_index()
            beban["Not_Yet"] = beban["Total"] - beban["Done"] - beban["In_Progress"]
            beban_long = beban.melt(id_vars=["PIC", "Total"], value_vars=["Not_Yet", "In_Progress", "Done"], var_name="Status", value_name="Jumlah")
            beban_long["Status"] = beban_long["Status"].map({"Not_Yet": "Not Yet Started", "In_Progress": "On Progress", "Done": "Done"})
            fig = px.bar(beban_long, y="PIC", x="Jumlah", color="Status", color_discrete_map={"Not Yet Started": "#ef4444", "On Progress": "#f59e0b", "Done": "#22c55e"}, orientation="h", barmode="stack")
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)
    with col3:
        st.markdown(f'<div class="section-title">Distribusi Bahan per Tim Kerja ({tahun_pilih})</div>', unsafe_allow_html=True)
        kantor = df["kantor"].fillna("-").value_counts().reindex(KANTOR_OPTIONS, fill_value=0).reset_index()
        kantor.columns = ["Kantor", "Jumlah"]
        fig = px.bar(kantor, x="Kantor", y="Jumlah", text="Jumlah", color="Kantor")
        fig.update_traces(textposition="outside"); fig.update_layout(showlegend=False, yaxis=dict(dtick=1), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f'<div class="section-title">Tren Bulanan dan Triwulanan ({tahun_pilih})</div>', unsafe_allow_html=True)
    c4, c5 = st.columns(2)
    df_trend = df.copy(); df_trend["tgl_disposisi"] = pd.to_datetime(df_trend["tgl_disposisi"], errors="coerce")
    with c4:
        month_names = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
        if df_trend["tgl_disposisi"].notna().any():
            df_trend["bulan_num"] = df_trend["tgl_disposisi"].dt.month
            bulanan = df_trend.dropna(subset=["bulan_num"]).groupby(["bulan_num", "status"]).size().reset_index(name="Jumlah")
            all_months = pd.DataFrame({"bulan_num": list(range(1, 13))})
            total_bulan = bulanan.groupby("bulan_num", as_index=False)["Jumlah"].sum() if not bulanan.empty else pd.DataFrame({"bulan_num":[], "Jumlah":[]})
            bulanan_view = all_months.merge(total_bulan, on="bulan_num", how="left").fillna(0)
            bulanan_view["Bulan"] = bulanan_view["bulan_num"].map(lambda x: month_names[int(x)-1])
            fig = px.line(bulanan_view, x="Bulan", y="Jumlah", markers=True)
            fig.update_traces(mode="lines+markers+text", line_shape="spline", line=dict(width=4), marker=dict(size=9), text=bulanan_view["Jumlah"], textposition="top center")
            fig.update_layout(showlegend=False, yaxis=dict(dtick=1), xaxis=dict(showgrid=False), margin=dict(l=10, r=10, t=10, b=10), height=360)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada data bulanan.")
    with c5:
        if df_trend["tgl_disposisi"].notna().any():
            df_trend["triwulan_chart"] = df_trend["tgl_disposisi"].dt.quarter.map(lambda q: f"TW{int(q)}")
            tri_order = ["TW1", "TW2", "TW3", "TW4"]
            triwulan = df_trend.dropna(subset=["triwulan_chart"]).groupby("triwulan_chart").size().reindex(tri_order, fill_value=0).reset_index(name="Jumlah")
            fig = px.bar(triwulan, x="triwulan_chart", y="Jumlah", text="Jumlah", color="triwulan_chart", color_discrete_map={"TW1":"#38bdf8","TW2":"#22c55e","TW3":"#f59e0b","TW4":"#ef4444"})
            fig.update_traces(textposition="outside"); fig.update_layout(showlegend=False, yaxis=dict(dtick=1), margin=dict(l=10, r=10, t=10, b=10), height=360)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada data triwulanan.")


def render_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="table-card">', unsafe_allow_html=True)
    top1, top2 = st.columns([5, 1])
    with top1:
        st.markdown('<div class="section-title">Daftar Bahan Paparan</div>', unsafe_allow_html=True)
    with top2:
        st.markdown(f'<div style="text-align:right;"><span class="badge">{len(df)} Data</span></div>', unsafe_allow_html=True)
    header_cols = st.columns([0.35, 2.6, 1.05, 1.35, 1.1, 1.0, 1.15, 1.05, 1.2])
    for col, title in zip(header_cols, ["No", "Judul", "Tim Kerja", "PIC", "Status", "Progress", "Approval", "Output", "Aksi"]):
        col.markdown(f"<div class='table-head'>{title}</div>", unsafe_allow_html=True)
    st.divider()
    for no, (_, row) in enumerate(df.iterrows(), start=1):
        pill_class = {"Done": "status-done", "On Progress": "status-progress"}.get(row["status"], "status-notyet")
        approval_class = {"Approved": "approval-approved", "Rejected": "approval-rejected"}.get(str(row["approval_status"]), "approval-pending")
        progress = max(0, min(100, int(row["progress"] or 0)))
        c0, c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.35, 2.6, 1.05, 1.35, 1.1, 1.0, 1.15, 1.05, 1.2])
        c0.write(no)
        with c1:
            st.markdown(f"<div class='row-title'><strong>{row['nama_bahan']}</strong></div>", unsafe_allow_html=True)
            if st.session_state.get("role") == "pic" and user_is_in_pic_list(st.session_state.get("user", ""), str(row["pic_list"])):
                st.markdown("<div class='mini-text'><strong>• Tugas Anda</strong></div>", unsafe_allow_html=True)
            info = []
            if row["jenis_bahan"]:
                info.append(str(row["jenis_bahan"]))
            if pd.notna(row["deadline"]):
                info.append(f"Deadline: {row['deadline'].date()}")
            if info:
                st.markdown(f"<div class='meta-text'>{' • '.join(info)}</div>", unsafe_allow_html=True)
            deadline_days = row.get("days_to_deadline", None)
            if pd.notna(deadline_days):
                deadline_days = int(deadline_days)
                if 0 <= deadline_days <= 3:
                    label = "H-0 / Hari ini" if deadline_days == 0 else f"H-{deadline_days}"
                    st.markdown(f"<span class='deadline-alert'>⚠ {label}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span class='deadline-safe'>Deadline: {row['deadline'].date()}</span>", unsafe_allow_html=True)
        with c2:
            st.write(row["kantor"] or "-")
            surat_value = str(row["file_surat"] or "").strip()
            if is_url(surat_value):
                if st.button("📩 Dispo", key=f"surat_{row['id']}", use_container_width=True):
                    show_link_dialog("Link Disposisi", surat_value)
            else:
                st.caption("Dispo: -")
        with c3:
            pics = split_pic_list(str(row["pic_list"]))
            if pics:
                for pic in pics[:4]:
                    st.markdown(f"<div class='pic-text'>• {pic}</div>", unsafe_allow_html=True)
                if len(pics) > 4:
                    st.markdown(f"<div class='pic-text'>+{len(pics)-4} PIC lain</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='pic-text'>-</div>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"<span class='status-pill {pill_class}'>{row['status']}</span>", unsafe_allow_html=True)
            if row["keterangan"]:
                st.markdown(f"<div class='mini-text'>{str(row['keterangan'])}</div>", unsafe_allow_html=True)
        with c5:
            st.progress(progress / 100); st.caption(f"{progress}%")
        with c6:
            st.markdown(f"<span class='approval-pill {approval_class}'>{row['approval_status']}</span>", unsafe_allow_html=True)
            if row["approved_by"]:
                st.markdown(f"<div class='mini-text'>Oleh: {row['approved_by']}</div>", unsafe_allow_html=True)
        with c7:
            paparan_value = str(row["file_paparan"] or "").strip()
            narasi_value = str(row["file_narasi"] or "").strip()
            if is_url(paparan_value):
                if st.button("📊 Paparan", key=f"paparan_{row['id']}", use_container_width=True):
                    show_link_dialog("Link Paparan", paparan_value)
            else:
                st.caption("Paparan: -")
            if is_url(narasi_value):
                if st.button("📝 Narasi", key=f"narasi_{row['id']}", use_container_width=True):
                    show_link_dialog("Link Narasi", narasi_value)
            else:
                st.caption("Narasi: -")
        with c8:
            can_edit = st.session_state.role in {"admin", "atasan"} or user_is_in_pic_list(st.session_state.user, str(row["pic_list"]))
            can_delete = st.session_state.role in {"admin", "atasan"}
            a1, a2 = st.columns(2)
            with a1:
                if st.button("✏️", key=f"edit_{row['id']}", disabled=not can_edit):
                    edit_dialog(int(row["id"]))
            with a2:
                if st.button("✅", key=f"approve_{row['id']}", disabled=st.session_state.role not in {"admin", "atasan"}):
                    approval_dialog(int(row["id"]))
            if can_delete:
                if st.button("🗑️ Hapus", key=f"del_{row['id']}", use_container_width=True):
                    bahan_df = load_bahan().copy()
                    bahan_df = bahan_df[bahan_df["id"] != int(row["id"])]
                    save_bahan(bahan_df)
                    append_audit(int(row["id"]), st.session_state.user, "delete bahan")
                    st.success("Data berhasil dihapus."); st.rerun()
        st.markdown("<div style='margin:6px 0 2px 0;'></div>", unsafe_allow_html=True)
        st.divider()
    st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard() -> None:
    inject_dashboard_css(); render_header()
    with st.sidebar:
        st.markdown(f"**Login sebagai:** {st.session_state.user} ({st.session_state.role})")
        if st.button("Tambah Bahan", use_container_width=True):
            tambah_bahan_dialog()
        if st.button("Ganti Password", use_container_width=True):
            change_password_dialog()
        if st.button("Refresh Data", use_container_width=True):
            clear_all_data_cache(); st.rerun()
        if st.button("Logout", use_container_width=True):
            logout()
    render_user_admin()
    df = load_bahan()
    if df.empty:
        st.info("Belum ada data bahan."); return
    with st.sidebar:
        st.markdown("---"); st.subheader("Filter Data")
        tahun_list = sorted([int(x) for x in df["tahun"].dropna().unique().tolist()]) if df["tahun"].notna().any() else [datetime.now().year]
        tahun_pilih = st.selectbox("Tahun", tahun_list, index=max(len(tahun_list)-1, 0))
        triwulan_filter = st.selectbox("Triwulan", ["Semua", "I", "II", "III", "IV"])
        scope = st.selectbox("Tampilan", ["Tugas Saya", "Semua Bahan"] if st.session_state.role == "pic" else ["Semua Bahan"], index=0)
        keyword = st.text_input("Search Keyword", placeholder="Nama bahan / instruksi")
        all_pics = sorted({pic for val in df["pic_list"].astype(str).tolist() for pic in split_pic_list(val)})
        pic_filter = st.selectbox("PIC", ["Semua"] + all_pics)
        kantor_list = sorted(df["kantor"].dropna().astype(str).unique().tolist())
        kantor_filter = st.selectbox("Kantor", ["Semua"] + kantor_list)
        jenis_list = sorted(df["jenis_bahan"].dropna().astype(str).unique().tolist())
        jenis_filter = st.selectbox("Jenis Bahan", ["Semua"] + jenis_list)
        approval_filter = st.selectbox("Approval", ["Semua"] + APPROVAL_OPTIONS)
    filtered = df.copy()
    if st.session_state.role == "pic" and scope == "Tugas Saya":
        filtered = filtered[filtered["pic_list"].apply(lambda x: user_is_in_pic_list(st.session_state.user, str(x)))]
    filtered = filtered[filtered["tahun"] == tahun_pilih] if "tahun" in filtered.columns else filtered
    if triwulan_filter != "Semua":
        filtered = filtered[filtered["triwulan"] == triwulan_filter]
    if keyword.strip():
        key = keyword.strip().lower()
        filtered = filtered[filtered["nama_bahan"].fillna("").astype(str).str.lower().str.contains(key, na=False) | filtered["instruksi"].fillna("").astype(str).str.lower().str.contains(key, na=False)]
    if pic_filter != "Semua":
        filtered = filtered[filtered["pic_list"].apply(lambda x: user_is_in_pic_list(pic_filter, str(x)))]
    if kantor_filter != "Semua":
        filtered = filtered[filtered["kantor"] == kantor_filter]
    if jenis_filter != "Semua":
        filtered = filtered[filtered["jenis_bahan"] == jenis_filter]
    if approval_filter != "Semua":
        filtered = filtered[filtered["approval_status"] == approval_filter]
    if filtered.empty:
        st.info("Tidak ada data yang cocok dengan filter."); return
    sorted_filtered = sort_bahan_df(filtered)
    export_columns = ["tgl_disposisi", "nama_bahan", "kantor", "jenis_bahan", "pic_list", "deadline", "status", "progress", "approval_status", "approved_by", "keterangan", "instruksi", "file_surat", "file_paparan", "file_narasi"]
    export_df = sorted_filtered[[c for c in export_columns if c in sorted_filtered.columns]].copy()
    with st.sidebar:
        st.markdown("---")
        st.download_button("Ekspor Excel", data=dataframe_to_excel_bytes(export_df), file_name=f"daftar_bahan_pimpinan_{tahun_pilih}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    render_kpi(filtered); render_charts(filtered, tahun_pilih); render_table(sorted_filtered)


def main() -> None:
    init_storage()
    if "user" not in st.session_state:
        render_login(); return
    render_dashboard()


if __name__ == "__main__":
    main()
