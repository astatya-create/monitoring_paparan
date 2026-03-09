from __future__ import annotations

import base64
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Monitoring Bahan Paparan", layout="wide")

# =========================
# PATHS & CONSTANTS
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = BASE_DIR / "monitoring.db"
LOGO_PATH = BASE_DIR / "logo_kemenperin.png"
STORAGE_DIR = BASE_DIR / "storage"
BACKUP_DIR = BASE_DIR / "backup"

STATUS_OPTIONS = ["Not Yet Started", "On Progress", "Done"]
ROLE_OPTIONS = ["admin", "atasan", "pic"]
KANTOR_OPTIONS = ["Tulodong", "Pusat"]
JENIS_OPTIONS = ["Kabinet", "Legislatif", "Instansi", "Lain-lain"]
PUSAT_ADMIN = ("admin", "admin123", "admin")


# =========================
# HELPERS
# =========================
def file_to_base64(file_path: Path) -> str:
    with file_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def safe_path(relative_or_abs: str | None) -> Path | None:
    if not relative_or_abs:
        return None
    p = Path(relative_or_abs)
    return p if p.is_absolute() else BASE_DIR / p


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
        cur.execute(
            """
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES (?, ?, ?)
            """,
            PUSAT_ADMIN,
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
    return row[0] if row else None


def get_pic_users() -> list[str]:
    df = get_df("SELECT username FROM users WHERE role = 'pic' ORDER BY username")
    return df["username"].tolist() if not df.empty else []


def log_action(bahan_id: int, user: str, action: str) -> None:
    run_sql(
        "INSERT INTO audit_log (bahan_id, user, action, timestamp) VALUES (?, ?, ?, ?)",
        (bahan_id, user, action, datetime.now().isoformat(timespec="seconds")),
    )


def save_uploaded_file(uploaded_file, target_dir: Path) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = uploaded_file.name.replace(" ", "_")
    file_path = target_dir / f"{timestamp}_{safe_name}"
    with file_path.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(file_path.relative_to(BASE_DIR))


def logout() -> None:
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()


# =========================
# UI STYLES
# =========================
def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { background-color: #f6f8fc; }
        header, footer { visibility: hidden; }
        .block-container { padding-top: 0.6rem; }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b1f3a 0%, #12345f 100%);
        }
        [data-testid="stSidebar"] * { color: #ffffff !important; }
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stDateInput label {
            color: #dbeafe !important;
            font-weight: 700 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] .stTextInput input,
        [data-testid="stSidebar"] .stDateInput input {
            background: rgba(255,255,255,0.08) !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
            color: #ffffff !important;
        }

        .dashboard-header {
            width: 100%;
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 18px;
            padding: 18px 22px;
            margin-bottom: 18px;
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
        }
        .dashboard-header-inner {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            flex-wrap: wrap;
        }
        .dashboard-header-left {
            display: flex;
            align-items: center;
            gap: 14px;
            min-width: 0;
        }
        .dashboard-header-logo {
            width: 74px;
            height: 74px;
            object-fit: contain;
            flex-shrink: 0;
        }
        .dashboard-header-title {
            color: #10233f;
            font-size: 2.45rem;
            line-height: 1.06;
            font-weight: 900;
            margin: 0 0 6px 0;
            letter-spacing: -0.02em;
        }
        .dashboard-header-subtitle {
            color: #1d4f7a;
            font-size: 1.05rem;
            font-weight: 800;
            margin: 0;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }
        .dashboard-header-user {
            text-align: right;
            color: #10233f;
            min-width: 180px;
            border-left: 1px solid #dbe4f0;
            padding-left: 18px;
        }
        .dashboard-header-user-name {
            font-size: 1.35rem;
            font-weight: 900;
            margin: 0;
        }
        .dashboard-header-user-role {
            font-size: 1rem;
            font-weight: 800;
            color: #1d4f7a;
            margin: 4px 0 0 0;
            text-transform: uppercase;
        }

        .hero-action button {
            min-height: 54px;
            border-radius: 16px !important;
            font-size: 1.08rem !important;
            font-weight: 800 !important;
            background: linear-gradient(90deg, #134b76 0%, #0f3d63 100%) !important;
            color: #ffffff !important;
            border: none !important;
            box-shadow: 0 10px 22px rgba(15, 76, 121, 0.18) !important;
        }

        .kpi-card {
            background: white;
            padding: 16px 18px;
            border-radius: 18px;
            box-shadow: 0 4px 16px rgba(15,23,42,0.06);
            margin-bottom: 10px;
        }
        .kpi-title { color:#64748b; font-size:13px; font-weight:800; letter-spacing:.08em; }
        .kpi-value { color:#0f172a; font-size:30px; font-weight:800; }
        .section-title { color:#0c4a6e; font-size:21px; font-weight:900; margin:20px 0 10px; }
        .table-card {
            background:white;
            border-radius:18px;
            padding:16px 18px;
            box-shadow:0 4px 16px rgba(15,23,42,0.06);
            margin-top: 18px;
        }
        .badge {
            display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px;
            background:#e0f2fe; color:#075985; font-weight:700;
        }
        .pill {
            display:inline-block; padding:6px 10px; border-radius:999px; font-weight:800; font-size:12px;
        }
        .pill.notyet { background:#e2e8f0; color:#334155; }
        .pill.progress { background:#fef3c7; color:#92400e; }
        .pill.done { background:#dcfce7; color:#166534; }
        .compact-row [data-testid="stHorizontalBlock"] { align-items: start; }
        .compact-row p,
        .compact-row [data-testid="stMarkdownContainer"] p { margin-bottom: 0.15rem !important; }
        .output-btn button, .table-action button {
            min-height: 2.25rem !important;
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
            border-radius: 10px !important;
        }

        @media (max-width: 900px) {
            .dashboard-header { padding: 16px 16px; border-radius: 16px; }
            .dashboard-header-title { font-size: 1.75rem; }
            .dashboard-header-logo { width: 58px; height: 58px; }
            .dashboard-header-user {
                border-left: none;
                padding-left: 0;
                min-width: auto;
                width: 100%;
                text-align: left;
            }
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
        .block-container { padding-top: 0.5rem !important; }
        .login-shell {
            max-width: 560px;
            margin: 0 auto;
            text-align: center;
            padding-top: 0.6rem;
        }
        .login-title {
            color: #10233f;
            font-size: 2.55rem;
            font-weight: 900;
            line-height: 1.1;
            margin-bottom: 10px;
        }
        .login-subtitle {
            color: #7b8daa;
            font-size: 1.15rem;
            font-weight: 600;
            margin-bottom: 24px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='login-shell'>", unsafe_allow_html=True)
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=120)
    st.markdown("<div class='login-title'>DASHBOARD MONITORING<br>BAHAN PAPARAN</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-subtitle'>Silakan masuk ke akun Anda</div>", unsafe_allow_html=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Masuk", use_container_width=True):
        role = authenticate(username, password)
        if role:
            st.query_params.clear()
            st.session_state.user = username.strip()
            st.session_state.role = role.lower()
            st.rerun()
        st.error("Username atau password salah.")
    st.markdown("</div>", unsafe_allow_html=True)

def render_preview() -> None:
    params = st.query_params
    preview_id = params.get("preview_id")
    kind = params.get("kind")
    if not preview_id or not kind:
        return

    try:
        row_id = int(preview_id[0] if isinstance(preview_id, list) else preview_id)
    except Exception:
        st.query_params.clear()
        st.error("Parameter preview_id tidak valid.")
        st.stop()

    kind = kind[0] if isinstance(kind, list) else kind
    column_map = {
        "surat": ("file_surat", "Preview Surat"),
        "paparan": ("file_paparan", "Preview Paparan"),
        "narasi": ("file_narasi", "Preview Narasi"),
    }
    if kind not in column_map:
        st.query_params.clear()
        st.error("Parameter kind tidak valid.")
        st.stop()

    if st.button("⬅ Kembali ke dashboard"):
        st.query_params.clear()
        st.rerun()

    df_prev = get_df(
        "SELECT id, nama_bahan, file_surat, file_paparan, file_narasi FROM bahan WHERE id = ?",
        (row_id,),
    )
    if df_prev.empty:
        st.query_params.clear()
        st.error("Data tidak ditemukan.")
        st.stop()

    row = df_prev.iloc[0]
    col_name, title = column_map[kind]
    file_path = safe_path(row[col_name])

    st.subheader(f"{title} — {row['nama_bahan']}")
    if not file_path or not file_path.exists():
        st.info("File belum tersedia.")
        st.stop()

    ext = file_path.suffix.lower()
    size_limit = 200 * 1024 * 1024

    if ext == ".pdf" and file_path.stat().st_size <= size_limit:
        with file_path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900" style="border:none;border-radius:12px;"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        with file_path.open("rb") as f:
            st.download_button("Download file", f, file_name=file_path.name)
        if ext != ".pdf":
            st.info("Preview inline saat ini hanya untuk PDF.")
    st.stop()

def render_tambah_bahan() -> None:
    if st.session_state.role not in {"admin", "atasan", "pic"}:
        return
    st.markdown("<div class='hero-action'>", unsafe_allow_html=True)
    if st.button("＋ Tambah Bahan", use_container_width=True):
        tambah_bahan_dialog()
    st.markdown("</div>", unsafe_allow_html=True)

def render_user_admin() -> None:
    if st.session_state.role != "admin":
        return

    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Menu Admin", ["Tambah User", "Kelola User"])

    if menu == "Tambah User":
        st.sidebar.subheader("Tambah User")
        username = st.sidebar.text_input("Username Baru")
        password = st.sidebar.text_input("Password Baru", type="password")
        role = st.sidebar.selectbox("Role", ROLE_OPTIONS)
        if st.sidebar.button("Simpan User"):
            if not username.strip() or not password:
                st.sidebar.error("Username dan password wajib diisi.")
            else:
                try:
                    run_sql(
                        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        (username.strip(), password, role),
                    )
                    st.sidebar.success("User berhasil ditambahkan.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.sidebar.error("Username sudah digunakan.")

    else:
        df_users = get_df("SELECT * FROM users ORDER BY username")
        if df_users.empty:
            st.sidebar.info("Belum ada user.")
            return
        selected = st.sidebar.selectbox("Pilih User", df_users["username"].tolist())
        user_data = df_users[df_users["username"] == selected].iloc[0]
        new_password = st.sidebar.text_input("Password Baru (opsional)", type="password")
        new_role = st.sidebar.selectbox(
            "Role",
            ROLE_OPTIONS,
            index=ROLE_OPTIONS.index(str(user_data["role"]).lower()),
        )
        col1, col2 = st.sidebar.columns(2)
        if col1.button("Update"):
            if new_password:
                run_sql(
                    "UPDATE users SET password = ?, role = ? WHERE username = ?",
                    (new_password, new_role, selected),
                )
            else:
                run_sql(
                    "UPDATE users SET role = ? WHERE username = ?",
                    (new_role, selected),
                )
            st.sidebar.success("User berhasil diupdate.")
            st.rerun()
        if col2.button("Hapus"):
            if selected == st.session_state.user:
                st.sidebar.error("Tidak bisa menghapus akun sendiri.")
            else:
                run_sql("DELETE FROM users WHERE username = ?", (selected,))
                st.sidebar.success("User berhasil dihapus.")
                st.rerun()


# =========================
# DIALOGS
# =========================
@st.dialog("Tambah Bahan Paparan")
def tambah_bahan_dialog() -> None:
    daftar_pic = get_pic_users()

    nama = st.text_input("Nama Bahan")
    tgl_disposisi = st.date_input("Tanggal Disposisi")

    if daftar_pic:
        pic1 = st.selectbox("PIC 1", daftar_pic)
        pic2 = st.selectbox("PIC 2", daftar_pic, index=1 if len(daftar_pic) > 1 else 0)
        kantor = st.selectbox("Kantor", KANTOR_OPTIONS)
        jenis = st.selectbox("Jenis Bahan", JENIS_OPTIONS)
        instruksi = st.text_area("Keywords / Instruksi", height=120)
        deadline = st.date_input("Deadline")
    else:
        pic1 = pic2 = kantor = jenis = deadline = None
        instruksi = ""
        st.warning("Belum ada user PIC.")

    file_surat = st.file_uploader("Upload Surat / Disposisi", type=["pdf", "docx"])

    col1, col2 = st.columns(2)
    with col1:
        submitted = st.button("Simpan", use_container_width=True)
    with col2:
        cancelled = st.button("Batal", use_container_width=True)

    if cancelled:
        st.rerun()

    if not submitted:
        return

    if not nama.strip():
        st.error("Nama bahan wajib diisi.")
        return
    if not daftar_pic:
        st.error("Belum ada user PIC.")
        return
    if pic1 == pic2:
        st.error("PIC 1 dan PIC 2 tidak boleh sama.")
        return

    existing = get_df(
        "SELECT id FROM bahan WHERE nama_bahan = ? AND deadline = ?",
        (nama.strip(), str(deadline)),
    )
    if not existing.empty:
        st.error("Agenda dengan nama bahan dan deadline tersebut sudah ada.")
        return

    file_path = ""
    if file_surat:
        tahun = pd.Timestamp(tgl_disposisi).year
        file_path = save_uploaded_file(file_surat, STORAGE_DIR / "disposisi" / str(tahun))

    run_sql(
        """
        INSERT INTO bahan (
            tgl_disposisi, nama_bahan, pic1, pic2, kantor, jenis_bahan,
            instruksi, deadline, status, progress, file_surat
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(tgl_disposisi),
            nama.strip(),
            pic1,
            pic2,
            kantor,
            jenis,
            instruksi,
            str(deadline),
            "Not Yet Started",
            0,
            file_path,
        ),
    )
    st.success("Bahan paparan berhasil ditambahkan.")
    st.rerun()


@st.dialog("Edit Bahan Paparan")
def edit_dialog(edit_id: int) -> None:
    df_edit = get_df("SELECT * FROM bahan WHERE id = ?", (edit_id,))
    if df_edit.empty:
        st.error("Data tidak ditemukan.")
        return

    row = df_edit.iloc[0]
    status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(row["status"]))
    progress = st.slider("Progress (%)", 0, 100, int(row["progress"] or 0))
    if status == "Done":
        progress = 100
    keterangan = st.text_area("Keterangan", row["keterangan"] or "")
    file_paparan = st.file_uploader("Upload Paparan", type=["pdf"])
    file_narasi = st.file_uploader("Upload Narasi")
    instruksi = st.text_area("Keywords / Instruksi", row["instruksi"] or "", height=120)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Simpan", use_container_width=True):
            pap_path = row["file_paparan"] or ""
            nar_path = row["file_narasi"] or ""
            if file_paparan:
                pap_path = save_uploaded_file(file_paparan, STORAGE_DIR / "output" / "paparan")
            if file_narasi:
                nar_path = save_uploaded_file(file_narasi, STORAGE_DIR / "output" / "narasi")

            run_sql(
                """
                UPDATE bahan
                SET status = ?, progress = ?, keterangan = ?, instruksi = ?,
                    file_paparan = ?, file_narasi = ?
                WHERE id = ?
                """,
                (status, progress, keterangan, instruksi, pap_path, nar_path, edit_id),
            )
            log_action(edit_id, st.session_state.user, "update bahan")
            st.success("Data berhasil diupdate.")
            st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True):
            st.rerun()


@st.dialog("Konfirmasi Hapus")
def delete_dialog(bahan_id: int, nama_bahan: str) -> None:
    st.warning(f"Yakin ingin menghapus **{nama_bahan}**?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Ya, Hapus", use_container_width=True):
            run_sql("DELETE FROM bahan WHERE id = ?", (bahan_id,))
            log_action(bahan_id, st.session_state.user, "delete bahan")
            st.success("Data berhasil dihapus.")
            st.rerun()
    with col2:
        if st.button("Batal", use_container_width=True):
            st.rerun()


# =========================
# DATA PIPELINE
# =========================
def load_data() -> pd.DataFrame:
    df = get_df("SELECT * FROM bahan ORDER BY tgl_disposisi DESC, id DESC")
    if df.empty:
        return df

    df["role_user"] = st.session_state.role
    df["tgl_disposisi"] = pd.to_datetime(df["tgl_disposisi"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["tgl_disposisi"]).copy()
    df["tahun"] = df["tgl_disposisi"].dt.year

    if st.session_state.role == "pic":
        user = st.session_state.user
        df = df[(df["pic1"] == user) | (df["pic2"] == user)].copy()

    return df


# =========================
# DASHBOARD
# =========================
def render_header() -> None:
    logo_html = (
        f'<img class="dashboard-header-logo" src="data:image/png;base64,{file_to_base64(LOGO_PATH)}">'
        if LOGO_PATH.exists()
        else ""
    )
    user_name = st.session_state.get("user", "-")
    user_role = str(st.session_state.get("role", "-")).upper()
    st.markdown(
        f"""
        <div class="dashboard-header">
            <div class="dashboard-header-inner">
                <div class="dashboard-header-left">
                    {logo_html}
                    <div>
                        <p class="dashboard-header-title">Dashboard Monitoring Penyusunan Bahan Paparan Pimpinan</p>
                        <p class="dashboard-header-subtitle">PDSIA Pusat &amp; Tulodong</p>
                    </div>
                </div>
                <div class="dashboard-header-user">
                    <p class="dashboard-header-user-name">{user_name}</p>
                    <p class="dashboard-header-user-role">{user_role}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi(df: pd.DataFrame) -> None:
    total = len(df)
    done = int((df["status"] == "Done").sum())
    on_progress = int((df["status"] == "On Progress").sum())
    not_started = int((df["status"] == "Not Yet Started").sum())
    total_pic = pd.concat([df["pic1"], df["pic2"]]).dropna().nunique()

    cards = [
        ("TOTAL PAPARAN", total, "#0c4a6e"),
        ("DALAM PROSES", on_progress, "#f59e0b"),
        ("SELESAI", done, "#22c55e"),
        ("PIC AKTIF", total_pic, "#06b6d4"),
        ("BELUM MULAI", not_started, "#94a3b8"),
    ]
    cols = st.columns(len(cards))
    for col, (title, value, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card" style="border-left:6px solid {color};">
                    <div class="kpi-title">{title}</div>
                    <div class="kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_charts(df: pd.DataFrame, tahun_pilih: int) -> None:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f'<div class="section-title">Komposisi Jenis Bahan ({tahun_pilih})</div>', unsafe_allow_html=True)
        jenis = df["jenis_bahan"].fillna("Unknown").value_counts().reset_index()
        jenis.columns = ["jenis_bahan", "jumlah"]
        fig = px.pie(jenis, names="jenis_bahan", values="jumlah", hole=0.55)
        fig.update_traces(textinfo="percent+label")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown(f'<div class="section-title">Distribusi Bahan per PIC ({tahun_pilih})</div>', unsafe_allow_html=True)
        df_pic = pd.concat(
            [
                df[["pic1", "status"]].rename(columns={"pic1": "PIC"}),
                df[["pic2", "status"]].rename(columns={"pic2": "PIC"}),
            ],
            ignore_index=True,
        ).dropna(subset=["PIC"])
        if df_pic.empty:
            st.info("Belum ada data PIC.")
        else:
            beban = df_pic.groupby("PIC").agg(
                Total=("status", "count"),
                Done=("status", lambda s: (s == "Done").sum()),
                In_Progress=("status", lambda s: (s == "On Progress").sum()),
            ).reset_index()
            beban["Not_Yet"] = beban["Total"] - beban["Done"] - beban["In_Progress"]
            beban_long = beban.melt(
                id_vars=["PIC", "Total"],
                value_vars=["Not_Yet", "In_Progress", "Done"],
                var_name="Status",
                value_name="Jumlah",
            )
            beban_long["Status"] = beban_long["Status"].map(
                {
                    "Not_Yet": "Not Yet Started",
                    "In_Progress": "On Progress",
                    "Done": "Done",
                }
            )
            fig = px.bar(
                beban_long,
                y="PIC",
                x="Jumlah",
                color="Status",
                orientation="h",
                barmode="stack",
                hover_data={"Total": True, "Jumlah": True, "PIC": False},
            )
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="")
            st.plotly_chart(fig, use_container_width=True)

    with col3:
        st.markdown(f'<div class="section-title">Distribusi Bahan per Tim Kerja ({tahun_pilih})</div>', unsafe_allow_html=True)
        kantor = df["kantor"].fillna("-").value_counts().reindex(KANTOR_OPTIONS, fill_value=0).reset_index()
        kantor.columns = ["Kantor", "Jumlah"]
        fig = px.bar(kantor, x="Kantor", y="Jumlah", text="Jumlah", color="Kantor")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, yaxis=dict(dtick=1), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    col4, col5 = st.columns(2)
    with col4:
        st.markdown(f'<div class="section-title">Tren Bulanan ({tahun_pilih})</div>', unsafe_allow_html=True)
        trend = df.copy()
        trend["bulan_angka"] = trend["tgl_disposisi"].dt.month
        trend["bulan_label"] = trend["tgl_disposisi"].dt.strftime("%b %Y")
        bulanan = trend.groupby(["bulan_angka", "bulan_label"]).size().reset_index(name="total").sort_values("bulan_angka")
        fig = px.line(bulanan, x="bulan_label", y="total", markers=True)
        fig.update_layout(showlegend=False, yaxis=dict(dtick=1), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col5:
        st.markdown(f'<div class="section-title">Tren Triwulanan ({tahun_pilih})</div>', unsafe_allow_html=True)
        trend = df.copy()
        trend["triwulan_angka"] = trend["tgl_disposisi"].dt.quarter
        trend["triwulan"] = trend["triwulan_angka"].map({1: "I", 2: "II", 3: "III", 4: "IV"})
        triwulan = trend.groupby(["triwulan_angka", "triwulan"]).size().reset_index(name="total").sort_values("triwulan_angka")
        fig = px.bar(triwulan, x="triwulan", y="total", text="total")
        fig.update_layout(showlegend=False, yaxis=dict(dtick=1), margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


def render_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="table-card">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div class="section-title" style="margin:0;">Daftar Bahan Paparan</div>
            <div class="badge">{len(df)} Data</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columns = [
        "No",
        "Judul",
        "Tim Kerja",
        "PIC",
        "Status",
        "Progress",
        "Output",
        "Aksi",
    ]
    header_cols = st.columns([0.5, 3, 1.3, 1.5, 1.2, 1.1, 1.35, 1.1])
    for c, title in zip(header_cols, columns):
        c.markdown(f"**{title}**")
    st.divider()

    for no, (_, row) in enumerate(df.iterrows(), start=1):
        pill_class = {
            "Done": "done",
            "On Progress": "progress",
        }.get(row["status"], "notyet")
        progress = max(0, min(100, int(row["progress"] or 0)))

        st.markdown("<div class='compact-row'>", unsafe_allow_html=True)
        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 3, 1.3, 1.5, 1.2, 1.1, 1.35, 1.1])
        c0.write(no)
        with c1:
            st.markdown(f"**{row['nama_bahan']}**")
            st.markdown(f"<span class='badge'>{row['jenis_bahan'] or '-'}</span>", unsafe_allow_html=True)
            if pd.notna(row["deadline"]):
                st.caption(f"Deadline: {row['deadline'].date()}")
        with c2:
            st.write(row["kantor"] or "-")
            surat = safe_path(row["file_surat"])
            if surat and surat.exists():
                st.markdown("<div class='output-btn'>", unsafe_allow_html=True)
                if st.button("📩 Disposisi", key=f"surat_{row['id']}", use_container_width=True):
                    st.query_params["preview_id"] = str(int(row["id"]))
                    st.query_params["kind"] = "surat"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        with c3:
            st.write(f"PIC 1: {row['pic1'] or '-'}")
            st.write(f"PIC 2: {row['pic2'] or '-'}")
        with c4:
            st.markdown(f"<span class='pill {pill_class}'>{row['status']}</span>", unsafe_allow_html=True)
            if row["keterangan"]:
                st.caption(row["keterangan"])
        with c5:
            st.progress(progress / 100)
            st.caption(f"{progress}%")
        with c6:
            paparan = safe_path(row["file_paparan"])
            narasi = safe_path(row["file_narasi"])
            if paparan and paparan.exists():
                st.markdown("<div class='output-btn'>", unsafe_allow_html=True)
                if st.button("👁️ Paparan", key=f"paparan_{row['id']}", use_container_width=True):
                    st.query_params["preview_id"] = str(int(row["id"]))
                    st.query_params["kind"] = "paparan"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.caption("Paparan: -")
            if narasi and narasi.exists():
                st.markdown("<div class='output-btn'>", unsafe_allow_html=True)
                if st.button("📝 Narasi", key=f"narasi_{row['id']}", use_container_width=True):
                    st.query_params["preview_id"] = str(int(row["id"]))
                    st.query_params["kind"] = "narasi"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.caption("Narasi: -")
        with c7:
            can_edit = st.session_state.role in {"admin", "atasan"} or st.session_state.user in {row['pic1'], row['pic2']}
            can_delete = st.session_state.role in {"admin", "atasan"}
            e1, e2 = st.columns(2)
            with e1:
                st.markdown("<div class='table-action'>", unsafe_allow_html=True)
                if st.button("✏️", key=f"edit_{row['id']}", disabled=not can_edit, use_container_width=True):
                    edit_dialog(int(row["id"]))
                st.markdown("</div>", unsafe_allow_html=True)
            with e2:
                st.markdown("<div class='table-action'>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"del_{row['id']}", disabled=not can_delete, use_container_width=True):
                    delete_dialog(int(row["id"]), str(row["nama_bahan"]))
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()

    st.markdown("</div>", unsafe_allow_html=True)

def render_dashboard() -> None:
    inject_global_css()
    render_header()

    with st.sidebar:
        st.markdown(f"### {st.session_state.user}")
        st.caption(f"Role: {st.session_state.role.upper()}")
        if st.button("Logout", use_container_width=True):
            logout()

    render_tambah_bahan()
    render_user_admin()

    df = load_data()
    if df.empty:
        st.warning("Belum ada data bahan.")
        return

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filter Data")
        tahun_list = sorted(df["tahun"].dropna().unique().tolist())
        tahun_pilih = st.selectbox("Tahun", tahun_list)
        keyword = st.text_input("Search Keyword", placeholder="Nama bahan / instruksi")
        pic_list = sorted(pd.concat([df["pic1"], df["pic2"]]).dropna().unique().tolist())
        pic_filter = st.selectbox("PIC", ["Semua"] + pic_list)
        kantor_list = sorted(df["kantor"].dropna().unique().tolist())
        kantor_filter = st.selectbox("Kantor", ["Semua"] + kantor_list)

    filtered = df[df["tahun"] == tahun_pilih].copy()
    if keyword.strip():
        k = keyword.lower().strip()
        filtered = filtered[
            filtered["nama_bahan"].fillna("").str.lower().str.contains(k)
            | filtered["instruksi"].fillna("").str.lower().str.contains(k)
        ]
    if pic_filter != "Semua":
        filtered = filtered[(filtered["pic1"] == pic_filter) | (filtered["pic2"] == pic_filter)]
    if kantor_filter != "Semua":
        filtered = filtered[filtered["kantor"] == kantor_filter]

    if filtered.empty:
        st.info("Tidak ada data yang cocok dengan filter.")
        return

    render_kpi(filtered)
    render_charts(filtered, tahun_pilih)
    render_table(filtered.sort_values(["deadline", "id"], ascending=[True, False]))


def main() -> None:
    init_db()
    if "user" not in st.session_state:
        render_login()
        return
    render_preview()
    render_dashboard()


if __name__ == "__main__":
    main()
