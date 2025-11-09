# app.py
import io
import os
import re
import csv
import zipfile
from collections import Counter

import pandas as pd
import streamlit as st


# -------------------- 유틸 함수 --------------------
INVALID_FILENAME_CHARS = r'[^A-Za-z0-9가-힣 _\-\.\(\)\[\]]'

def sanitize_filename(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(INVALID_FILENAME_CHARS, '_', name)
    if not name:
        name = "untitled"
    return name

def ensure_txt_suffix(name: str) -> str:
    return name if name.lower().endswith(".txt") else f"{name}.txt"

def safe_read_csv(file, encoding_choice: str | None, sep_choice: str | None) -> pd.DataFrame:
    if encoding_choice == "자동 감지(우선 utf-8, 실패 시 latin1)":
        tried = []
        for enc in ("utf-8", "cp949", "euc-kr", "latin1"):
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, sep=sep_choice or None)
                return df
            except Exception as e:
                tried.append((enc, str(e)))
        raise RuntimeError("CSV를 읽는 데 실패했습니다. 시도한 인코딩: " + ", ".join(enc for enc, _ in tried))
    else:
        file.seek(0)
        return pd.read_csv(file, encoding=encoding_choice, sep=sep_choice or None)

def sniff_delimiter(sample_bytes: bytes) -> str | None:
    try:
        sample = sample_bytes.decode("utf-8", errors="ignore")
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        return None

def first_nonempty_str(series_like) -> str | None:
    for val in series_like:
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


# -------------------- 앱 UI --------------------
st.set_page_config(page_title="CSV → TXT 변환기", page_icon="✅", layout="centered")
st.title("CSV → TXT 변환기")
st.caption("CSV 각 행에서 텍스트를 추출해 개별 .txt 파일로 만들어 ZIP으로 내려받습니다.")

uploaded = st.file_uploader("CSV 파일을 업로드하세요", type=["csv"])

with st.expander("고급 설정", expanded=False):
    delimiter_auto = None
    if uploaded is not None:
        uploaded.seek(0)
        delimiter_auto = sniff_delimiter(uploaded.read(20_000))
    sep_choice = st.selectbox(
        "구분자",
        options=[delimiter_auto or "자동 판별 실패(기본 , 사용)", ",", ";", "\\t", "|"],
        index=0
    )
    if sep_choice == "자동 판별 실패(기본 , 사용)":
        selected_sep = None
    elif sep_choice == "\\t":
        selected_sep = "\t"
    else:
        selected_sep = sep_choice

    encoding_choice = st.selectbox(
        "인코딩",
        options=[
            "자동 감지(우선 utf-8, 실패 시 latin1)",
            "utf-8",
            "cp949",
            "euc-kr",
            "latin1",
        ],
        index=0
    )

    default_prefix = ""
    default_suffix = ""
    col_a, col_b = st.columns(2)
    with col_a:
        prefix = st.text_input("파일명 앞에 붙일 텍스트(선택)", value=default_prefix)
    with col_b:
        suffix = st.text_input("파일명 뒤에 붙일 텍스트(선택)", value=default_suffix)

if uploaded is None:
    st.info("상단에서 CSV 파일을 먼저 업로드하세요.")
    st.stop()

# -------------------- CSV 읽기 --------------------
try:
    df = safe_read_csv(uploaded, encoding_choice, selected_sep)
except Exception as e:
    st.error(f"CSV 파일을 읽는 중 오류가 발생했습니다:\n\n{e}")
    st.stop()

if df.empty:
    st.warning("CSV에 내용이 없습니다.")
    st.stop()

st.subheader("미리보기")
st.dataframe(df.head(20), use_container_width=True)

# -------------------- 컬럼 선택 --------------------
st.subheader("옵션 선택")

filename_col = None
candidate_filename_cols = [c for c in df.columns if c.lower() == "filename"] or list(df.columns)
filename_col = st.selectbox("파일명으로 사용할 컬럼(없으면 행 번호 사용)", options=["(없음)"] + candidate_filename_cols)

text_mode = st.radio(
    "텍스트 추출 방법을 선택하세요",
    options=[
        "특정 컬럼에서 추출",
        "각 행에서 첫 번째 비어있지 않은 문자열 찾기(원본 코드와 유사)",
    ],
    index=1
)

text_col = None
if text_mode == "특정 컬럼에서 추출":
    text_col = st.selectbox("텍스트 컬럼 선택", options=list(df.columns))

# -------------------- 변환 실행 --------------------
run = st.button("TXT 파일 생성하기")

if run:
    # 생성된 파일명을 중복 없이 보장
    used_names = Counter()
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, row in df.iterrows():
            # 텍스트 값 결정
            if text_mode == "특정 컬럼에서 추출":
                val = row.get(text_col, None)
                text_value = val if isinstance(val, str) and val.strip() else None
            else:
                text_value = first_nonempty_str(row.values)

            if not text_value:
                continue

            # 파일명 결정
            if filename_col != "(없음)":
                raw_name = str(row.get(filename_col, "")).strip()
                fname = sanitize_filename(raw_name) or f"row_{i+1}"
            else:
                fname = f"row_{i+1}"

            fname = prefix + fname + suffix
            fname = ensure_txt_suffix(fname)

            # 중복 처리
            base, ext = os.path.splitext(fname)
            used_names[base] += 1
            if used_names[base] > 1:
                fname = f"{base}_{used_names[base]}{ext}"

            zf.writestr(fname, text_value)

    mem_zip.seek(0)
    st.success(f"변환 완료! 총 {len(df)}개 행을 처리했고, 텍스트가 있는 행만 ZIP에 포함했습니다.")
    st.download_button(
        label="ZIP 파일 다운로드",
        data=mem_zip,
        file_name="texts_from_csv.zip",
        mime="application/zip",
        use_container_width=True
    )

st.caption("파일명 컬럼과 텍스트 컬럼을 지정하지 않으면, 각 행에서 가장 먼저 발견되는 비어있지 않은 문자열을 사용해 원본 동작과 유사하게 처리합니다.")
