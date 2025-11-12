import io
import os
import re
import zipfile
from typing import Optional

import pandas as pd
import streamlit as st


st.set_page_config(page_title="CSV → TXT 변환기", page_icon="🗂️", layout="centered")

st.title("CSV → TXT 변환기")
st.write("CSV를 업로드하면 각 행의 텍스트를 개별 `.txt` 파일로 만들어 ZIP으로 다운로드할 수 있습니다.")
st.caption("원본 동작 유지: 각 행에서 **첫 번째 문자열형 셀**을 텍스트로 사용하며, `filename` 컬럼이 있으면 파일명으로 사용합니다.")

uploaded = st.file_uploader("CSV 파일을 업로드하세요", type=["csv"])

def read_csv_safely(file) -> Optional[pd.DataFrame]:
    # 원본과 동일한 인코딩 시도: utf-8 → latin1
    try:
        try:
            return pd.read_csv(file, encoding="utf-8")
        except UnicodeDecodeError:
            file.seek(0)
            return pd.read_csv(file, encoding="latin1")
    except Exception as e:
        st.error(f"CSV 파일을 읽는 중 오류가 발생했습니다:\n{e}")
        return None

def sanitize_filename(name: str) -> str:
    # 파일명에서 위험/부적절 문자 제거
    name = str(name)
    name = name.strip()
    # 경로 구분자, 제어문자 제거
    name = re.sub(r"[\\/:\*\?\"<>\|\r\n\t]", "_", name)
    # 공백 압축
    name = re.sub(r"\s+", " ", name)
    # 빈 값 보호
    return name if name else "untitled"

def first_string_cell(row) -> Optional[str]:
    for val in row:
        if isinstance(val, str) and val.strip():
            return val
    return None

def ensure_unique(name: str, used: set) -> str:
    base, ext = os.path.splitext(name)
    if name not in used:
        used.add(name)
        return name
    i = 2
    while True:
        candidate = f"{base}_{i}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        i += 1

if uploaded is not None:
    df = read_csv_safely(uploaded)

    if df is not None:
        st.success("CSV 파일을 정상적으로 불러왔습니다.")
        st.write(f"열(컬럼) 수: **{len(df.columns)}**, 행 수: **{len(df)}**")

        # filename 컬럼 존재 여부 확인(대소문자 무시)
        filename_col = None
        for col in df.columns:
            if str(col).lower() == "filename":
                filename_col = col
                break

        if st.button("변환 시작"):
            # ZIP을 메모리에서 생성
            buffer = io.BytesIO()
            used_names = set()
            created = 0
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for i, row in df.iterrows():
                    text_value = first_string_cell(row)
                    if text_value is None:
                        continue

                    if filename_col:
                        raw_name = f"{row[filename_col]}.txt"
                    else:
                        raw_name = f"row_{i+1}.txt"

                    file_name = sanitize_filename(raw_name)
                    file_name = ensure_unique(file_name, used_names)

                    zf.writestr(file_name, text_value)
                    created += 1

            buffer.seek(0)

            st.success(f"✅ 변환 완료! 원본과 동일하게 총 {len(df)}개의 행을 처리했으며, 실제 텍스트 파일 {created}개가 생성되었습니다.")
            st.download_button(
                label="ZIP 다운로드",
                data=buffer,
                file_name="converted_texts.zip",
                mime="application/zip",
            )

            if created == 0:
                st.info("모든 행에서 문자열형 텍스트를 찾지 못했습니다. CSV 내에 문자열 데이터가 있는지 확인해 주세요.")
        else:
            st.info("아래 버튼을 눌러 변환을 시작하세요.")
else:
    st.write("좌측 또는 위의 업로드 영역에서 CSV 파일을 선택해 주세요.")
