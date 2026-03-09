from __future__ import annotations

import base64
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Monitoring Bahan Paparan", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = BASE_DIR / "monitoring.db"
LOGO_PATH = BASE_DIR / "logo_kemenperin.png"
STORAGE_DIR = BASE_DIR / "storage"
BACKUP_DIR = BASE_DIR / "backup"

ROLE_OPTIONS = ["admin", "atasan", "pic"]
KANTOR_OPTIONS = ["Pusat", "Tulodong"]
JENIS_OPTIONS = ["Kabinet", "Legislatif", "Instansi", "Lain-lain"]
DEFAULT_USERS = [("admin", "admin123", "admin")]


def file_to_base64(path: Path) -> str:
    with path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def safe_path(p: str | None) -> Path | None:
    if not p:
        return None
    x = Path(p)
    return x if x.is_absolute() else BASE_DIR / x


def ensure_directories() -> None:
    for path in [
        STORAGE_DIR / "disposisi",
        STORAGE_DIR / "output" / "paparan",
        STORAGE_DIR / "output" / "narasi",
        BACKUP_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_directories()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users(
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bahan(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tgl_disposisi TEXT,
                nama_bahan TEXT NOT NULL,
                pic1 TEXT,
                pic2 TEXT,
                kantor TEXT,
                jenis_bahan TEXT,
                instruksi TEXT,
                deadline TEXT,
                status TEXT DEFAULT 'Not Yet Started',
                progress INTEGER DEFAULT 0,
                keterangan TEXT,
                file_surat TEXT,
                file_paparan TEXT,
                file_narasi TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bahan_id INTEGER,
                user TEXT,
                action TEXT,
                timestamp TEXT
            )
            """
        )
        conn.commit()


def seed_default_users() -> None:
    with closing(get_conn()) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
            DEFAULT_USERS,
        )
        conn.commit()


@st.cache_data(ttl=30)
def get_df(query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        return pd.read_sql_query(query, conn, params=params)


def run_sql(query: str, params: tuple[Any, ...] = ()) -> None:
    with closing(get_conn()) as conn:
        conn.execute(query, params)
        conn.commit()
    get_df.clear()


def authenticate(username: str, password: str) -> str | None:
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT role FROM users WHERE username = ? AND password = ?",
            (username.strip(), password),
        ).fetchone()
    return str(row[0]).lower() if row else None


def get_users() -> list[str]:
    df = get_df("SELECT username FROM users ORDER BY username")
    return df["username"].tolist() if not df.empty else []


def get_pic_users() -> list[str]:
    df = get_df("SELECT username FROM users WHERE lower(role) = 'pic' ORDER BY username")
    return df["username"].tolist() if not df.empty else []


def save_uploaded_file(uploaded_file, target_dir: Path) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = uploaded_file.name.replace(" ", "_")
    file_path = target_dir / f"{timestamp}_{safe_name}"
    with file_path.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(file_path.relative_to(BASE_DIR))


def log_action(bahan_id: int, user: str, action: str) -> None:
    run_sql(
        "INSERT INTO audit_log (bahan_id, user, action, timestamp) VALUES (?, ?, ?, ?)",
        (bahan_id, user, action, datetime.now().isoformat(timespec="seconds")),
    )


def logout() -> None:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()


def open_preview(row_id: int, kind: str) -> None:
    st.query_params["preview_id"] = str(row_id)
    st.query_params["kind"] = kind
    st.rerun()


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #f3f5f7;
            --card: #ffffff;
            --text: #152238;
            --muted: #7d8ca5;
            --line: #dde3ea;
            --navy: #0b1a3a;
            --blue: #0e557f;
            --green: #18b26a;
            --orange: #f39b07;
            --red: #f44336;
            --yellow: #f2c300;
            --purple: #a855f7;
            --shadow: 0 4px 16px rgba(15,23,42,0.08);
        }
        [data-testid="stAppViewContainer"] { background: var(--bg); }
        .stApp { color: var(--text); }
        .block-container {
            padding-top: 0.35rem !important;
            padding-bottom: 0.6rem !important;
            padding-left: 0.65rem !important;
            padding-right: 0.65rem !important;
            max-width: 100% !important;
        }
        header[data-testid="stHeader"] { background: transparent; }
        footer { visibility: hidden; }
        [data-testid="stSidebar"] { display: none; }

        .simple-header {
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 14px;
            box-shadow: var(--shadow);
            margin-bottom: 0.8rem;
            overflow: hidden;
        }
        .simple-header-grid {
            display: grid;
            grid-template-columns: 140px 1fr 220px;
            align-items: center;
        }
        .simple-header-logo, .simple-header-right { padding: 0.8rem 1rem; }
        .simple-header-center {
            padding: 0.7rem 1rem;
            border-left: 1px solid var(--line);
            border-right: 1px solid var(--line);
        }
        .simple-header-title {
            font-size: 1.16rem;
            font-weight: 900;
            color: var(--navy);
            line-height: 1.2;
            text-transform: uppercase;
            margin: 0;
        }
        .simple-header-sub {
            color: var(--blue);
            font-weight: 800;
            letter-spacing: 0.12em;
            font-size: 0.74rem;
            margin-top: 0.2rem;
            text-transform: uppercase;
        }
        .simple-header-user {
            text-align: right;
            font-weight: 800;
            color: var(--text);
            font-size: 0.78rem;
            text-transform: capitalize;
        }
        .simple-header-role {
            color: var(--blue);
            font-weight: 900;
            text-transform: uppercase;
            text-align: right;
            font-size: 0.78rem;
        }
        .metric-box {
            background: var(--card);
            border: 1px solid #d5dce5;
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1rem 1rem 0.9rem;
            min-height: 104px;
            position: relative;
            overflow: hidden;
            margin-bottom: 0.85rem;
        }
        .metric-box::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 5px;
            height: 100%;
            background: var(--metric-color, #94a3b8);
        }
        .metric-title { color: #8495b1; font-weight: 800; font-size: 0.76rem; text-transform: uppercase; margin-bottom: 0.7rem; }
        .metric-value { font-size: 2rem; line-height: 1; font-weight: 900; color: var(--navy); }
        .chart-card, .table-shell {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1rem;
            margin-bottom: 0.95rem;
        }
        .card-title { color: #21456d; font-size: 0.95rem; font-weight: 900; margin-bottom: 0.65rem; }
        .table-title { color: #55739a; font-size: 0.98rem; font-weight: 900; font-style: italic; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.8rem; }
        .filter-label { color: #8b9bb3; font-size: 0.72rem; font-weight: 800; text-transform: uppercase; margin-bottom: 0.2rem; }
        .table-header-row { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 0.6rem 0; margin-top: 0.5rem; margin-bottom: 0.2rem; }
        .table-header-cell { color: #8b9bb3; font-size: 0.76rem; font-weight: 900; text-transform: uppercase; }
        .title-main { font-weight: 900; color: var(--navy); font-size: 0.98rem; margin-bottom: 0.14rem; }
        .meta-line { color: #64748b; font-size: 0.78rem; line-height: 1.25; }
        .tiny-badge { display: inline-block; background: #e8f3ff; color: #0e557f; font-weight: 800; border-radius: 8px; padding: 0.18rem 0.45rem; font-size: 0.68rem; margin-right: 0.5rem; margin-top: 0.18rem; }
        .pill-status { display: inline-block; padding: 0.26rem 0.7rem; border-radius: 999px; font-size: 0.76rem; font-weight: 900; }
        .status-done { background: #e7f7ef; color: #00995b; }
        .status-progress { background: #fff2dd; color: #cc7a00; }
        .status-notyet { background: #eef2f6; color: #64748b; }
        .progress-wrap { height: 10px; border-radius: 999px; background: #e7edf4; overflow: hidden; margin-top: 0.35rem; margin-bottom: 0.18rem; }
        .progress-bar { height: 10px; border-radius: 999px; background: #0e557f; }
        .progress-text { color: #55739a; font-size: 0.78rem; font-weight: 800; }
        .top-action .stButton > button,
        .logout-action .stButton > button { border-radius: 16px; min-height: 56px; font-weight: 900; }
        .top-action .stButton > button { background: #0e557f; color: white; border: none; box-shadow: 0 6px 14px rgba(14,85,127,0.22); }
        .table-shell .stButton > button { min-height: 34px; padding-top: 0; padding-bottom: 0; border-radius: 12px; }
        .admin-wrap { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 0.8rem; margin-bottom: 0.9rem; }

        @media (max-width: 900px) {
            .simple-header-grid { grid-template-columns: 1fr; }
            .simple-header-center { border-left: none; border-right: none; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
            .simple-header-user, .simple-header-role { text-align: left; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display:none; }
        header, footer { visibility:hidden; }
        .block-container {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            max-width: 100% !important;
        }
        .login-page {
            min-height: 100vh;
            background: linear-gradient(90deg, #081633 0 26%, #f6f7f9 26% 74%, #081633 74% 100%);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-panel { width: min(620px, 92vw); padding: 1rem 0; }
        .login-title { text-align:center; color:#14233d; font-size:2.2rem; line-height:1.15; font-weight:900; margin:0.65rem 0 0.5rem 0; text-transform:uppercase; }
        .login-sub { text-align:center; color:#8898b2; font-size:1rem; margin-bottom:1.2rem; }
        .login-footer { text-align:center; color:#cbd5e1; font-weight:800; letter-spacing:0.12em; margin-top:1.5rem; }
        .field-label { color:#8b9bb3; font-weight:900; font-size:0.9rem; text-transform:uppercase; margin-bottom:0.25rem; }
        .login-wrap .stSelectbox, .login-wrap .stTextInput { margin-bottom: 0.65rem; }
        .login-wrap .stSelectbox > div > div, .login-wrap .stTextInput > div > div > input {
            border-radius:18px !important; min-height:62px !important; border:1px solid #dfe6ef !important;
            font-size:1.05rem !important; font-weight:700 !important; background:#fbfcfe !important;
        }
        .login-wrap .stButton > button {
            width:100%; min-height:64px; border-radius:18px; background:#0e557f; color:white;
            font-size:1rem; font-weight:900; border:none; box-shadow:0 8px 18px rgba(14,85,127,0.25);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='login-page'><div class='login-panel login-wrap'>", unsafe_allow_html=True)
    if LOGO_PATH.exists():
        with st.columns([1, 1, 1])[1]:
            st.image(str(LOGO_PATH), width=140)
    st.markdown("<div class='login-title'>Dashboard Monitoring<br>Bahan Paparan</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-sub'>Silakan masuk ke akun Anda</div>", unsafe_allow_html=True)
    with st.columns([0.2, 0.6, 0.2])[1]:
        users = [""] + get_users()
        st.markdown("<div class='field-label'>Pilih Pengguna</div>", unsafe_allow_html=True)
        username = st.selectbox("Pilih Pengguna", users, format_func=lambda x: "-- Pilih User --" if x == "" else x, label_visibility="collapsed")
        st.markdown("<div class='field-label'>Password</div>", unsafe_allow_html=True)
        password = st.text_input("Password", type="password", placeholder="Masukkan password", label_visibility="collapsed")
        if st.button("MASUK SEKARANG"):
            role = authenticate(username, password)
            if role:
                st.session_state.user = username.strip()
                st.session_state.role = role
                st.rerun()
            st.error("Username atau password salah.")
    st.markdown("<div class='login-footer'>BAGIAN PDSIA - KEMENPERIN 2026</div></div></div>", unsafe_allow_html=True)


def render_preview() -> None:
    params = st.query_params
    preview_id = params.get("preview_id")
    kind = params.get("kind")
    if not preview_id or not kind:
        return
    try:
        row_id = int(preview_id[0] if isinstance(preview_id, list) else preview_id)
    except Exception:
        st.error("Parameter preview_id tidak valid.")
        st.stop()
    kind = kind[0] if isinstance(kind, list) else kind
    mapping = {
        "surat": ("file_surat", "Preview Surat / Disposisi"),
        "paparan": ("file_paparan", "Preview Paparan"),
        "narasi": ("file_narasi", "Preview Narasi"),
    }
    if kind not in mapping:
        st.error("Parameter kind tidak valid.")
        st.stop()
    df_prev = get_df("SELECT id, nama_bahan, file_surat, file_paparan, file_narasi FROM bahan WHERE id = ?", (row_id,))
    if df_prev.empty:
        st.error("Data tidak ditemukan.")
        st.stop()
    row = df_prev.iloc[0]
    col_name, title = mapping[kind]
    file_path = safe_path(row[col_name])
    c1, c2 = st.columns([1, 6])
    with c1:
        if st.button("⬅ Kembali", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with c2:
        st.markdown(f"### {title}")
        st.caption(f"Bahan: {row['nama_bahan']}")
    if not file_path or not file_path.exists():
        st.info("File belum tersedia.")
        st.stop()
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        with file_path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900" style="border:none;border-radius:18px;background:white;"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        with file_path.open("rb") as f:
            st.download_button("Download file", f, file_name=file_path.name)
        st.info("Preview inline saat ini hanya untuk PDF.")
    st.stop()


@st.dialog("Tambah Bahan Paparan")
def add_bahan_dialog() -> None:
    daftar_pic = get_pic_users()
    if not daftar_pic:
        st.warning("Belum ada user PIC. Tambahkan user PIC terlebih dahulu di Kelola User.")
        return
    with st.form("form_tambah_bahan_dialog", clear_on_submit=True):
        nama = st.text_input("Nama Bahan")
        c1, c2 = st.columns(2)
        with c1:
            tgl_disposisi = st.date_input("Tanggal Disposisi")
            pic1 = st.selectbox("PIC 1", daftar_pic)
            kantor = st.selectbox("Tim Kerja", KANTOR_OPTIONS)
        with c2:
            deadline = st.date_input("Deadline")
            pic2 = st.selectbox("PIC 2", daftar_pic)
            jenis = st.selectbox("Jenis Bahan", JENIS_OPTIONS)
        instruksi = st.text_area("Keyword / Instruksi", height=100)
        file_surat = st.file_uploader("Upload Surat / Disposisi", type=["pdf", "docx"])
        b1, b2 = st.columns(2)
        submitted = b1.form_submit_button("Simpan", use_container_width=True)
        cancelled = b2.form_submit_button("Batal", use_container_width=True)
    if cancelled:
        st.rerun()
    if not submitted:
        return
    if not nama.strip():
        st.error("Nama bahan wajib diisi.")
        return
    if pic1 == pic2:
        st.error("PIC 1 dan PIC 2 tidak boleh sama.")
        return
    file_path = ""
    if file_surat:
        file_path = save_uploaded_file(file_surat, STORAGE_DIR / "disposisi" / str(pd.Timestamp(tgl_disposisi).year))
    run_sql(
        """
        INSERT INTO bahan (
            tgl_disposisi, nama_bahan, pic1, pic2, kantor, jenis_bahan,
            instruksi, deadline, status, progress, file_surat
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(tgl_disposisi), nama.strip(), pic1, pic2, kantor, jenis,
            instruksi, str(deadline), "Not Yet Started", 0, file_path,
        ),
    )
    st.success("Bahan berhasil ditambahkan.")
    st.rerun()


@st.dialog("Edit Bahan Paparan")
def edit_dialog(edit_id: int) -> None:
    df_edit = get_df("SELECT * FROM bahan WHERE id = ?", (edit_id,))
    if df_edit.empty:
        st.error("Data tidak ditemukan.")
        return
    row = df_edit.iloc[0]
    daftar_pic = get_pic_users() or [row["pic1"], row["pic2"]]
    with st.form(f"edit_form_{edit_id}"):
        nama = st.text_input("Nama Bahan", value=row["nama_bahan"])
        c1, c2 = st.columns(2)
        with c1:
            tgl_disposisi = st.date_input("Tanggal Disposisi", value=pd.to_datetime(row["tgl_disposisi"]).date() if pd.notna(row["tgl_disposisi"]) else datetime.today().date())
            pic1 = st.selectbox("PIC 1", daftar_pic, index=max(0, daftar_pic.index(row["pic1"])) if row["pic1"] in daftar_pic else 0)
            kantor = st.selectbox("Tim Kerja", KANTOR_OPTIONS, index=KANTOR_OPTIONS.index(row["kantor"]) if row["kantor"] in KANTOR_OPTIONS else 0)
        with c2:
            deadline = st.date_input("Deadline", value=pd.to_datetime(row["deadline"]).date() if pd.notna(row["deadline"]) else datetime.today().date())
            pic2 = st.selectbox("PIC 2", daftar_pic, index=max(0, daftar_pic.index(row["pic2"])) if row["pic2"] in daftar_pic else 0)
            jenis = st.selectbox("Jenis Bahan", JENIS_OPTIONS, index=JENIS_OPTIONS.index(row["jenis_bahan"]) if row["jenis_bahan"] in JENIS_OPTIONS else 0)
        instruksi = st.text_area("Keyword / Instruksi", value=row["instruksi"] or "", height=100)
        status = st.selectbox("Status", ["Not Yet Started", "On Progress", "Done"], index=["Not Yet Started", "On Progress", "Done"].index(row["status"]) if row["status"] in ["Not Yet Started", "On Progress", "Done"] else 0)
        progress = st.slider("Progress", 0, 100, int(row["progress"] or 0), 5)
        keterangan = st.text_area("Keterangan", value=row["keterangan"] or "", height=80)
        paparan = st.file_uploader("Upload Paparan", type=["pdf", "ppt", "pptx"], key=f"paparan_{edit_id}")
        narasi = st.file_uploader("Upload Narasi", type=["pdf", "doc", "docx"], key=f"narasi_{edit_id}")
        c3, c4 = st.columns(2)
        saved = c3.form_submit_button("Simpan Perubahan", use_container_width=True)
        cancel = c4.form_submit_button("Batal", use_container_width=True)
    if cancel:
        st.rerun()
    if not saved:
        return
    file_paparan = row["file_paparan"]
    file_narasi = row["file_narasi"]
    if paparan:
        file_paparan = save_uploaded_file(paparan, STORAGE_DIR / "output" / "paparan")
    if narasi:
        file_narasi = save_uploaded_file(narasi, STORAGE_DIR / "output" / "narasi")
    run_sql(
        """
        UPDATE bahan
        SET tgl_disposisi=?, nama_bahan=?, pic1=?, pic2=?, kantor=?, jenis_bahan=?,
            instruksi=?, deadline=?, status=?, progress=?, keterangan=?, file_paparan=?, file_narasi=?
        WHERE id=?
        """,
        (
            str(tgl_disposisi), nama.strip(), pic1, pic2, kantor, jenis,
            instruksi, str(deadline), status, progress, keterangan, file_paparan, file_narasi, edit_id,
        ),
    )
    log_action(edit_id, st.session_state.user, "update bahan")
    st.success("Data berhasil diupdate.")
    st.rerun()


@st.dialog("Konfirmasi Hapus")
def delete_dialog(bahan_id: int, nama_bahan: str) -> None:
    st.warning(f"Yakin ingin menghapus **{nama_bahan}**?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Ya, Hapus", use_container_width=True):
            run_sql("DELETE FROM bahan WHERE id = ?", (bahan_id,))
            log_action(bahan_id, st.session_state.user, "delete bahan")
            st.success("Data berhasil dihapus.")
            st.rerun()
    with c2:
        if st.button("Batal", use_container_width=True):
            st.rerun()


def render_user_admin() -> None:
    st.markdown('<div class="admin-wrap">', unsafe_allow_html=True)
    menu = st.radio("Menu Admin", ["Tambah User", "Kelola User"], horizontal=True)
    if menu == "Tambah User":
        c1, c2, c3 = st.columns(3)
        username = c1.text_input("Username Baru")
        password = c2.text_input("Password Baru", type="password")
        role = c3.selectbox("Role", ROLE_OPTIONS)
        if st.button("Simpan User"):
            if not username.strip() or not password:
                st.error("Username dan password wajib diisi.")
            else:
                try:
                    run_sql("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username.strip(), password, role))
                    st.success("User berhasil ditambahkan.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username sudah digunakan.")
    else:
        df_users = get_df("SELECT * FROM users ORDER BY username")
        if df_users.empty:
            st.info("Belum ada user.")
        else:
            selected = st.selectbox("Pilih User", df_users["username"].tolist())
            user_data = df_users[df_users["username"] == selected].iloc[0]
            c1, c2 = st.columns(2)
            new_password = c1.text_input("Password Baru (opsional)", type="password")
            new_role = c2.selectbox("Role", ROLE_OPTIONS, index=ROLE_OPTIONS.index(str(user_data["role"]).lower()) if str(user_data["role"]).lower() in ROLE_OPTIONS else 0)
            b1, b2 = st.columns(2)
            if b1.button("Update"):
                if new_password:
                    run_sql("UPDATE users SET password = ?, role = ? WHERE username = ?", (new_password, new_role, selected))
                else:
                    run_sql("UPDATE users SET role = ? WHERE username = ?", (new_role, selected))
                st.success("User berhasil diupdate.")
                st.rerun()
            if b2.button("Hapus"):
                if selected == st.session_state.user:
                    st.error("Tidak bisa menghapus akun sendiri.")
                else:
                    run_sql("DELETE FROM users WHERE username = ?", (selected,))
                    st.success("User berhasil dihapus.")
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def load_data() -> pd.DataFrame:
    df = get_df("SELECT * FROM bahan ORDER BY tgl_disposisi DESC, id DESC")
    if df.empty:
        return df
    df["tgl_disposisi"] = pd.to_datetime(df["tgl_disposisi"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["tgl_disposisi"]).copy()
    df["tahun"] = df["tgl_disposisi"].dt.year
    if st.session_state.role == "pic":
        user = st.session_state.user
        df = df[(df["pic1"] == user) | (df["pic2"] == user)].copy()
    return df


def render_header() -> None:
    logo_html = f'<img src="data:image/png;base64,{file_to_base64(LOGO_PATH)}" width="74">' if LOGO_PATH.exists() else ""
    st.markdown(
        f"""
        <div class="simple-header">
            <div class="simple-header-grid">
                <div class="simple-header-logo">{logo_html}</div>
                <div class="simple-header-center">
                    <div class="simple-header-title">Dashboard Monitoring Penyusunan Bahan Paparan Pimpinan</div>
                    <div class="simple-header-sub">PDSIA Pusat &amp; Tulodong</div>
                </div>
                <div class="simple-header-right">
                    <div class="simple-header-user">{st.session_state.user}</div>
                    <div class="simple-header-role">{str(st.session_state.role).upper()}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi(df: pd.DataFrame) -> None:
    total = len(df)
    proses = int((df["status"] == "On Progress").sum())
    selesai = int((df["status"] == "Done").sum())
    ditunda = int((df["status"] == "Not Yet Started").sum())
    pusat = int((df["kantor"] == "Pusat").sum())
    tulodong = int((df["kantor"] == "Tulodong").sum())
    cards = [
        ("TOTAL BAHAN", total, "#94a3b8"),
        ("PROSES", proses, "#f44336"),
        ("SELESAI", selesai, "#10b981"),
        ("DITUNDA", ditunda, "#f59e0b"),
        ("PUSAT", pusat, "#f2c300"),
        ("TULODONG", tulodong, "#a855f7"),
    ]
    cols = st.columns(6)
    for col, (title, value, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="metric-box" style="--metric-color:{color}">
                    <div class="metric-title">{title}</div>
                    <div class="metric-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_charts(df: pd.DataFrame, tahun_pilih: int) -> None:
    col1, col2, col3 = st.columns(3)
    jenis = df["jenis_bahan"].fillna("-").value_counts().reset_index()
    jenis.columns = ["Kategori", "Jumlah"]
    with col1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">◔ Distribusi Kategori</div>', unsafe_allow_html=True)
        fig = px.pie(jenis, names="Kategori", values="Jumlah", hole=0.68)
        fig.update_layout(height=320, margin=dict(l=5, r=5, t=5, b=5), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">≣ Beban Kerja Tim</div>', unsafe_allow_html=True)
        df_pic = pd.concat([
            df[["pic1"]].rename(columns={"pic1": "PIC"}),
            df[["pic2"]].rename(columns={"pic2": "PIC"}),
        ], ignore_index=True).dropna()
        if df_pic.empty:
            st.info("Belum ada data PIC.")
        else:
            beban = df_pic["PIC"].value_counts().reset_index()
            beban.columns = ["PIC", "Jumlah"]
            fig = px.bar(beban, y="PIC", x="Jumlah", orientation="h")
            fig.update_layout(height=320, margin=dict(l=5, r=5, t=5, b=5), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">▤ Final per Tim Kerja</div>', unsafe_allow_html=True)
        final_df = df[df["status"] == "Done"]
        kantor = final_df["kantor"].fillna("-").value_counts().reindex(KANTOR_OPTIONS, fill_value=0).reset_index()
        kantor.columns = ["Tim", "Jumlah"]
        fig = px.bar(kantor, x="Tim", y="Jumlah", text="Jumlah")
        fig.update_layout(height=320, margin=dict(l=5, r=5, t=5, b=5), showlegend=False, yaxis=dict(dtick=1))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    col4, col5 = st.columns(2)
    with col4:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">↗ Tren Bulanan ({tahun_pilih})</div>', unsafe_allow_html=True)
        trend = df.copy()
        trend["bulan_angka"] = trend["tgl_disposisi"].dt.month
        trend["bulan"] = trend["tgl_disposisi"].dt.strftime("%b")
        bulanan = trend.groupby(["bulan_angka", "bulan"]).size().reset_index(name="Jumlah").sort_values("bulan_angka")
        fig = px.line(bulanan, x="bulan", y="Jumlah", markers=True)
        fig.update_layout(height=250, margin=dict(l=5, r=5, t=5, b=5), showlegend=False, yaxis=dict(dtick=1))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with col5:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">▮ Tren Triwulanan ({tahun_pilih})</div>', unsafe_allow_html=True)
        tri = df.copy()
        tri["triwulan_angka"] = tri["tgl_disposisi"].dt.quarter
        tri["Triwulan"] = tri["triwulan_angka"].map({1: "TW I", 2: "TW II", 3: "TW III", 4: "TW IV"})
        triwulan = tri.groupby(["triwulan_angka", "Triwulan"]).size().reset_index(name="Jumlah").sort_values("triwulan_angka")
        fig = px.bar(triwulan, x="Triwulan", y="Jumlah", text="Jumlah")
        fig.update_layout(height=250, margin=dict(l=5, r=5, t=5, b=5), showlegend=False, yaxis=dict(dtick=1))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="table-shell">', unsafe_allow_html=True)
    st.markdown('<div class="table-title">Daftar Bahan Paparan</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = st.columns([1.5, 1.5, 1.4, 1.4, 0.6])
    with f1:
        st.markdown('<div class="filter-label">Cari Judul</div>', unsafe_allow_html=True)
        judul = st.text_input('Cari Judul', placeholder='Ketik judul...', label_visibility='collapsed', key='filter_judul')
    with f2:
        st.markdown('<div class="filter-label">Keyword</div>', unsafe_allow_html=True)
        keyword = st.text_input('Keyword', placeholder='Cari keyword...', label_visibility='collapsed', key='filter_keyword')
    with f3:
        st.markdown('<div class="filter-label">Kategori</div>', unsafe_allow_html=True)
        kategori = st.selectbox('Kategori', ['Semua'] + sorted(df['jenis_bahan'].dropna().unique().tolist()), label_visibility='collapsed', key='filter_kategori')
    with f4:
        st.markdown('<div class="filter-label">Tim Kerja</div>', unsafe_allow_html=True)
        tim = st.selectbox('Tim Kerja', ['Semua'] + sorted(df['kantor'].dropna().unique().tolist()), label_visibility='collapsed', key='filter_tim')
    with f5:
        st.markdown('<div class="filter-label">&nbsp;</div>', unsafe_allow_html=True)
        if st.button('Reset', use_container_width=True):
            st.session_state['filter_judul'] = ''
            st.session_state['filter_keyword'] = ''
            st.session_state['filter_kategori'] = 'Semua'
            st.session_state['filter_tim'] = 'Semua'
            st.rerun()

    filtered = df.copy()
    if judul.strip():
        filtered = filtered[filtered['nama_bahan'].fillna('').str.contains(judul, case=False, na=False)]
    if keyword.strip():
        filtered = filtered[
            filtered['instruksi'].fillna('').str.contains(keyword, case=False, na=False)
            | filtered['nama_bahan'].fillna('').str.contains(keyword, case=False, na=False)
        ]
    if kategori != 'Semua':
        filtered = filtered[filtered['jenis_bahan'] == kategori]
    if tim != 'Semua':
        filtered = filtered[filtered['kantor'] == tim]

    hcols = st.columns([3.1, 1.2, 2.0, 1.2, 1.3, 1.2, 1.1])
    headers = ['Judul & Kategori', 'Tim Kerja', 'PIC (Lead & Support)', 'Status', 'Progres', 'Aksi Dokumen', 'Update']
    st.markdown('<div class="table-header-row">', unsafe_allow_html=True)
    for c, t in zip(hcols, headers):
        c.markdown(f"<div class='table-header-cell'>{t}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    for _, row in filtered.sort_values(['deadline', 'id'], ascending=[True, False]).iterrows():
        prog = max(0, min(100, int(row['progress'] or 0)))
        status_class = 'status-done' if row['status'] == 'Done' else 'status-progress' if row['status'] == 'On Progress' else 'status-notyet'
        cols = st.columns([3.1, 1.2, 2.0, 1.2, 1.3, 1.2, 1.1])
        with cols[0]:
            st.markdown(f"<div class='title-main'>{row['nama_bahan']}</div>", unsafe_allow_html=True)
            tanggal = f"📅 {row['deadline'].date()}" if pd.notna(row['deadline']) else ''
            st.markdown(f"<span class='tiny-badge'>{(row['jenis_bahan'] or '-').upper()}</span><span class='meta-line'>{tanggal}</span>", unsafe_allow_html=True)
        with cols[1]:
            st.markdown(f"<div class='meta-line'><b>{row['kantor'] or '-'}</b></div>", unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"<div class='meta-line'>🔵 {row['pic1'] or '-'}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='meta-line'>🟣 {row['pic2'] or '-'}</div>", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<span class='pill-status {status_class}'>{row['status']}</span>", unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f"<div class='progress-wrap'><div class='progress-bar' style='width:{prog}%'></div></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='progress-text'>{prog}%</div>", unsafe_allow_html=True)
        with cols[5]:
            surat = safe_path(row['file_surat'])
            paparan = safe_path(row['file_paparan'])
            narasi = safe_path(row['file_narasi'])
            if surat and surat.exists():
                if st.button('DOKUMEN', key=f'doc_{row["id"]}', use_container_width=True):
                    open_preview(int(row['id']), 'surat')
            else:
                st.caption('Belum ada')
            b1, b2 = st.columns(2)
            with b1:
                if paparan and paparan.exists() and st.button('Paparan', key=f'pap_{row["id"]}', use_container_width=True):
                    open_preview(int(row['id']), 'paparan')
            with b2:
                if narasi and narasi.exists() and st.button('Narasi', key=f'nar_{row["id"]}', use_container_width=True):
                    open_preview(int(row['id']), 'narasi')
        with cols[6]:
            can_edit = st.session_state.role in {'admin', 'atasan'} or st.session_state.user in {row['pic1'], row['pic2']}
            can_delete = st.session_state.role in {'admin', 'atasan'}
            a1, a2 = st.columns(2)
            with a1:
                if st.button('Edit', key=f'edit_{row["id"]}', use_container_width=True, disabled=not can_edit):
                    edit_dialog(int(row['id']))
            with a2:
                if st.button('Hapus', key=f'del_{row["id"]}', use_container_width=True, disabled=not can_delete):
                    delete_dialog(int(row['id']), str(row['nama_bahan']))
        st.divider()
    st.markdown('</div>', unsafe_allow_html=True)


def render_dashboard() -> None:
    inject_global_css()
    render_header()
    top1, top2 = st.columns([8, 1.3])
    with top1:
        st.markdown('<div class="top-action">', unsafe_allow_html=True)
        if st.button('➕ Tambah Paparan', use_container_width=True):
            add_bahan_dialog()
        st.markdown('</div>', unsafe_allow_html=True)
    with top2:
        st.markdown('<div class="logout-action">', unsafe_allow_html=True)
        if st.button('Logout', use_container_width=True):
            logout()
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.role == 'admin':
        with st.expander('Kelola User', expanded=False):
            render_user_admin()

    df = load_data()
    if df.empty:
        st.warning('Belum ada data bahan.')
        return
    tahun_list = sorted(df['tahun'].dropna().unique().tolist())
    tahun_pilih = st.selectbox('Tahun', tahun_list, key='tahun_global')
    filtered = df[df['tahun'] == tahun_pilih].copy()
    if filtered.empty:
        st.info('Tidak ada data untuk tahun terpilih.')
        return
    render_kpi(filtered)
    render_charts(filtered, tahun_pilih)
    render_table(filtered)


def main() -> None:
    init_db()
    seed_default_users()
    if 'user' not in st.session_state:
        render_login()
        return
    inject_global_css()
    render_preview()
    render_dashboard()


if __name__ == '__main__':
    main()
