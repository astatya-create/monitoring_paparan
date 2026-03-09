from __future__ import annotations

import ast
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
SEED_USERS_FILE = BASE_DIR / "seed_users.py"

STATUS_OPTIONS = ["Not Yet Started", "On Progress", "Done"]
ROLE_OPTIONS = ["admin", "atasan", "pic"]
KANTOR_OPTIONS = ["Tulodong", "Pusat"]
JENIS_OPTIONS = ["Kabinet", "Legislatif", "Instansi", "Lain-lain"]
DEFAULT_SEED_USERS = [("admin", "admin123", "admin")]


def safe_path(relative_or_abs: str | None) -> Path | None:
    if not relative_or_abs:
        return None
    p = Path(relative_or_abs)
    return p if p.is_absolute() else BASE_DIR / p


def file_to_base64(file_path: Path) -> str:
    with file_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


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
        conn.executemany(
            "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
            load_seed_users(),
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
    st.rerun()


def open_preview(row_id: int, kind: str) -> None:
    st.session_state["preview_id"] = int(row_id)
    st.session_state["preview_kind"] = kind
    st.rerun()


def close_preview() -> None:
    st.session_state.pop("preview_id", None)
    st.session_state.pop("preview_kind", None)
    st.rerun()


def inject_dashboard_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { background: #f4f7fb; }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #17355c 0%, #0f2747 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        [data-testid="stSidebar"] * { color: white !important; }
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stTextInput label,
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stDateInput label,
        [data-testid="stSidebar"] .stTextArea label,
        [data-testid="stSidebar"] .stFileUploader label {
            color: white !important;
            font-weight: 600;
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stDownloadButton > button {
            background: white !important;
            color: #17355c !important;
            border: none !important;
            font-weight: 700 !important;
            border-radius: 12px !important;
        }
        .header-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 4px 18px rgba(15, 39, 71, 0.06);
        }
        .header-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            flex-wrap: wrap;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .header-title {
            color: #17355c;
            font-size: 38px;
            font-weight: 800;
            line-height: 1.08;
            margin: 0;
        }
        .header-subtitle {
            color: #64748b;
            font-size: 15px;
            margin-top: 6px;
            font-weight: 600;
        }
        .header-user {
            text-align: right;
            color: #17355c;
            font-weight: 700;
            font-size: 16px;
        }
        .kpi-card {
            background: white;
            border-radius: 18px;
            padding: 16px 18px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 4px 18px rgba(15, 39, 71, 0.05);
            margin-bottom: 8px;
        }
        .kpi-label { color: #64748b; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
        .kpi-value { color: #0f172a; font-size: 30px; font-weight: 800; margin-top: 8px; }
        .section-title {
            color: #17355c;
            font-size: 22px;
            font-weight: 800;
            margin: 12px 0 8px;
        }
        .table-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 16px 18px;
            box-shadow: 0 4px 18px rgba(15, 39, 71, 0.05);
            margin-top: 16px;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 999px;
            background: #e8f0fb;
            color: #17355c;
            font-size: 12px;
            font-weight: 700;
        }
        .status-pill {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 800;
        }
        .status-notyet { background: #e2e8f0; color: #334155; }
        .status-progress { background: #fef3c7; color: #92400e; }
        .status-done { background: #dcfce7; color: #166534; }
        .compact-title { margin-bottom: 0; }
        div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
            border-radius: 10px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        header, footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([2, 2, 2])
    with center:
        st.markdown("<div style='text-align:center;margin-top:2rem'>", unsafe_allow_html=True)
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=110)
        st.markdown("## Dashboard Monitoring Bahan Paparan")
        st.caption("Silakan masuk ke akun Anda")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Masuk", use_container_width=True):
            role = authenticate(username, password)
            if role:
                st.session_state.user = username.strip()
                st.session_state.role = role.lower()
                st.rerun()
            st.error("Username atau password salah.")
        st.markdown("</div>", unsafe_allow_html=True)


@st.dialog("Tambah Bahan")
def tambah_bahan_dialog() -> None:
    daftar_pic = get_pic_users()
    if not daftar_pic:
        st.warning("Belum ada user PIC. Tambahkan user PIC dulu di Kelola User.")
        return

    with st.form("form_tambah_bahan", clear_on_submit=True):
        nama = st.text_input("Nama Bahan")
        col1, col2 = st.columns(2)
        with col1:
            tgl_disposisi = st.date_input("Tanggal Disposisi")
            pic1 = st.selectbox("PIC 1", daftar_pic)
            kantor = st.selectbox("Kantor", KANTOR_OPTIONS)
        with col2:
            deadline = st.date_input("Deadline")
            pic2 = st.selectbox("PIC 2", daftar_pic)
            jenis = st.selectbox("Jenis Bahan", JENIS_OPTIONS)

        instruksi = st.text_area("Keywords / Instruksi", height=120)
        file_surat = st.file_uploader("Upload Surat / Disposisi", type=["pdf", "docx"])
        submit = st.form_submit_button("Simpan", use_container_width=True)

    if not submit:
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
    instruksi = st.text_area("Keywords / Instruksi", row["instruksi"] or "", height=120)
    file_paparan = st.file_uploader("Upload Paparan", type=["pdf"])
    file_narasi = st.file_uploader("Upload Narasi")

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


def render_preview() -> bool:
    preview_id = st.session_state.get("preview_id")
    kind = st.session_state.get("preview_kind")
    if not preview_id or not kind:
        return False

    column_map = {
        "surat": ("file_surat", "Preview Surat"),
        "paparan": ("file_paparan", "Preview Paparan"),
        "narasi": ("file_narasi", "Preview Narasi"),
    }
    if kind not in column_map:
        close_preview()
        return False

    df_prev = get_df(
        "SELECT id, nama_bahan, file_surat, file_paparan, file_narasi FROM bahan WHERE id = ?",
        (int(preview_id),),
    )
    if df_prev.empty:
        st.error("Data tidak ditemukan.")
        return True

    row = df_prev.iloc[0]
    col_name, title = column_map[kind]
    file_path = safe_path(row[col_name])

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("⬅ Kembali", use_container_width=True):
            close_preview()
    with c2:
        st.markdown(f"### {title} — {row['nama_bahan']}")

    if not file_path or not file_path.exists():
        st.info("File belum tersedia.")
        return True

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        with file_path.open("rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900" style="border:none;border-radius:12px;"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        with file_path.open("rb") as f:
            st.download_button("Download file", f, file_name=file_path.name, use_container_width=False)
        st.info("Preview inline saat ini hanya untuk PDF.")
    return True


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
        if st.sidebar.button("Simpan User", use_container_width=True):
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
        if col1.button("Update", use_container_width=True):
            if new_password:
                run_sql(
                    "UPDATE users SET password = ?, role = ? WHERE username = ?",
                    (new_password, new_role, selected),
                )
            else:
                run_sql("UPDATE users SET role = ? WHERE username = ?", (new_role, selected))
            st.sidebar.success("User berhasil diupdate.")
            st.rerun()
        if col2.button("Hapus", use_container_width=True):
            if selected == st.session_state.user:
                st.sidebar.error("Tidak bisa menghapus akun sendiri.")
            else:
                run_sql("DELETE FROM users WHERE username = ?", (selected,))
                st.sidebar.success("User berhasil dihapus.")
                st.rerun()


def load_data() -> pd.DataFrame:
    df = get_df("SELECT * FROM bahan ORDER BY tgl_disposisi DESC, id DESC")
    if df.empty:
        return df
    df["tgl_disposisi"] = pd.to_datetime(df["tgl_disposisi"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int)
    df["tahun"] = df["tgl_disposisi"].dt.year
    if st.session_state.role == "pic":
        user = st.session_state.user
        df = df[(df["pic1"] == user) | (df["pic2"] == user)].copy()
    return df


def render_header() -> None:
    logo_html = (
        f'<img src="data:image/png;base64,{file_to_base64(LOGO_PATH)}" width="92">'
        if LOGO_PATH.exists()
        else ""
    )
    st.markdown(
        f"""
        <div class="header-card">
            <div class="header-row">
                <div class="header-left">
                    {logo_html}
                    <div>
                        <div class="header-title">Dashboard Monitoring Bahan Paparan Pimpinan</div>
                        <div class="header-subtitle">Monitoring disposisi, paparan, dan narasi</div>
                    </div>
                </div>
                <div class="header-user">{st.session_state.user}<br>{str(st.session_state.role).upper()}</div>
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
        ("TOTAL PAPARAN", total, "#17355c"),
        ("DALAM PROSES", on_progress, "#f59e0b"),
        ("SELESAI", done, "#22c55e"),
        ("PIC AKTIF", total_pic, "#06b6d4"),
        ("BELUM MULAI", not_started, "#94a3b8"),
    ]
    cols = st.columns(len(cards))
    for col, (label, value, color) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card" style="border-left: 6px solid {color};">
                    <div class="kpi-label">{label}</div>
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
        fig = px.pie(jenis, names="jenis_bahan", values="jumlah", hole=0.58)
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
                {"Not_Yet": "Not Yet Started", "In_Progress": "On Progress", "Done": "Done"}
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


def render_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="table-card">', unsafe_allow_html=True)
    top1, top2 = st.columns([5, 1])
    with top1:
        st.markdown('<div class="section-title compact-title">Daftar Bahan Paparan</div>', unsafe_allow_html=True)
    with top2:
        st.markdown(f'<div style="text-align:right;"><span class="badge">{len(df)} Data</span></div>', unsafe_allow_html=True)

    header_cols = st.columns([0.45, 2.6, 1.1, 1.35, 1.1, 1.0, 1.25, 1.0])
    for col, title in zip(header_cols, ["No", "Judul", "Tim Kerja", "PIC", "Status", "Progress", "Output", "Aksi"]):
        col.markdown(f"**{title}**")
    st.divider()

    for no, (_, row) in enumerate(df.iterrows(), start=1):
        pill_class = {
            "Done": "status-done",
            "On Progress": "status-progress",
        }.get(row["status"], "status-notyet")
        progress = max(0, min(100, int(row["progress"] or 0)))

        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.45, 2.6, 1.1, 1.35, 1.1, 1.0, 1.25, 1.0])
        c0.write(no)
        with c1:
            st.markdown(f"**{row['nama_bahan']}**")
            info = []
            if row["jenis_bahan"]:
                info.append(str(row["jenis_bahan"]))
            if pd.notna(row["deadline"]):
                info.append(f"Deadline: {row['deadline'].date()}")
            if info:
                st.caption(" • ".join(info))
        with c2:
            st.write(row["kantor"] or "-")
            surat = safe_path(row["file_surat"])
            if surat and surat.exists():
                if st.button("📩 Surat", key=f"surat_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "surat")
        with c3:
            st.caption(f"PIC 1: {row['pic1'] or '-'}")
            st.caption(f"PIC 2: {row['pic2'] or '-'}")
        with c4:
            st.markdown(f"<span class='status-pill {pill_class}'>{row['status']}</span>", unsafe_allow_html=True)
            if row["keterangan"]:
                st.caption(str(row["keterangan"]))
        with c5:
            st.progress(progress / 100)
            st.caption(f"{progress}%")
        with c6:
            paparan = safe_path(row["file_paparan"])
            narasi = safe_path(row["file_narasi"])
            if paparan and paparan.exists():
                if st.button("👁️ Paparan", key=f"paparan_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "paparan")
            else:
                st.caption("Paparan: -")
            if narasi and narasi.exists():
                if st.button("📝 Narasi", key=f"narasi_{row['id']}", use_container_width=True):
                    open_preview(int(row["id"]), "narasi")
            else:
                st.caption("Narasi: -")
        with c7:
            can_edit = st.session_state.role in {"admin", "atasan"} or st.session_state.user in {row['pic1'], row['pic2']}
            can_delete = st.session_state.role in {"admin", "atasan"}
            a1, a2 = st.columns(2)
            with a1:
                if st.button("✏️", key=f"edit_{row['id']}", disabled=not can_edit):
                    edit_dialog(int(row["id"]))
            with a2:
                if st.button("🗑️", key=f"del_{row['id']}", disabled=not can_delete):
                    delete_dialog(int(row["id"]), str(row["nama_bahan"]))
        st.divider()

    st.markdown("</div>", unsafe_allow_html=True)


def render_dashboard() -> None:
    inject_dashboard_css()
    render_header()

    with st.sidebar:
        st.success(f"Login sebagai: {st.session_state.user} ({st.session_state.role})")
        if st.button("Tambah Bahan", use_container_width=True):
            tambah_bahan_dialog()
        if st.button("Logout", use_container_width=True):
            logout()

    render_user_admin()

    df = load_data()
    if df.empty:
        st.info("Belum ada data bahan.")
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
        key = keyword.strip().lower()
        filtered = filtered[
            filtered["nama_bahan"].fillna("").str.lower().str.contains(key)
            | filtered["instruksi"].fillna("").str.lower().str.contains(key)
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
    if render_preview():
        return
    render_dashboard()


if __name__ == "__main__":
    main()
