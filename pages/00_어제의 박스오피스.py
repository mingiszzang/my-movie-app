# main.py
# KOBIS 일별 박스오피스 API를 이용한 "어제의 박스오피스" 대시보드

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 어제의 박스오피스")
st.caption("영화진흥위원회 KOBIS 일별 박스오피스 데이터를 이용합니다.")


# ---------------------------------------------------------
# 2. 한국 시간 기준으로 어제 날짜 계산
# ---------------------------------------------------------
# Streamlit Cloud 서버가 외국 시간대를 사용하더라도
# 반드시 한국 시간(Asia/Seoul)을 기준으로 계산합니다.
korea_now = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday = korea_now.date() - timedelta(days=1)

# API 요청에는 YYYYMMDD 형식이 필요합니다.
target_dt = yesterday.strftime("%Y%m%d")

# 화면 표시용 날짜입니다.
display_date = yesterday.strftime("%Y년 %m월 %d일")


# ---------------------------------------------------------
# 3. KOBIS API 데이터 가져오기
# ---------------------------------------------------------
@st.cache_data(ttl=1800)
def load_boxoffice_data(api_key: str, target_date: str) -> pd.DataFrame:
    """
    KOBIS 일별 박스오피스 데이터를 가져와
    판다스 데이터프레임으로 반환합니다.

    ttl=1800은 데이터를 30분 동안 캐시한다는 뜻입니다.
    """

    api_url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_date,
    }

    try:
        # 응답이 지나치게 오래 걸리지 않도록 제한 시간을 설정합니다.
        response = requests.get(api_url, params=params, timeout=60)

        # 400, 500 등의 HTTP 오류가 발생하면 예외를 발생시킵니다.
        response.raise_for_status()

        data = response.json()

    except requests.exceptions.Timeout as error:
        raise RuntimeError(
            "KOBIS 서버의 응답 시간이 너무 오래 걸리고 있습니다. "
            "잠시 후 다시 시도해 주세요."
        ) from error

    except requests.exceptions.ConnectionError as error:
        raise RuntimeError(
            "KOBIS 서버에 연결할 수 없습니다. "
            "인터넷 연결 또는 KOBIS 서버 상태를 확인해 주세요."
        ) from error

    except requests.exceptions.HTTPError as error:
        raise RuntimeError(
            f"KOBIS API 요청 중 HTTP 오류가 발생했습니다. "
            f"상태 코드: {response.status_code}"
        ) from error

    except requests.exceptions.JSONDecodeError as error:
        raise RuntimeError(
            "KOBIS 서버의 응답을 읽을 수 없습니다. "
            "잠시 후 다시 시도해 주세요."
        ) from error

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            "KOBIS API 요청 중 네트워크 오류가 발생했습니다."
        ) from error

    # 인증키 오류 등 KOBIS가 faultInfo를 반환한 경우입니다.
    if "faultInfo" in data:
        fault_info = data.get("faultInfo", {})
        message = fault_info.get(
            "message",
            "인증키 또는 API 요청 정보를 확인해 주세요.",
        )

        raise RuntimeError(f"KOBIS API 오류: {message}")

    # 정상 응답에서 영화 목록을 가져옵니다.
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError) as error:
        raise RuntimeError(
            "KOBIS 응답에서 박스오피스 데이터를 찾을 수 없습니다."
        ) from error

    if not movie_list:
        raise RuntimeError(
            "해당 날짜의 박스오피스 데이터가 아직 제공되지 않았습니다."
        )

    df = pd.DataFrame(movie_list)

    # API의 숫자는 문자열로 전달되므로 숫자형으로 변환합니다.
    numeric_columns = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
        "showCnt",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            ).fillna(0).astype(int)

    # 순위 숫자를 기준으로 다시 정렬합니다.
    df = df.sort_values("rank").reset_index(drop=True)

    return df


# ---------------------------------------------------------
# 4. Streamlit secrets에서 인증키 불러오기
# ---------------------------------------------------------
try:
    kobis_key = st.secrets["KOBIS_KEY"]

except KeyError:
    st.error(
        "KOBIS 인증키가 설정되지 않았습니다.\n\n"
        "Streamlit Cloud의 **Settings → Secrets**에 다음과 같이 입력해 주세요.\n\n"
        '```toml\nKOBIS_KEY = "발급받은_인증키"\n```'
    )
    st.stop()


# ---------------------------------------------------------
# 5. 데이터 불러오기
# ---------------------------------------------------------
with st.spinner(f"{display_date} 박스오피스 데이터를 불러오는 중입니다..."):
    try:
        df = load_boxoffice_data(kobis_key, target_dt)

    except RuntimeError as error:
        st.error(str(error))
        st.info(
            "인증키가 정확한지, KOBIS 서비스가 정상적으로 운영 중인지 "
            "확인한 후 다시 시도해 주세요."
        )
        st.stop()


st.subheader(f"📅 {display_date} 박스오피스")


# ---------------------------------------------------------
# 6. 순위 변동 표시 만들기
# ---------------------------------------------------------
def make_rank_display(row):

    rank = int(row["rank"])
    inten = int(row["rankInten"])

    if inten > 0:
        mark = f"🔺 {inten}"

    elif inten < 0:
        mark = f"🔻 {abs(inten)}"

    else:
        mark = "➖"

    return f"{rank}위   {mark}"


def make_movie_name(row) -> str:
    """
    누적 관객수가 100만 명 이상이면
    영화명 옆에 트로피를 표시합니다.
    """

    movie_name = row["movieNm"]

    if row["audiAcc"] >= 1_000_000:
        return f"{movie_name} 🏆"

    return movie_name


df["순위"] = df.apply(make_rank_display, axis=1)
df["영화명"] = df.apply(make_movie_name, axis=1)


# ---------------------------------------------------------
# 7. 1위 영화 지표 카드
# ---------------------------------------------------------
first_movie = df.iloc[0]

st.markdown("### 🥇 박스오피스 1위")

# 1위 영화명은 한 줄 전체를 사용합니다.
if first_movie["rankInten"] > 0:
    rank_delta = f"순위 {first_movie['rankInten']}계단 상승"
elif first_movie["rankInten"] < 0:
    rank_delta = f"순위 {abs(first_movie['rankInten'])}계단 하락"
else:
    rank_delta = "순위 변동 없음"

st.metric(
    label="1위 영화",
    value=first_movie["영화명"],
    delta=rank_delta,
    delta_color="normal" if first_movie["rankInten"] >= 0 else "inverse",
)

# 숫자 지표는 아래쪽 3개 열에 넓게 배치합니다.
metric_col1, metric_col2, metric_col3 = st.columns(3)

with metric_col1:
    st.metric(
        label="어제 관객수",
        value=f"{first_movie['audiCnt']:,}명",
    )

with metric_col2:
    st.metric(
        label="누적 관객수",
        value=f"{first_movie['audiAcc']:,}명",
    )

with metric_col3:
    st.metric(
        label="스크린수",
        value=f"{first_movie['scrnCnt']:,}개",
    )


# ---------------------------------------------------------
# 8. 관객수 상위 5편 막대그래프
# ---------------------------------------------------------
import plotly.express as px

st.markdown("### 📊 관객수 상위 5편")

# 관객수 기준 상위 5편
top5 = (
    df.nlargest(5, "audiCnt")
    .sort_values("audiCnt", ascending=False)
)

fig = px.bar(
    top5,
    x="audiCnt",
    y="movieNm",
    orientation="h",
    text="audiCnt",
)

# 1위가 위에 오도록
fig.update_yaxes(autorange="reversed")

# 숫자를 천 단위 콤마로 표시
fig.update_traces(
    texttemplate="%{text:,}",
    textposition="outside",
)

fig.update_layout(
    height=420,
    xaxis_title="관객수",
    yaxis_title="",
    margin=dict(l=180, r=40, t=20, b=20),  # ← 긴 영화명 때문에 왼쪽 여백을 크게
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# 9. 전체 순위 표
# ---------------------------------------------------------
st.markdown("### 📋 전체 박스오피스 순위")

table_df = df[
    [
        "순위",
        "영화명",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

table_df = table_df.rename(
    columns={
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수",
    }
)

st.dataframe(
    table_df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "순위": st.column_config.TextColumn(
            "순위",
            width="small",
        ),
        "영화명": st.column_config.TextColumn(
            "영화명",
            width="large",
        ),
        "개봉일": st.column_config.DateColumn(
            "개봉일",
            format="YYYY-MM-DD",
        ),
        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="%d명",
        ),
        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="%d명",
        ),
        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="%d개",
        ),
    },
)

st.caption(
    "🔴 ↑ 순위 상승 · 🔵 ↓ 순위 하락 · "
    "🏆 누적 관객 100만 명 이상"
)

st.divider()
st.caption(
    f"조회 기준일: {display_date} · "
    "출처: 영화진흥위원회 KOBIS 오픈API"
)
