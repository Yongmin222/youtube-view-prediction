"""
YouTube 음식 영상 수집기 v2.0 (강화된 필터링)

YouTube Data API v3로 음식/요리 관련 채널과 영상의 메타데이터(15개 컬럼)를 수집해
BigQuery 테이블(youtube_data2.video_stats_v1)에 저장한다.

실행 전 환경변수 설정:
    export YOUTUBE_API_KEY="발급받은 API 키"
    export GCP_PROJECT_ID="BigQuery를 사용할 GCP 프로젝트 ID"
"""
from google.cloud import bigquery
import requests
from datetime import datetime, timezone
import os
import time
import json

# 설정 (키와 프로젝트 ID는 코드에 직접 쓰지 않고 환경변수에서 읽는다)
API_KEY = os.environ["YOUTUBE_API_KEY"]
PROJECT_ID = os.environ["GCP_PROJECT_ID"]

# 1. 강화된 검색 키워드 (음식 채널 타겟팅)
SEARCH_KEYWORDS = [
    "먹방", "요리", "맛집", "음식",
    "달달", "야식", "디저트", "밥",
    "매운", "ASMR", "푸드"
]

# 2. 채널 필터링 키워드 (채널 이름/설명에 있어야 음식 채널)
CHANNEL_KEYWORDS = [
    "먹방", "음식", "요리", "쿡", "cook", "food", "레시피",
    "맛집", "푸드", "먹는", "kitchen", "baking", "cooking"
]

# 3. 영상 필터링 (강력한 2중 체크)
MUST_INCLUDE_KEYWORDS = [
    "먹방", "먹는", "먹어", "먹을", "요리", "레시피", "recipe",
    "맛집", "맛있", "음식", "mukbang", "eating", "food",
    "쿡방", "cook", "야식", "디저트", "베이킹", "ramen", "라면", "달달", "매운", "달콤"
]

MUST_EXCLUDE_KEYWORDS = [
    "게임", "game", "gaming", "music", "노래", "커버",
    "뉴스", "news", "정치", "주식", "코인", "투자", "영화"
]


def is_food_channel(channel_info):
    """채널이 음식 관련 채널인지 판단"""
    title = channel_info.get("title", "").lower()
    description = channel_info.get("description", "").lower()

    text = f"{title} {description}"
    for keyword in CHANNEL_KEYWORDS:
        if keyword.lower() in text:
            return True
    return False


def video_matches_filter(title, description=""):
    """영상이 음식 관련 영상인지 강력한 2중 필터링"""
    text = f"{title} {description}".lower()

    # 1단계: 필수 키워드 하나 이상 포함?
    has_required = False
    for keyword in MUST_INCLUDE_KEYWORDS:
        if keyword.lower() in text:
            has_required = True
            break

    if not has_required:
        return False

    # 2단계: 제외 키워드 없어야 함
    for keyword in MUST_EXCLUDE_KEYWORDS:
        if keyword.lower() in text:
            return False

    return True


def search_videos_enhanced(keywords, max_results_per_keyword=200):
    """여러 키워드로 검색 + 중복 제거"""
    all_video_ids = set()
    all_channel_ids = set()

    print("🔍 다양한 키워드로 음식 채널 검색 중...")

    for keyword in keywords:
        video_ids, channel_ids = search_videos_single(keyword, max_results=max_results_per_keyword)
        all_video_ids.update(video_ids)
        all_channel_ids.update(channel_ids)

        print(f"  '{keyword}': 영상 {len(video_ids)}개, 채널 {len(channel_ids)}개")
        time.sleep(0.3)

    print(f"\n📊 검색 집계: 영상 {len(all_video_ids)}개, 채널 {len(all_channel_ids)}개")
    return list(all_video_ids), list(all_channel_ids)


def search_videos_single(keyword, max_results=200):
    """단일 키워드 검색 (결과 수 제한)"""
    video_ids = []
    channel_ids = set()
    next_page_token = None
    results_count = 0

    url = "https://www.googleapis.com/youtube/v3/search"

    while results_count < max_results:
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 50,
            "regionCode": "KR",
            "key": API_KEY
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = requests.get(url, params=params)
        data = response.json()

        if "items" not in data:
            break

        for item in data["items"]:
            if results_count >= max_results:
                break
            video_ids.append(item["id"]["videoId"])
            channel_ids.add(item["snippet"]["channelId"])
            results_count += 1

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.5)

    return video_ids[:max_results], list(channel_ids)


def filter_food_channels(channel_ids):
    """음식 채널만 필터링"""
    food_channels = []

    print(f"\n🍽️ 음식 채널 필터링 중... ({len(channel_ids)}개)")

    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        ids_string = ",".join(batch)

        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "snippet,statistics",
            "id": ids_string,
            "key": API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        for item in data.get("items", []):
            if is_food_channel(item["snippet"]):
                food_channels.append({
                    "channel_id": item["id"],
                    "channel_title": item["snippet"]["title"],
                    "subscriber_count": int(item["statistics"].get("subscriberCount", 0))
                })

        time.sleep(0.3)

    print(f"✅ 음식 채널 선별 완료: {len(food_channels)}개")
    return food_channels


def get_channel_videos_efficient(channel_id):
    """채널의 최근 영상을 채널당 최대 600개까지만 가져오기 (API 할당량 절약)"""
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "contentDetails", "id": channel_id, "key": API_KEY}

    response = requests.get(url, params=params)
    data = response.json()

    if not data.get("items"):
        return []

    uploads_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids = []
    next_page_token = None

    # 채널당 최대 600개 (API 절약)
    max_videos = 600

    while len(video_ids) < max_videos:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_id,
            "maxResults": 50,
            "key": API_KEY
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params)
        data = response.json()

        if "items" not in data:
            break

        for item in data["items"]:
            if len(video_ids) >= max_videos:
                break
            video_ids.append(item["contentDetails"]["videoId"])

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


def parse_duration(duration_str):
    """ISO 8601 duration을 초 단위로 변환"""
    if not duration_str:
        return 0

    duration_str = duration_str.replace("PT", "")
    hours = 0
    minutes = 0
    seconds = 0

    if "H" in duration_str:
        hours, duration_str = duration_str.split("H")
        hours = int(hours)

    if "M" in duration_str:
        parts = duration_str.split("M")
        minutes = int(parts[0])
        duration_str = parts[1] if len(parts) > 1 else ""

    if "S" in duration_str:
        seconds = int(duration_str.replace("S", ""))

    return hours * 3600 + minutes * 60 + seconds


def get_video_details_filtered(video_ids, food_channels):
    """강력한 필터링으로 음식 영상만 수집"""
    channel_lookup = {ch["channel_id"]: ch for ch in food_channels}
    all_results = []

    print(f"\n🎥 음식 영상 상세 정보 수집 중... ({len(video_ids)}개)")

    filtered_count = 0
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        ids_string = ",".join(batch)

        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ids_string,
            "key": API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        for item in data.get("items", []):
            title = item["snippet"]["title"]
            description = item["snippet"].get("description", "")

            # 강력한 2중 필터링
            if not video_matches_filter(title, description):
                filtered_count += 1
                continue

            channel_id = item["snippet"]["channelId"]
            channel_info = channel_lookup.get(channel_id, {})

            duration_str = item["contentDetails"].get("duration", "")
            duration_seconds = parse_duration(duration_str)

            video_info = {
                "video_id": item["id"],
                "title": title,
                "description": description[:500],
                "channel_id": channel_id,
                "channel_title": item["snippet"].get("channelTitle", ""),
                "category_id": item["snippet"].get("categoryId", ""),
                "tags": json.dumps(item["snippet"].get("tags", []), ensure_ascii=False),
                "duration": duration_str,
                "duration_seconds": duration_seconds,
                "view_count": int(item["statistics"].get("viewCount", 0)),
                "like_count": int(item["statistics"].get("likeCount", 0)),
                "comment_count": int(item["statistics"].get("commentCount", 0)),
                # 음식 채널 필터를 통과하지 못한 채널의 영상은 구독자 수가 0으로 저장된다
                "subscriber_count": channel_info.get("subscriber_count", 0),
                "published_at": item["snippet"]["publishedAt"],
                "collected_at": datetime.now(timezone.utc).isoformat()
            }
            all_results.append(video_info)

        if (i // 50) % 10 == 0:
            print(f"  수집: {len(all_results)}개 (필터링: {filtered_count}개)")

        time.sleep(0.3)

    print(f"✅ 최종 음식 영상: {len(all_results)}개 (제외: {filtered_count}개)")
    return all_results


def save_to_bigquery(video_data):
    """BigQuery 저장 (중복 체크 포함)"""
    if not video_data:
        return 0

    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"{PROJECT_ID}.youtube_data2.video_stats_v1"

    # 중복 제거 (video_id 기준)
    unique_videos = {v["video_id"]: v for v in video_data}.values()
    video_data = list(unique_videos)

    print(f"\n💾 BigQuery 저장 중... ({len(video_data)}개 중복 제거 후)")

    total_saved = 0
    batch_size = 1000

    for i in range(0, len(video_data), batch_size):
        batch = video_data[i:i+batch_size]
        rows_to_insert = [dict(video) for video in batch]

        errors = client.insert_rows_json(table_id, rows_to_insert)

        if errors:
            print(f"  배치 {i//batch_size + 1} 에러: {len(errors)}개")
        else:
            total_saved += len(rows_to_insert)
            print(f"  저장: {total_saved}/{len(video_data)}")

        time.sleep(0.5)

    return total_saved


if __name__ == "__main__":
    print("=" * 60)
    print("🍽️ YouTube 음식 영상 수집기 v2.0 (강화된 필터링)")
    print(f"검색 키워드: {len(SEARCH_KEYWORDS)}개")
    print("=" * 60)

    # 1단계: 다양한 키워드로 검색
    initial_video_ids, all_channel_ids = search_videos_enhanced(SEARCH_KEYWORDS)

    # 2단계: 음식 채널만 선별
    food_channels = filter_food_channels(all_channel_ids)

    # 3단계: 음식 채널의 영상 수집 (채널당 최대 600개)
    all_food_video_ids = set(initial_video_ids)
    print(f"\n📺 음식 채널 영상 수집 중... ({len(food_channels)}개 채널)")

    for idx, channel in enumerate(food_channels):
        video_ids = get_channel_videos_efficient(channel["channel_id"])
        before = len(all_food_video_ids)
        all_food_video_ids.update(video_ids)
        added = len(all_food_video_ids) - before

        print(f"[{idx+1}/{len(food_channels)}] {channel['channel_title'][:25]}: "
              f"{len(video_ids)}개 (신규 +{added}) | 구독자 {channel['subscriber_count']:,}")
        time.sleep(0.3)

    print(f"\n📊 총 음식 영상 ID: {len(all_food_video_ids):,}")

    # 4단계: 강력한 필터링으로 최종 음식 영상 선별
    final_video_data = get_video_details_filtered(list(all_food_video_ids), food_channels)

    # 5단계: BigQuery 저장 (중복 제거)
    saved_count = save_to_bigquery(final_video_data)

    print("\n" + "=" * 60)
    print("🎉 수집 완료")
    print(f"   음식 채널: {len(food_channels)}개")
    print(f"   최종 영상: {len(final_video_data):,}개")
    print(f"   BigQuery 저장: {saved_count:,}개")
    print("=" * 60)
