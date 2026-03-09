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
DEFAULT_USERS = [
    ("admin", "admin123", "admin"),
]


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
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()



def open_preview(row_id: int, kind: str) -> None:
    st.query_params["preview_id"] = str(row_id)
    st.query_params["kind"] = kind
    st.rerun()


# =========================
# UI STYLES
# =========================
def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #eef4ff;
            --card: rgba(255,255,255,0.88);
            --border: rgba(148,163,184,0.24);
            --text: #0f172a;
            --muted: #64748b;
            --primary: #1d4ed8;
            --primary-soft: #dbeafe;
            --success: #16a34a;
            --warning: #f59e0b;
            --shadow: 0 14px 36px rgba(15,23,42,0.08);
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(29,78,216,0.12), transparent 30%),
                radial-gradient(circle at top right, rgba(34,197,94,0.10), transparent 25%),
                linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
        }

        .stApp {
            color: var(--text);
        }

        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
            max-width: 1380px;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f8fbff 0%, #eff6ff 100%);
            border-right: 1px solid rgba(148,163,184,0.15);
        }

        .hero-card {
            position: relative;
            overflow: hidden;
            border-radius: 28px;
            padding: 28px 30px;
            margin-bottom: 22px;
            background:
                linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(239,246,255,0.92) 100%);
            border: 1px solid rgba(191,219,254,0.85);
            box-shadow: 0 18px 40px rgba(29,78,216,0.12);
        }

        .hero-card::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 86% 22%, rgba(59,130,246,0.18), transparent 18%),
                radial-gradient(circle at 80% 70%, rgba(34,197,94,0.14), transparent 18%);
            pointer-events: none;
        }

        .hero-grid {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 22px;
            position: relative;
            z-index: 2;
        }

        .hero-brand {
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 8px;
        }

        .hero-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 800;
            color: var(--primary);
            background: var(--primary-soft);
            border: 1px solid rgba(59,130,246,0.16);
            padding: 8px 12px;
            border-radius: 999px;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .hero-title {
            font-size: 36px;
            line-height: 1.12;
            font-weight: 900;
            color: var(--text);
            margin: 0 0 8px 0;
        }

        .hero-sub {
            margin: 0;
            color: #475569;
            font-size: 15px;
            line-height: 1.6;
            max-width: 780px;
        }

        .hero-stat-wrap {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            justify-content: flex-end;
            min-width: 280px;
        }

        .hero-stat {
            min-width: 118px;
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(148,163,184,0.18);
            box-shadow: 0 8px 24px rgba(15,23,42,0.06);
            border-radius: 20px;
            padding: 14px 16px;
        }

        .hero-stat-label {
            font-size: 11px;
            font-weight: 800;
            color: #64748b;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .hero-stat-value {
            font-size: 28px;
            font-weight: 900;
            color: #0f172a;
            line-height: 1;
        }

        .kpi-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.94) 100%);
            border: 1px solid var(--border);
            padding: 16px 18px;
            border-radius: 22px;
            box-shadow: var(--shadow);
            margin-bottom: 10px;
        }

        .kpi-title {
            color: #64748b;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .kpi-value {
            color: #0f172a;
            font-size: 30px;
            font-weight: 900;
            line-height: 1.05;
        }

        .section-title {
            color: #0f172a;
            font-size: 21px;
            font-weight: 900;
            margin: 0 0 12px;
        }

        .table-card {
            background: var(--card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 18px 18px 10px;
            box-shadow: var(--shadow);
            margin-top: 20px;
        }

        .table-toolbar {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            margin-bottom:8px;
        }

        .badge {
            display:inline-flex;
            align-items:center;
            gap:6px;
            padding:6px 10px;
            border-radius:999px;
            font-size:12px;
            background:#e0f2fe;
            color:#075985;
            font-weight:800;
        }

        .table-header {
            margin: 4px 0 10px 0;
            padding: 0 4px;
            color: #475569;
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .06em;
        }

        .row-card {
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(226,232,240,0.9);
            border-radius: 18px;
            padding: 8px 10px;
            margin-bottom: 10px;
            box-shadow: 0 6px 20px rgba(15,23,42,0.04);
        }

        .judul-utama {
            font-size: 15px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 2px;
            line-height: 1.35;
        }

        .muted-txt {
            color: var(--muted);
            font-size: 12px;
            line-height: 1.35;
        }

        .tiny-chip {
            display:inline-block;
            margin-top: 4px;
            padding:4px 8px;
            border-radius:999px;
            background:#eff6ff;
            color:#1d4ed8;
            font-size:11px;
            font-weight:800;
        }

        .pill {
            display:inline-block;
            padding:5px 10px;
            border-radius:999px;
            font-weight:800;
            font-size:11px;
        }

        .pill.notyet { background:#e2e8f0; color:#334155; }
        .pill.progress { background:#fef3c7; color:#92400e; }
        .pill.done { background:#dcfce7; color:#166534; }

        .output-stack {
            display:flex;
            flex-direction:column;
            gap:6px;
        }

        div[data-testid="stButton"] > button {
            border-radius: 12px;
            font-weight: 700;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button {
            background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%);
            color: white;
            border: none;
            box-shadow: 0 10px 22px rgba(37,99,235,0.22);
        }

        .compact-btn div[data-testid="stButton"] > button {
            min-height: 34px;
            padding: 0.25rem 0.6rem;
            font-size: 12px;
        }

        div[data-testid="stProgressBar"] > div > div {
            border-radius: 999px;
        }

        @media (max-width: 980px) {
            .hero-grid {
                flex-direction: column;
                align-items: flex-start;
            }
            .hero-stat-wrap {
                justify-content: flex-start;
            }
            .hero-title {
                font-size: 28px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================
# LOGIN / PREVIEW
# =========================
def render_login() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display:none; }
        header, footer { visibility:hidden; }
        .block-container { padding-top: 1.2rem !important; max-width: 680px !important; }
        .login-shell {
            min-height: 78vh;
            display:flex;
            align-items:center;
            justify-content:center;
        }
        .login-card {
            width:100%;
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,252,0.95) 100%);
            border: 1px solid rgba(191,219,254,0.9);
            box-shadow: 0 20px 48px rgba(29,78,216,0.12);
            border-radius: 28px;
            padding: 28px 30px 22px;
            text-align:center;
        }
        .login-title {
            font-size: 34px;
            line-height: 1.2;
            font-weight: 900;
            color: #0f172a;
            margin: 10px 0 8px;
        }
        .login-subtitle {
            color: #64748b;
            font-size: 15px;
            margin-bottom: 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='login-shell'><div class='login-card'>", unsafe_allow_html=True)
    if LOGO_PATH.exists():
        logo_col = st.columns([1, 1, 1])[1]
        with logo_col:
            st.image(str(LOGO_PATH), width=130)
    st.markdown("<div class='login-title'>Dashboard Monitoring Bahan Paparan</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-subtitle'>Silakan masuk ke akun Anda</div>", unsafe_allow_html=True)

    form_col = st.columns([0.12, 0.76, 0.12])[1]
    with form_col:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Masuk", use_container_width=True):
            role = authenticate(username, password)
            if role:
                st.session_state.user = username.strip()
                st.session_state.role = role.lower()
                st.rerun()
            st.error("Username atau password salah.")
    st.markdown("</div></div>", unsafe_allow_html=True)



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
    column_map = {
        "surat": ("file_surat", "Preview Surat / Disposisi"),
        "paparan": ("file_paparan", "Preview Paparan"),
        "narasi": ("file_narasi", "Preview Narasi"),
    }
    if kind not in column_map:
        st.error("Parameter kind tidak valid.")
        st.stop()

    df_prev = get_df(
        "SELECT id, nama_bahan, file_surat, file_paparan, file_narasi FROM bahan WHERE id = ?",
        (row_id,),
    )
    if df_prev.empty:
        st.error("Data tidak ditemukan.")
        st.stop()

    row = df_prev.iloc[0]
    col_name, title = column_map[kind]
    file_path = safe_path(row[col_name])

    top1, top2 = st.columns([1, 6])
    with top1:
        if st.button("⬅ Kembali", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with top2:
        st.markdown(f"### {title}")
        st.caption(f"Bahan: {row['nama_bahan']}")

    if not file_path or not file_path.exists():
        st.info("File belum tersedia.")
        st.stop()

    ext = file_path.suffix.lower()
    size_limit = 200 * 1024 * 1024

    if ext == ".pdf" and file_path.stat().st_size <= size_limit:
        with file_path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900" style="border:none;border-radius:18px;background:white;"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        with file_path.open("rb") as f:
            st.download_button("Download file", f, file_name=file_path.name)
        if ext != ".pdf":
            st.info("Preview inline saat ini hanya untuk PDF.")
    st.stop()


# =========================
# SIDEBAR FORMS
# =========================
def render_tambah_bahan() -> None:
    if st.session_state.role not in {"admin", "atasan", "pic"}:
        return

    st.sidebar.markdown("---")
    st.sidebar.subheader("Input Bahan")
    st.sidebar.caption("Klik tombol untuk membuka form input bahan paparan.")
    if st.sidebar.button("➕ Tambah Bahan", use_container_width=True):
        add_bahan_dialog()



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
def add_bahan_dialog() -> None:
    daftar_pic = get_pic_users()
    if not daftar_pic:
        st.warning("Belum ada user PIC. Tambahkan user PIC terlebih dahulu.")
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

        instruksi = st.text_area("Keywords / Instruksi", height=110)
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
    st.success("Bahan berhasil ditambahkan.")
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
def render_header(df: pd.DataFrame | None = None) -> None:
    total_data = len(df) if df is not None else 0
    done = int((df["status"] == "Done").sum()) if df is not None and not df.empty else 0
    in_progress = int((df["status"] == "On Progress").sum()) if df is not None and not df.empty else 0
    logo_html = (
        f'<img src="data:image/png;base64,{file_to_base64(LOGO_PATH)}" width="82">'
        if LOGO_PATH.exists()
        else ""
    )
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-grid">
                <div>
                    <div class="hero-brand">
                        {logo_html}
                        <div>
                            <div class="hero-chip">Dashboard Monitoring • Bagian PDSIA</div>
                            <h1 class="hero-title">Dashboard Monitoring Bahan Paparan Pimpinan</h1>
                            <p class="hero-sub">Pantau progres bahan paparan, PIC, disposisi, dan output narasi dalam satu tampilan yang lebih jelas, modern, dan mudah dibaca.</p>
                        </div>
                    </div>
                </div>
                <div class="hero-stat-wrap">
                    <div class="hero-stat">
                        <div class="hero-stat-label">Total</div>
                        <div class="hero-stat-value">{total_data}</div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Progress</div>
                        <div class="hero-stat-value">{in_progress}</div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Done</div>
                        <div class="hero-stat-value">{done}</div>
                    </div>
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
        ("TOTAL PAPARAN", total, "#1d4ed8"),
        ("DALAM PROSES", on_progress, "#f59e0b"),
        ("SELESAI", done, "#16a34a"),
        ("PIC AKTIF", total_pic, "#06b6d4"),
        ("BELUM MULAI", not_started, "#94a3b8"),
    ]
    cols = st.columns(len(cards))
    for col, (title, value, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card" style="border-top:5px solid {color};">
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
        <div class="table-toolbar">
            <div class="section-title" style="margin:0;">Daftar Bahan Paparan</div>
            <div class="badge">{len(df)} Data</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    header_cols = st.columns([0.45, 3.2, 1.2, 1.55, 1.3, 1.0, 1.2, 1.0])
    header_titles = ["No", "Judul", "Tim", "PIC", "Status", "Prog", "Output", "Aksi"]
    for c, title in zip(header_cols, header_titles):
        c.markdown(f"<div class='table-header'>{title}</div>", unsafe_allow_html=True)

    for no, (_, row) in enumerate(df.iterrows(), start=1):
        pill_class = {
            "Done": "done",
            "On Progress": "progress",
        }.get(row["status"], "notyet")
        progress = max(0, min(100, int(row["progress"] or 0)))

        st.markdown('<div class="row-card">', unsafe_allow_html=True)
        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.45, 3.2, 1.2, 1.55, 1.3, 1.0, 1.2, 1.0])

        with c0:
            st.markdown(f"<div class='judul-utama' style='font-size:14px'>{no}</div>", unsafe_allow_html=True)

        with c1:
            st.markdown(f"<div class='judul-utama'>{row['nama_bahan']}</div>", unsafe_allow_html=True)
            meta = []
            if pd.notna(row["deadline"]):
                meta.append(f"Deadline: {row['deadline'].date()}")
            if row["instruksi"]:
                meta.append(f"Instruksi: {str(row['instruksi'])[:60]}")
            if meta:
                st.markdown(f"<div class='muted-txt'>{' • '.join(meta)}</div>", unsafe_allow_html=True)
            st.markdown(f"<span class='tiny-chip'>{row['jenis_bahan'] or '-'}</span>", unsafe_allow_html=True)

        with c2:
            st.markdown(f"<div class='muted-txt'><b>{row['kantor'] or '-'}</b></div>", unsafe_allow_html=True)
            surat = safe_path(row["file_surat"])
            if surat and surat.exists():
                if st.button("📩 Surat", key=f"surat_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "surat")

        with c3:
            st.markdown(f"<div class='muted-txt'>PIC 1: <b>{row['pic1'] or '-'}</b></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='muted-txt'>PIC 2: <b>{row['pic2'] or '-'}</b></div>", unsafe_allow_html=True)

        with c4:
            st.markdown(f"<span class='pill {pill_class}'>{row['status']}</span>", unsafe_allow_html=True)
            if row["keterangan"]:
                st.markdown(f"<div class='muted-txt' style='margin-top:6px'>{row['keterangan']}</div>", unsafe_allow_html=True)

        with c5:
            st.progress(progress / 100)
            st.markdown(f"<div class='muted-txt'>{progress}%</div>", unsafe_allow_html=True)

        with c6:
            st.markdown("<div class='output-stack compact-btn'>", unsafe_allow_html=True)
            paparan = safe_path(row["file_paparan"])
            narasi = safe_path(row["file_narasi"])
            if paparan and paparan.exists():
                if st.button("👁 Paparan", key=f"paparan_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "paparan")
            else:
                st.markdown("<div class='muted-txt'>Paparan: -</div>", unsafe_allow_html=True)
            if narasi and narasi.exists():
                if st.button("📝 Narasi", key=f"narasi_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "narasi")
            else:
                st.markdown("<div class='muted-txt'>Narasi: -</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with c7:
            can_edit = st.session_state.role in {"admin", "atasan"} or st.session_state.user in {row['pic1'], row['pic2']}
            can_delete = st.session_state.role in {"admin", "atasan"}
            e1, e2 = st.columns(2)
            with e1:
                if st.button("✏️", key=f"edit_{row['id']}", disabled=not can_edit, use_container_width=True):
                    edit_dialog(int(row["id"]))
            with e2:
                if st.button("🗑️", key=f"del_{row['id']}", disabled=not can_delete, use_container_width=True):
                    delete_dialog(int(row["id"]), str(row["nama_bahan"]))

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)



def render_dashboard() -> None:
    inject_global_css()

    with st.sidebar:
        st.success(f"Login sebagai: {st.session_state.user} ({st.session_state.role})")
        if st.button("Logout", use_container_width=True):
            logout()

    render_tambah_bahan()
    render_user_admin()

    df = load_data()
    render_header(df)
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
    seed_default_users()
    if "user" not in st.session_state:
        render_login()
        return
    inject_global_css()
    render_preview()
    render_dashboard()


if __name__ == "__main__":
    main()
