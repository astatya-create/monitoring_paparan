from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Editor Link OneDrive", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "monitoring.db"

st.title("Editor Link OneDrive untuk Dashboard Bahan Paparan")
st.caption("Gunakan tool ini untuk mengubah file_surat, file_paparan, dan file_narasi menjadi link OneDrive langsung di database lokal.")

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(ttl=2)
def load_bahan() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                nama_bahan,
                file_surat,
                file_paparan,
                file_narasi,
                status,
                progress,
                deadline
            FROM bahan
            ORDER BY id
            """,
            conn,
        )
    return df

def update_links(bahan_id: int, surat: str, paparan: str, narasi: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE bahan
            SET file_surat = ?, file_paparan = ?, file_narasi = ?
            WHERE id = ?
            """,
            (surat.strip(), paparan.strip(), narasi.strip(), bahan_id),
        )
        conn.commit()
    load_bahan.clear()

if not DB_PATH.exists():
    st.error(f"Database tidak ditemukan: {DB_PATH}")
    st.stop()

df = load_bahan()

if df.empty:
    st.info("Belum ada data bahan di database.")
    st.stop()

keyword = st.text_input("Cari nama bahan", placeholder="mis. Rakor KSP / RDP DPR")
filtered = df.copy()
if keyword.strip():
    key = keyword.strip().lower()
    filtered = filtered[filtered["nama_bahan"].fillna("").str.lower().str.contains(key)]

st.subheader("Daftar bahan")
st.dataframe(filtered, use_container_width=True, hide_index=True)

options = [f"{row.id} — {row.nama_bahan}" for row in filtered.itertuples(index=False)]
selected = st.selectbox("Pilih bahan yang akan diubah link-nya", options)

selected_id = int(selected.split(" — ", 1)[0])
row = df[df["id"] == selected_id].iloc[0]

st.subheader("Edit link")
st.write(f"**ID:** {selected_id}")
st.write(f"**Nama bahan:** {row['nama_bahan']}")

with st.form("form_edit_links"):
    file_surat = st.text_input("Link OneDrive Disposisi", value="" if pd.isna(row["file_surat"]) else str(row["file_surat"]))
    file_paparan = st.text_input("Link OneDrive Paparan", value="" if pd.isna(row["file_paparan"]) else str(row["file_paparan"]))
    file_narasi = st.text_input("Link OneDrive Narasi", value="" if pd.isna(row["file_narasi"]) else str(row["file_narasi"]))

    submitted = st.form_submit_button("Simpan Link", use_container_width=True)

if submitted:
    update_links(selected_id, file_surat, file_paparan, file_narasi)
    st.success("Link berhasil diperbarui di monitoring.db")
    st.rerun()

st.markdown("---")
st.subheader("Cek cepat data saat ini")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption("file_surat")
    st.code("" if pd.isna(row["file_surat"]) else str(row["file_surat"]), language=None)
with col2:
    st.caption("file_paparan")
    st.code("" if pd.isna(row["file_paparan"]) else str(row["file_paparan"]), language=None)
with col3:
    st.caption("file_narasi")
    st.code("" if pd.isna(row["file_narasi"]) else str(row["file_narasi"]), language=None)
