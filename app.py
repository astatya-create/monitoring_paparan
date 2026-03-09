import streamlit as st
import sqlite3
import pandas as pd
import base64
import os
from datetime import datetime
import plotly.express as px
from urllib.parse import quote

st.set_page_config(layout="wide")

DB_NAME = "monitoring.db"

def get_base64(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# ================= DB FUNCTIONS =================


def get_users():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT username FROM users", conn)
    conn.close()
    return df["username"].tolist()


def authenticate(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT role FROM users
        WHERE username=? AND password=?
    """, (username, password))
    result = c.fetchone()
    conn.close()
    return result

def logout():
    st.session_state.clear()
    st.rerun()

def get_df(query):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def exec_sql(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def main_app():

    st.sidebar.success(
        f"Login sebagai: {st.session_state.user} ({st.session_state.role})"
    )

# ================= INIT =================
def init_folders():
    paths = [
        "storage/disposisi",
        "storage/output/kabinet",
        "storage/output/legislatif",
        "storage/output/instansi",
        "storage/output/lain-lain",
        "backup"
    ]
    for p in paths:
        os.makedirs(p, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        password TEXT,
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS bahan(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tgl_disposisi DATE,
        nama_bahan TEXT,
        pic1 TEXT,
        pic2 TEXT,
        kantor TEXT,
        jenis_bahan TEXT,
        instruksi TEXT,
        deadline DATE,
        status TEXT,
        progress INTEGER,
        keterangan TEXT,
        file_surat TEXT,
        file_paparan TEXT,
        file_narasi TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bahan_id INTEGER,
        user TEXT,
        action TEXT,
        timestamp DATETIME
    )
    """)

    conn.commit()
    conn.close()

def seed_users():
    conn = sqlite3.connect('monitoring.db', check_same_thread=False)
    
    c = conn.cursor()

    users = [
        ("admin", "admin123", "Pusat"),
    ]

    for user in users:
        c.execute("""
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, user)

    conn.commit()
    conn.close()

# ================= AUDIT =================
def log_action(bahan_id, user, action):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO audit_log VALUES(NULL,?,?,?,?)",
              (bahan_id,user,action,datetime.now()))
    conn.commit()
    conn.close()


# ================= CSS DAN DEF LOGIN PAGE =================
BASE_DIR = os.getcwd()
logo_path = os.path.join(BASE_DIR, "logo_kemenperin.png")
def login_page():

    st.markdown("""
    <style>

    /* Hide Streamlit default UI */
    [data-testid="stSidebar"] {display:none;}
    header {visibility:hidden;}
    footer {visibility:hidden;}

    /* Remove default padding */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }

    .login-wrapper{
        min-height:20vh;
        display:flex;
        justify-content:center;
        align-items:center;
        background:white;
    }

    .login-mini-title {
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 1px;
        color: #64748b;
        text-transform: uppercase;
        margin-bottom: 10px;
        text-align: center;
    }

    .login-title {
        font-size: 30px;
        font-weight: 800;
        color: #0f172a;
        text-align: center;
        line-height: 1.3;
        margin-bottom: 8px;
    }

    .login-sub {
        font-size: 14px;
        color: #64748b;
        text-align: center;
        margin-bottom: 24px;
    }

    .login-logo img {
        width: 50px;
        display: flex;
        justify-content: center;
        margin-bottom: 16px;
    }

    .login-field-label {
        font-size: 13px;
        font-weight: 700;
        color: #475569;
        margin-bottom: 6px;
    }

    div.stButton > button {
        background: #0c4a6e;
        color: white;
        font-weight: 800;
        padding: 12px;
        border-radius: 12px;
        width: 100%;
        border: none;
        box-shadow: 0 8px 18px rgba(0,0,0,0.12);
    }

    div.stButton > button:hover {
        background: #083b56;
        transform: translateY(-1px);
        transition: 0.2s ease;
    }

    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    
    left, center, right = st.columns([3, 2, 3])

    with center:
        st.markdown(f"""
            <div class="header-container">
                <img src="data:image/png;base64,{get_base64(logo_path)}">
            </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="login-mini-title">Monitoring System</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-title">Dashboard Monitoring<br>Bahan Paparan</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div class="login-sub">Silakan masuk ke akun Anda</div>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="login-field-label">Username</div>', unsafe_allow_html=True)
        username = st.text_input(
            "",
            key="login_user",
            label_visibility="collapsed"
        )

        st.markdown('<div class="login-field-label">Password</div>', unsafe_allow_html=True)
        password = st.text_input(
            "",
            type="password",
            key="login_pass",
            label_visibility="collapsed"
        )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("MASUK SEKARANG", key="login_btn"):
            result = authenticate(username, password)
            if result:
                st.session_state.user = username
                st.session_state.role = result[0]
                st.rerun()
            else:
                st.error("Username / Password salah")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


if "user" not in st.session_state:
    login_page()
    st.stop()

# ===== ROUTE PREVIEW (TAB BARU) =====

params = st.query_params

preview_id = params.get("preview_id")
kind = params.get("kind")   # surat | paparan | narasi

if preview_id and kind:

    # amankan query param
    if isinstance(preview_id, list):
        preview_id = preview_id[0]
    if isinstance(kind, list):
        kind = kind[0]

    preview_id = int(preview_id)

    df_prev = get_df(f"""
        SELECT nama_bahan, file_surat, file_paparan, file_narasi
        FROM bahan
        WHERE id = {preview_id}
    """)

    if df_prev.empty:
        st.error("Data tidak ditemukan.")
        st.stop()

    row = df_prev.iloc[0]
    nama = row["nama_bahan"]

    if kind == "surat":
        path = row.get("file_surat", "") or ""
        title = f"Preview Surat — {nama}"

    elif kind == "paparan":
        path = row.get("file_paparan", "") or ""
        title = f"Preview Paparan — {nama}"

    elif kind == "narasi":
        path = row.get("file_narasi", "") or ""
        title = f"Preview Narasi — {nama}"

    else:
        st.error("Parameter kind tidak valid.")
        st.stop()

    st.markdown(f"## {title}")

    if not path:
        st.info("File belum tersedia.")
        st.stop()

    # ubah path relatif menjadi absolut
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)

    if not os.path.exists(path):
        st.error(f"File tidak ditemukan: {path}")
        st.stop()

    ext = os.path.splitext(path)[1].lower()
    
    # cek ukuran file
    file_size = os.path.getsize(path)
    MAX_PREVIEW = 200 * 1024 * 1024  # 200MB

    if ext == ".pdf" and file_size <= MAX_PREVIEW:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        st.markdown(
            f"""
            <iframe src="data:application/pdf;base64,{b64}"
                    width="100%" height="900"
                    style="border:none;border-radius:12px;"></iframe>
            """,
            unsafe_allow_html=True
        )
    
    elif ext == ".pdf" and file_size > MAX_PREVIEW:

        

        with open(path, "rb") as f:
            st.download_button(
                "⬇️ Download PDF",
                f,
                file_name=os.path.basename(path),
                key=f"download_large_{preview_id}_{kind}"
            )

    else:
        with open(path, "rb") as f:
            st.download_button(
                "⬇️ Download file",
                f,
                file_name=os.path.basename(path),
                key=f"download_preview_{preview_id}_{kind}"
            )

        st.info("Preview inline stabil saat ini hanya untuk PDF. Silakan download untuk tipe lain.")

    st.stop()


# ================ CSS DASHBOARD ==========================

st.markdown("""
<style>

[data-testid="stAppViewContainer"] {
    background-color: #f1f5f9;
}

.block-container { padding-top: 2rem; }

/* ===== HEADER WRAPPER ===== */
.header-container {
    display: flex;
    align-items: center;
    gap: 18px;
    margin-bottom: 20px;   /* jarak ke KPI */
}

/* ===== TITLE AREA ===== */
.header-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* HEADER */
.dashboard-title {
    font-size: 34px;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 0px;
}

.dashboard-sub {
    font-size: 30px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #64748b;
    margin-bottom: 12px;  /* DIPERKECIL */
}

/* ===== LOGO ===== */
.header-logo img {
    width: 200px;
}

/* ===== TITLE AREA ===== */
.header-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* ===== FIXED HEADER RESPONSIVE ===== */
.header-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;

    z-index: 1000;

    background: white;
    padding: 18px 3rem 12px 3rem;

    border-bottom: 1px solid #e5e7eb;
    transition: all 0.3s ease;
}

/* Tambahkan jarak ke konten utama agar KPI tidak ketutup */
[data-testid="stAppViewContainer"] .block-container {
    padding-top: 110px !important;
}

/* ===== Saat Sidebar Terbuka ===== */
section[data-testid="stSidebar"][aria-expanded="true"] ~ div .header-container {
    left: 260px;
}

/* ===== Saat Sidebar Ditutup ===== */
section[data-testid="stSidebar"][aria-expanded="false"] ~ div .header-container {
    left: 0;
}

/* Tambah garis bawah elegan */
.header-container {
    border-bottom: 1px solid #e5e7eb;
}

.logout-area {
    position: fixed;
    top: 30px;
    right: 30px;
    z-index: 1100;
}

/* KPI ROW SPACING */
.kpi-row {
    margin-top: 5px;      /* DIPERKECIL */
    margin-bottom: 5px;  /* DITAMBAH */
}

/* KPI CARD */
.kpi-card {
    background: white;
    padding: 20px;
    border-radius: 18px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.05);
    transition: all 0.2s ease-in-out;
}

.kpi-card:hover {
    transform: translateY(-2px);
}

.kpi-title {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #64748b;
    text-transform: uppercase;
}

.kpi-value {
    font-size: 32px;
    font-weight: 800;
    margin-top: 6px;
    color: #0f172a;
}

/* SECTION CARD */
.section-card {
    background: #ffffff;
    padding: 28px;
    border-radius: 20px;
    box-shadow: 0 4px 18px rgba(15,23,42,0.05);
    margin-top: 35px;
}

.section-card .stDataFrame {
margin-top: 10px;
}

/* SECTION TITLE FOR GRAFIK */
.section-title {
    font-size: 20px;
    font-weight: 800;
    color: #0c4a6e;
    margin-bottom: 20px;
}

/* ===== SIDEBAR CONTAINER ===== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c4a6e 0%, #09324a 100%);
    padding-top: 20px;
    border-right: 1px solid rgba(255,255,255,0.08);
}

/* Remove default padding gap */
section[data-testid="stSidebar"] > div {
    padding-top: 0px;
}

/* ===== TEXT GLOBAL ===== */
section[data-testid="stSidebar"] * {
    color: #ffffff !important;
    font-size: 14px;
}

/* ===== SIDEBAR TITLE ===== */
.sidebar-title {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
    margin-bottom: 20px;
    opacity: 0.85;
}

/* ===== WIDGET LABEL ===== */
section[data-testid="stSidebar"] label {
    font-weight: 600 !important;
    margin-bottom: 4px !important;
}

/* ===== SELECTBOX ===== */
section[data-testid="stSidebar"] div[data-baseweb="select"] {
    background-color: rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}

/* ===== TEXT INPUT ===== */
section[data-testid="stSidebar"] input {
    background-color: rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    color: white !important;
}

/* ===== BUTTON ===== */
section[data-testid="stSidebar"] button {
    background-color: #0f5a85 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    border: none !important;
}

section[data-testid="stSidebar"] button:hover {
    background-color: #136a9f !important;
    transform: translateY(-1px);
    transition: 0.2s;
}

/* ===== EXPANDER ===== */
section[data-testid="stSidebar"] .streamlit-expanderHeader {
    background-color: rgba(255,255,255,0.05) !important;
    border-radius: 8px !important;
    padding: 6px 10px !important;
}

/* ===== DIVIDER ===== */
.sidebar-divider {
    height: 1px;
    background: rgba(255,255,255,0.1);
    margin: 20px 0;
}

/* ===== INPUT TEXT (yang diketik user) ===== */
section[data-testid="stSidebar"] input {
    color: #111827 !important;
    background-color: white !important;
}

/* ===== SELECTBOX (isi dropdown terpilih) ===== */
section[data-testid="stSidebar"] div[data-baseweb="select"] div {
    color: #111827 !important;
}

/* ===== Textarea kalau ada ===== */
section[data-testid="stSidebar"] textarea {
    color: #111827 !important;
    background-color: white !important;
}

[data-testid="stDataFrame"] {
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 4px 12px rgba(0,0,0,0.04);
}

#====Tabel====
.table-card {
  background: #ffff;
  border-radius: 18px;
  box-shadow: 0 4px 18px rgba(15,23,42,0.06);
  padding: 18px 18px;
  margin-top: 18px;
}

.table-header {
  display:flex; justify-content:space-between; align-items:center;
  padding: 6px 4px 14px 4px;
  border-bottom: none;
}

.table-title {
  font-weight: 800; letter-spacing: 1px; color:#0c4a6e;
  font-size: 18px; text-transform: uppercase;
  text-align:center;
}

.table-count {
  background:#0c4a6e; color:#fff;
  padding:6px 10px; border-radius: 999px;
  font-size:12px; font-weight:700;
}

.row {
  display:grid;
  grid-template-columns: 0.6fr 3fr 1.5fr 1.3fr 2fr 1.5fr 1.5fr 1.2fr;
  gap: 12px;
  align-items:center;
  padding: 14px 6px;
  border-bottom: none;
  border-top: 2px solid #c7c7d4;
}

.row:last-child { border-bottom: none; }

.col-title .judul { font-weight:800; color:#0f172a; font-size:16px; }
.badge {
  display:inline-block; margin-top:6px;
  background:#e0f2fe; color:#075985;
  font-weight:800; font-size:11px;
  padding:6px 10px; border-radius: 10px;
}
.deadline { margin-left:10px; color:#ef4444; font-weight:800; font-size:12px; }

.tim { font-weight:800; color:#0f172a; }
.tim-sub { color:#94a3b8; font-style:italic; font-size:12px; margin-top:4px; }

.pic-item { display:flex; align-items:center; gap:8px; margin:4px 0; color:#0f172a; font-weight:700; }
.dot1,.dot2{
  width:10px;height:10px;border-radius:999px; display:inline-block;
}
.dot1{ background:#2563eb;}
.dot2{ background:#a855f7;}

.pill {
  display:inline-block;
  padding:6px 12px; border-radius: 999px;
  font-weight:900; font-size:16px;
  background:#f1f5f9; color:#475569;
  text-align:center;
}
.pill.done{ background:#dcfce7; color:#166534;}
.pill.progress{ background:#fef9c3; color:#854d0e;}
.pill.notyet{ background:#e2e8f0; color:#334155;}

.prog-wrap { display:flex; align-items:center; gap:10px; }
.prog-bar{
  flex:1; height:10px; background:#e2e8f0;
  border-radius:999px; overflow:hidden;
}
.prog-fill{ height:100%; background:#0c4a6e; }
.prog-text{ font-weight:900; color:#0f172a; font-size:12px; width:40px; text-align:right; }

.table-no{
    text-align:center;
    font-weight:700;
    color:#475569;
}
/* ===== CSSROW BORDER ===== */
.table-row {
    padding-top: 10px;
    padding-bottom: 10px;
    border-bottom: none;
}

.table-row:last-child { border-top: 2px solid #c7c7d4; }

/* ===== CSSROW BORDER FINISH ===== */

.ket-text {
    font-size:12px;
    color:#64748b;
    margin-top:6px;
    line-height:1.3;
}

.status-wrap{
    display:flex;
    flex-direction:column;
    align-items:center;   /* center horizontal */
    justify-content:center;
    gap:3px;
    text-align:center;
}

.prog-wrap-v{
  width:100% !important;
  display:flex !important;
  flex-direction:column !important;
  align-items:stretch !important;   /* penting: bar full lebar */
  gap:6px !important;
}

.prog-bar-v{
  width:100% !important;
  height:10px !important;
  background:#e2e8f0 !important;
  border-radius:999px !important;
  overflow:hidden !important;
}

.prog-fill-v{
  height:100% !important;
  background:#0c4a6e !important;
  border-radius:999px !important;
  transition: width .5s ease;
}

.prog-text-v{
  text-align:center !important;
  font-size:12px !important;
  font-weight:900 !important;
  color:#64748b !important;
  line-height:1 !important;
}

</style>
""", unsafe_allow_html=True)

# ================= MAIN =================

with st.sidebar:
    if st.button("Logout", key="logout_sidebar", use_container_width=True):
        logout()

main_app()

#==== POP UP FORM & KONFIRMASI =====
@st.dialog("Edit Bahan Paparan")
def edit_dialog(edit_id: int):
    df_edit = get_df(f"SELECT * FROM bahan WHERE id={edit_id}")
    if df_edit.empty:
        st.error("Data tidak ditemukan.")
        return

    row = df_edit.iloc[0]

    status = st.selectbox(
        "Status",
        ["Not Yet Started", "On Progress", "Done"],
        index=["Not Yet Started", "On Progress", "Done"].index(row["status"])
    )

    progress = st.slider(
        "Progress (%)",
        0, 100,
        int(row["progress"] if row["progress"] else 0)
    )

    keterangan = st.text_area("Keterangan", row["keterangan"] or "")

    file_paparan = st.file_uploader("Upload Paparan", type=["pdf"], max_upload_size=500)
        
    file_narasi  = st.file_uploader("Upload Narasi", type=None)
    
    pap_path = row.get("file_paparan", "") or ""
    pap_exists = bool(pap_path) and os.path.exists(pap_path)
    
    if pap_exists:
        instruksi = st.text_area(
            "Keywords / Instruksi",
            row["instruksi"] or "",
            key=f"edit_instruksi_{edit_id}",
            height=120
        )
    else:
        instruksi = row["instruksi"] or ""
        st.info("Keywords bisa diisi setelah lampiran Output/Paparan tersedia.")
    
    colA, colB = st.columns(2)

    with colA:
        if st.button("💾 Simpan", key=f"save_edit_{edit_id}"):

            pap_path = row.get("file_paparan", "") or ""
            nar_path = row.get("file_narasi", "") or ""

            # amankan progress
            try:
                progress_val = int(progress) if progress is not None else 0
            except:
                progress_val = 0

            # upload paparan
            if file_paparan:
                os.makedirs("storage/output/paparan", exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pap_path = f"storage/output/paparan/{timestamp}_{file_paparan.name}"

                with open(pap_path, "wb") as f:
                    f.write(file_paparan.getbuffer())

            # upload narasi
            if file_narasi:
                os.makedirs("storage/output/narasi", exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nar_path = f"storage/output/narasi/{timestamp}_{file_narasi.name}"

                with open(nar_path, "wb") as f:
                    f.write(file_narasi.getbuffer())

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            c.execute("""
                UPDATE bahan
                SET status=?,
                    progress=?,
                    keterangan=?,
                    instruksi=?,
                    file_paparan=?,
                    file_narasi=?
                WHERE id=?
            """, (
                status,
                progress_val,
                keterangan,
                instruksi,
                pap_path,
                nar_path,
                edit_id
                ))

            conn.commit()
            conn.close()

            st.success("Berhasil diupdate")
            st.rerun()

    with colB:
        if st.button("Batal"):
            st.rerun()

@st.dialog("Konfirmasi Hapus")
def confirm_delete_dialog(bahan_id: int, nama_bahan: str):
    st.warning(f"Yakin ingin menghapus **{nama_bahan}**?")
    colA, colB = st.columns(2)
    with colA:
        if st.button("🗑️ Ya, Hapus", key=f"confirm_del_{bahan_id}"):
            exec_sql("DELETE FROM bahan WHERE id=?", (bahan_id,))
            st.success("Data berhasil dihapus.")
            st.rerun()
    with colB:
        if st.button("Batal", key=f"cancel_del_{bahan_id}"):
            st.rerun()


# ================= TAMBAH BAHAN =================

def get_pic_users():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(
        "SELECT username FROM users WHERE role = 'pic'",
        conn
    )
    conn.close()
    return df["username"].tolist()

if st.session_state.role in ["admin", "atasan", "pic"]:

    st.sidebar.header("Tambah Bahan")

    daftar_pic = get_pic_users()

    with st.sidebar.form("form_tambah_bahan", clear_on_submit=True):

        nama = st.text_input("Nama Bahan")
        tgl_disposisi = st.date_input("Tanggal Disposisi")

        pic1 = None
        pic2 = None
        kantor = None
        jenis = None
        instruksi = ""
        deadline = None

        if not daftar_pic:
            st.warning("Belum ada user PIC")
        else:
            pic1 = st.selectbox("PIC 1", daftar_pic)
            pic2 = st.selectbox("PIC 2", daftar_pic)

            kantor = st.selectbox("Kantor", ["Tulodong", "Pusat"])
            jenis = st.selectbox("Jenis", ["Kabinet", "Legislatif", "Instansi", "Lain-lain"])
            instruksi = st.text_area("Keywords")
            deadline = st.date_input("Deadline")

        file_surat = st.file_uploader(
            "Upload Surat (Undangan/Disposisi)",
            type=["pdf", "docx"]
        )

        submitted = st.form_submit_button("Simpan")

    if submitted:

        if not nama.strip():
            st.sidebar.error("Nama bahan wajib diisi")

        elif not daftar_pic:
            st.sidebar.error("Belum ada user PIC")

        elif pic1 == pic2:
            st.sidebar.error("PIC 1 dan PIC 2 tidak boleh sama")

        else:
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()

                # ================= CEK DUPLIKASI =================
                c.execute("""
                    SELECT id FROM bahan
                    WHERE nama_bahan = ? AND deadline = ?
                """, (nama, deadline))

                if c.fetchone():
                    st.sidebar.error("⚠️ Agenda dengan nama bahan & deadline tersebut sudah ada!")
                    conn.close()

                else:
                    # ================= SIMPAN FILE =================
                    file_path = ""

                    if file_surat:
                        tahun = pd.to_datetime(tgl_disposisi).year
                        folder = f"storage/disposisi/{tahun}"
                        os.makedirs(folder, exist_ok=True)

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        file_path = f"{folder}/{timestamp}_{file_surat.name}"

                        with open(file_path, "wb") as f:
                            f.write(file_surat.getbuffer())

                    # ================= INSERT DATA =================
                    c.execute("""
                        INSERT INTO bahan (
                            tgl_disposisi,
                            nama_bahan,
                            pic1,
                            pic2,
                            kantor,
                            jenis_bahan,
                            instruksi,
                            deadline,
                            status,
                            file_surat
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tgl_disposisi,
                        nama,
                        pic1,
                        pic2,
                        kantor,
                        jenis,
                        instruksi,
                        deadline,
                        "Not Yet Started",
                        file_path
                    ))

                    conn.commit()
                    conn.close()

                    st.sidebar.success("Bahan berhasil ditambahkan")
                    st.rerun()

            except sqlite3.Error as e:
                st.sidebar.error(f"Terjadi kesalahan database: {e}")   

# ================= TAMBAH & KELOLA USER =================

def tambah_user():
    st.sidebar.header("Tambah User")

    username = st.sidebar.text_input("Username Baru")
    password = st.sidebar.text_input("Password", type="password")
    role = st.sidebar.selectbox("Role", ["admin", "atasan", "pic"])

    if st.sidebar.button("Simpan User"):
        if not username or not password:
            st.sidebar.error("Username & Password wajib diisi")
        else:
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()

                c.execute("""
                    INSERT INTO users (username, password, role)
                    VALUES (?, ?, ?)
                """, (username.strip(), password, role))

                conn.commit()
                conn.close()

                st.sidebar.success("User berhasil ditambahkan")
                st.rerun()

            except sqlite3.IntegrityError:
                st.sidebar.error("Username sudah digunakan")

def kelola_user():
    st.sidebar.header("Kelola User")

    conn = sqlite3.connect(DB_NAME)
    df_users = pd.read_sql("SELECT * FROM users", conn)
    conn.close()

    if df_users.empty:
        st.sidebar.info("Belum ada user")
        return

    user_selected = st.sidebar.selectbox(
        "Pilih User",
        df_users["username"].tolist()
    )

    user_data = df_users[df_users["username"] == user_selected].iloc[0]

    st.sidebar.markdown("### Edit User")

    new_password = st.sidebar.text_input(
        "Password Baru (kosongkan jika tidak diubah)",
        type="password"
    )

    new_role = st.sidebar.selectbox(
        "Role",
        ["admin", "atasan", "pic"],
        index=["admin", "atasan", "pic"].index(user_data["role"])
    )

    col1, col2 = st.sidebar.columns(2)

    # ================= EDIT USER =================
    if col1.button("Update"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        if new_password:
            c.execute("""
                UPDATE users
                SET password = ?, role = ?
                WHERE username = ?
            """, (new_password, new_role, user_selected))
        else:
            c.execute("""
                UPDATE users
                SET role = ?
                WHERE username = ?
            """, (new_role, user_selected))

        conn.commit()
        conn.close()

        st.sidebar.success("User berhasil diupdate")
        st.rerun()

    # ================= HAPUS USER =================
    if col2.button("Hapus"):
        if user_selected == st.session_state.user:
            st.sidebar.error("Tidak bisa menghapus akun sendiri")
        else:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM users WHERE username = ?", (user_selected,))
            conn.commit()
            conn.close()

            st.sidebar.success("User berhasil dihapus")
            st.rerun()

if st.session_state.role == "admin":
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### **MENU ADMIN**")

    menu_admin = st.sidebar.radio(
        "",
        ["Tambah User", "Kelola User"]
    )

    if menu_admin == "Tambah User":
        tambah_user()

    elif menu_admin == "Kelola User":
        kelola_user()

# ================= LOAD DATA =================

# Filter untuk PIC
if st.session_state.role == "PIC":
    df = df[
        (df["pic1"] == st.session_state.user) |
        (df["pic2"] == st.session_state.user)
    ]


# ================= KONVERSI TANGGAL =================

# Ambil data dulu
df = get_df("SELECT * FROM bahan")
df["tgl_disposisi"] = pd.to_datetime(
    df["tgl_disposisi"],
    errors="coerce"
)
df = df.dropna(subset=["tgl_disposisi"]).copy()
df["tahun"] = df["tgl_disposisi"].dt.year

if df.empty:
    st.warning("Belum ada data bahan")
    st.stop()

# ================= FILTER SIDEBAR =================
with st.sidebar:

    st.markdown("### Filter Data")

    # Tahun
    tahun_list = sorted(df["tahun"].unique())

    tahun_pilih = st.selectbox(
        "Tahun",
        tahun_list,
        key="filter_tahun"
    )

    # Keyword
    keyword = st.text_input(
        "Search Keyword",
        placeholder="Nama bahan / instruksi",
        key="filter_keyword"
    )

    # PIC
    pic_list = sorted(
        pd.concat([df["pic1"], df["pic2"]]).dropna().unique()
    )

    pic_filter = st.selectbox(
        "PIC",
        ["Semua"] + pic_list,
        key="filter_pic"
    )

    # Kantor
    kantor_list = sorted(df["kantor"].dropna().unique())

    kantor_filter = st.selectbox(
        "Kantor",
        ["Semua"] + kantor_list,
        key="filter_kantor"
    )

# ================= APPLY FILTER =================

df_tahun = df[df["tahun"] == tahun_pilih].copy()

# filter keyword
if keyword.strip():
    k = keyword.lower()

    df_tahun = df_tahun[
        df_tahun["nama_bahan"].fillna("").str.lower().str.contains(k) |
        df_tahun["instruksi"].fillna("").str.lower().str.contains(k)
    ]

# filter PIC
if pic_filter != "Semua":
    df_tahun = df_tahun[
        (df_tahun["pic1"] == pic_filter) |
        (df_tahun["pic2"] == pic_filter)
    ]

# filter kantor
if kantor_filter != "Semua":
    df_tahun = df_tahun[
        df_tahun["kantor"] == kantor_filter
    ]

# ================= MONITORING =================

st.markdown(f"""
<div class="header-container">
    <div class="header-logo">
        <img src="data:image/png;base64,{get_base64(logo_path)}">
    </div>
    <div class="header-text">
        <div class="dashboard-title">Dashboard Monitoring Bahan Paparan Pimpinan</div>
        <div class="dashboard-sub">Bagian PDSIA</div>
    </div>
</div>
""", unsafe_allow_html=True)

if not df_tahun.empty:

    df_tahun["deadline"] = pd.to_datetime(df_tahun["deadline"])
    today = pd.to_datetime("today")

# ================= KPI SUMMARY =================

    total = len(df_tahun)
    done = len(df_tahun[df_tahun["status"] == "Done"])
    canceled = len(df_tahun[df_tahun["status"] == "Canceled"])
    progress = len(df_tahun[df_tahun["status"] == "On Progress"])
    not_started = len(df_tahun[df_tahun["status"] == "Not Yet Started"])

    aktif = len(
        df_tahun[
            (df_tahun["status"] != "Done") &
            (df_tahun["status"] != "Canceled")
        ]
    )

    overdue = len(
        df_tahun[
            (df_tahun["deadline"] < today) &
            (df_tahun["status"] != "Done") &
            (df_tahun["status"] != "Canceled")
        ]
    )

    # Hitung PIC Aktif (berbasis tahun)
    df_pic1 = df_tahun[["pic1"]].rename(columns={"pic1": "pic"})
    df_pic2 = df_tahun[["pic2"]].rename(columns={"pic2": "pic"})
    df_all_pic = pd.concat([df_pic1, df_pic2])
    df_all_pic = df_all_pic[df_all_pic["pic"].notna()]
    total_pic = df_all_pic["pic"].nunique()

    
    
    # KPI layout clean (1 baris saja)
    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns(5)

    def kpi_card(title, value, color):
        st.markdown(f"""
        <div class="kpi-card" style="border-left:6px solid {color};">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    with col1:
        kpi_card("TOTAL PAPARAN", total, "#0c4a6e")

    with col2:
        kpi_card("DALAM PROSES", progress, "#facc15")

    with col3:
        kpi_card("SELESAI", done, "#22c55e")

    with col4:
        kpi_card("PIC AKTIF", total_pic, "#06b6d4")

    with col5:
        kpi_card("BELUM MULAI", not_started, "#94a3b8")

    st.markdown('</div>', unsafe_allow_html=True)


# ================= BEBAN KERJA  =================
colA, colB, colC = st.columns(3)

if not df.empty:
    with colA:
    # ================== DONUT CHART (JENIS BAHAN) ==================
        st.markdown(f'<div class="section-title">Komposisi Jenis Bahan ({tahun_pilih})</div>', unsafe_allow_html=True)

        jenis_count = df_tahun["jenis_bahan"].fillna("Unknown").value_counts().reset_index()
        jenis_count.columns = ["jenis_bahan", "jumlah"]

        fig = px.pie(jenis_count, names="jenis_bahan", values="jumlah", hole=0.55)
        fig.update_traces(textinfo="percent+label")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False, paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with colB:
        st.markdown(f'<div class="section-title">Distribusi Bahan Per PIC ({tahun_pilih})</div>', unsafe_allow_html=True)

        # WORKLOAD PIC
        df_pic = df[["pic1", "pic2", "status"]]
        df_pic1 = df_pic.rename(columns={"pic1": "PIC"}).drop(columns=["pic2"])
        df_pic2 = df_pic.rename(columns={"pic2": "PIC"}).drop(columns=["pic1"])

        df_all_pic = pd.concat([df_pic1, df_pic2], ignore_index=True)

        beban = df_all_pic.groupby("PIC").agg(
            Total=("status", "count"),
            In_Progress=("status", lambda x: (x == "On Progress").sum()),
            Done=("status", lambda x: (x == "Done").sum())
        ).reset_index()

        # (opsional) kalau Anda juga mau tampilkan yang belum mulai
        beban["Not_Yet"] = beban["Total"] - beban["In_Progress"] - beban["Done"]

        beban = beban.sort_values("Total", ascending=False)

        # ubah ke format long untuk plotly
        beban_long = beban.melt(
             id_vars=["PIC", "Total"],
             value_vars=["Not_Yet", "In_Progress", "Done"],   # kalau tidak mau Not_Yet, hapus dari sini
             var_name="Status",
             value_name="Jumlah"
         )

        # label status agar rapi
        status_label = {
            "Not_Yet": "Not Yet Started",
            "In_Progress": "On Progress",
            "Done": "Done"
        }
        beban_long["Status"] = beban_long["Status"].map(status_label)

        import plotly.express as px

        fig = px.bar(
            beban_long,
            y="PIC",
            x="Jumlah",
            color="Status",
            orientation="h",
            barmode="stack",
            hover_data={"Total": True, "Jumlah": True, "PIC": False},
        )

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(categoryorder="total ascending"),  # bar terbesar di atas
            legend_title_text=""
        )

        st.plotly_chart(fig, use_container_width=True)

    with colC:
        st.markdown(f'<div class="section-title">Distribusi Bahan Per Tim Kerja ({tahun_pilih})</div>', unsafe_allow_html=True)
        # ==========================
        # BEBAN KERJA PER KANTOR
        # ==========================

        # Tentukan daftar kantor tetap
        daftar_kantor = ["Pusat", "Tulodong"]

        # Hitung jumlah bahan per kantor
        beban_kantor = df["kantor"].value_counts().reindex(daftar_kantor, fill_value=0).reset_index()
        beban_kantor.columns = ["Kantor", "Jumlah"]
    
        # Buat grafik batang
        fig_kantor = px.bar(
            beban_kantor,
            x="Kantor",
            y="Jumlah",
            text="Jumlah",
            color="Kantor",
            category_orders={"Kantor": daftar_kantor},  # Ini kunci supaya axis tetap muncul
            color_discrete_map={
                "Pusat": "#0c4a6e",
                "Tulodong": "#94a3b8"
            }
        )

        fig_kantor.update_traces(textposition="outside")

        fig_kantor.update_layout(
            yaxis=dict(
                dtick=1,
                gridcolor="rgba(0,0,0,0.05)"
            ),
            xaxis_title="",
            yaxis_title="Jumlah Bahan",
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=10, r=10, t=10, b=10)
        )

        st.plotly_chart(fig_kantor, use_container_width=True)

else:
    st.info("Belum ada data bahan")

st.markdown('</div>', unsafe_allow_html=True)

# ================= TREND BULANAN PER TAHUN =================

colA, colB = st.columns(2)
with colA:

    st.markdown(
        f'<div class="section-title">Tren Bulanan Penyusunan Bahan ({tahun_pilih})</div>',
        unsafe_allow_html=True
    )

    if not df_tahun.empty:

        df_tahun = df_tahun.copy()
        df_tahun["tgl_disposisi"] = pd.to_datetime(df_tahun["tgl_disposisi"])

        # Buat kolom bulan
        df_tahun["bulan_angka"] = df_tahun["tgl_disposisi"].dt.month
        df_tahun["bulan_label"] = df_tahun["tgl_disposisi"].dt.strftime("%b %Y")

        trend_bulan = (
            df_tahun
            .groupby(["bulan_angka", "bulan_label"])
            .size()
            .reset_index(name="total")
            .sort_values("bulan_angka")
        )

        import plotly.express as px

        fig_bulan = px.line(
            trend_bulan,
            x="bulan_label",
            y="total",
            markers=True
        )

        fig_bulan.update_traces(
            line=dict(
                color="#06b6d4",
                width=4,
                shape="spline"   # garis smooth
            ),
            marker=dict(
                size=10,
                color="#06b6d4",
                line=dict(width=2, color="white")
            ),
            fill="tozeroy",   # area bawah garis
            fillcolor="rgba(6,182,212,0.15)"
        )

        fig_bulan.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            margin=dict(l=10, r=10, t=20, b=10),

            yaxis=dict(
                range=[0, trend_bulan["total"].max() + 1 if not trend_bulan.empty else 1],
                dtick=1,
                gridcolor="rgba(0,0,0,0.05)"
            ),

            xaxis=dict(
                showgrid=False
            ),

            xaxis_title="",
            yaxis_title="Jumlah Bahan"
        )

        st.plotly_chart(fig_bulan, use_container_width=True)

    else:
        st.info("Belum ada data tahun ini")

# ================= TREND PER TRIWULAN =================

with colB:
    st.markdown(f'<div class="section-title">Tren Triwulanan Penyusunan Bahan ({tahun_pilih})</div>', unsafe_allow_html=True)


    # Pastikan tidak kosong
    if not df_tahun.empty:

        df_tahun = df_tahun.copy()

        # Pastikan datetime
        df_tahun["tgl_disposisi"] = pd.to_datetime(df_tahun["tgl_disposisi"])

        # Buat kolom turunan
        df_tahun["tahun"] = df_tahun["tgl_disposisi"].dt.year
        df_tahun["bulan"] = df_tahun["tgl_disposisi"].dt.month
        df_tahun["triwulan_angka"] = df_tahun["tgl_disposisi"].dt.quarter

        roman = {1: "I", 2: "II", 3: "III", 4: "IV"}
        df_tahun["triwulan"] = df_tahun["triwulan_angka"].map(roman)

        trend_triwulan = (
           df_tahun
        .groupby(["triwulan_angka", "triwulan"])
        .size()
        .reset_index(name="total")
        .sort_values("triwulan_angka")
    )


        fig_triwulan = px.bar(
            trend_triwulan,
            x="triwulan",
            y="total",
            text="total"
        )

        fig_triwulan.update_traces(
            marker=dict(
                color="#94a3b8"
            )
        )

        fig_triwulan.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            margin=dict(l=10, r=10, t=20, b=10),
            yaxis=dict(
                range=[0, trend_triwulan["total"].max() + 1 if not trend_triwulan.empty else 1],
                dtick=1,
                gridcolor="rgba(0,0,0,0.05)"
            ),
            xaxis=dict(
                showgrid=False
            ),
            xaxis_title="",
            yaxis_title="Jumlah Bahan"
        )
        st.plotly_chart(fig_triwulan, use_container_width=True)


    else:
        st.info("Belum ada data tahun ini")

#====Tabel monitoring====

st.markdown('<div class="table-card">', unsafe_allow_html=True)

st.markdown(f"""
<div class="table-header">
  <div class="table-title">DAFTAR BAHAN PAPARAN</div>
  <div class="table-count">{len(df_tahun)} Data</div>
</div>
""", unsafe_allow_html=True)

# Header kolom (opsional, kalau mau sama seperti contoh)
st.markdown("""
<div class="row" style="font-weight:900;color:#161617;text-transform:uppercase;font-size:16px;text-align:center;">
  <div>No</div>
  <div>Judul & Kategori</div>
  <div>Tim Kerja</div>
  <div>PIC</div>
  <div>Status</div>
  <div>Progres</div>
  <div>Output</div>
  <div>Aksi</div>
</div>
""", unsafe_allow_html=True)

for no, (_, r) in enumerate(df_tahun.iterrows(), start=1):
    status = str(r.get("status", ""))

    if status == "Done":
        pill_class, pill_text = "done", "FINAL"
    elif status == "On Progress":
        pill_class, pill_text = "progress", "PROSES"
    else:
        pill_class, pill_text = "notyet", "BELUM"

    progress_raw = r.get("progress", 0)

    if pd.isna(progress_raw) or progress_raw == "":
        progres = 0
    else:
        progres = int(float(progress_raw))
    
    st.markdown('<div class="table-row">', unsafe_allow_html=True)

    c0, c1, c2, c3, c4, c5, c6, c7 = st.columns(
        [0.6, 3, 1.5, 1.3, 2, 1.5, 1.5, 1.2],
        vertical_alignment="center"
    )
    
    with c0:
        st.markdown(
            f'<div style="text-align:center;font-weight:700;color:#475569;">{no}</div>',
            unsafe_allow_html=True
        )
    with c1:
        st.markdown(f"""
        <div class="col-title">
            <div class="judul">{r['nama_bahan']}</div>
            <span class="badge">{r['jenis_bahan']}</span>
            <span class="deadline">📅 {str(r['deadline'])}</span>
        </div>
        """, unsafe_allow_html=True)

    with c2:

        # tampilkan kantor
        st.markdown(f"""
        <div>
            <div class="tim">{r.get('kantor','')}</div>
            <div class="tim-sub">
        """, unsafe_allow_html=True)

        # link preview surat
        surat_path = r.get("file_surat", "")

        if surat_path and os.path.exists(surat_path):

            st.markdown(
                f"""
                <a href="?preview_id={int(r['id'])}&kind=surat"
                   target="_blank"
                   rel="noopener noreferrer"
                   style="text-decoration:none;font-size:16px;">
                   📩 Disposisi
                </a>
                """,
                unsafe_allow_html=True
            )

        else:
            st.caption("Disposisi: -")

        # tutup div html
        st.markdown("""
            </div>
        </div>
        """, unsafe_allow_html=True)

       
    with c3:
        st.markdown(f"""
        <div>
            <div class="pic-item"><span class="dot1"></span>{r.get('pic1','-')}</div>
            <div class="pic-item"><span class="dot2"></span>{r.get('pic2','-')}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        prog = int(progres) if str(progres).isdigit() else int(progres or 0)
        prog = max(0, min(100, prog))

        st.markdown(f"""
        <div class="prog-wrap-v">
            <div class="prog-bar-v">
                <div class="prog-fill-v" style="width:{prog}%;"></div>
            </div>
            <div class="prog-text-v">{prog}%</div>
        </div>
        """, unsafe_allow_html=True)    

    with c5:
        st.markdown(f"""
        <div class="status-wrap">
            <span class="pill {pill_class}">{pill_text}</span>
            <div class="ket-text">{r.get("keterangan","")}</div>
        </div>
        """, unsafe_allow_html=True)

    with c6:
        pap_path = r.get("file_paparan", "") or ""
        nar_path = r.get("file_narasi", "")

        # Paparan
        if pap_path:
            pap_full = pap_path if os.path.isabs(pap_path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), pap_path)
        else:
            pap_full = ""

        if pap_full and os.path.exists(pap_full):
            st.markdown(
                f"""
                <a href="?preview_id={int(r['id'])}&kind=paparan"
                   target="_blank" rel="noopener noreferrer"
                   style="text-decoration:none;font-size:16px;margin-right:10px;">
                   👁️Paparan
                </a>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("<span style='color:#cbd5e1;font-size:16px;margin-right:10px;'>👁️Paparan</span>", unsafe_allow_html=True)

        # Narasi
        if nar_path and os.path.exists(nar_path):
            st.markdown(
                f"""
                <a href="?preview_id={int(r['id'])}&kind=narasi"
                   target="_blank" rel="noopener noreferrer"
                   style="text-decoration:none;font-size:16px;">
                   Narasi
                </a>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("<span style='color:#cbd5e1;font-size:16px;'>📝 Narasi </span>", unsafe_allow_html=True)

    with c7:

        col_edit, col_del = st.columns(2)

        # validasi PIC
        if st.session_state.role == "pic":
            if st.session_state.user not in [r["pic1"], r["pic2"]]:
                st.button("✏️", key=f"edit_disabled_{r['id']}", disabled=True)
                continue
        # tombol edit
        with col_edit:
            if st.button("✏️", key=f"edit_{int(r['id'])}", help="Edit"):
                edit_dialog(int(r["id"]))

        with col_del:
            if st.button("🗑️", key=f"del_{int(r['id'])}", help="Hapus"):
                    confirm_delete_dialog(int(r["id"]), str(r["nama_bahan"]))

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

#=====RENDER Tombol EDIT=====
if "edit_id" in st.session_state:
    edit_id = st.session_state.edit_id

    df_edit = get_df(f"SELECT * FROM bahan WHERE id={edit_id}")
    if df_edit.empty:
        st.error("Data edit tidak ditemukan.")
    else:
        row = df_edit.iloc[0]

        st.markdown("### Edit Bahan")

        status = st.selectbox(
            "Status",
            ["Not Yet Started", "On Progress", "Done"],
            index=["Not Yet Started", "On Progress", "Done"].index(row["status"])
        )

        progress = st.slider(
            "Progress",
            0,
            100,
            int(row["progress"] or 0),
            disabled=(status == "Done")
)

        if status == "Done":
           progress = 100

        keterangan = st.text_area("Keterangan", row["keterangan"] or "")

        colA, colB = st.columns(2)
        with colA:
            if st.button("💾 Simpan", key="save_edit"):
                exec_sql(
                    """
                    UPDATE bahan
                    SET status=?,
                        progress=?,
                        keterangan=?
                    WHERE id=?
                    """,
                    (status, progress, keterangan, edit_id)
                )
                
                if "edit_id" in st.session_state:
                    del st.session_state.edit_id
                
                st.success("Berhasil diupdate")
                st.rerun()

        with colB:
            if st.button("Batal", key="cancel_edit"):
                del st.session_state.edit_id
                st.rerun()

