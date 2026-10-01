-- ============================================================================
-- Feature Engineering: 전처리 테이블 생성 (복원본)
--
-- [안내] 이 프로젝트를 진행한 교육용 GCP 계정이 종료되어 원본 SQL 전문은 남아 있지 않습니다.
-- 이 파일은 프로젝트 보고서 4.2의 Feature 표(변환 수식)와 4.3에 수록된 SQL을 바탕으로
-- 다시 작성한 것이며, 보고서에 수식이 적혀 있지 않은 has_special_chars(특수문자 비율 10% 이상 여부)는
-- 포함하지 않았습니다. 따라서 보고서의 17개 Feature 중 16개를 담고 있습니다.
-- ============================================================================
CREATE OR REPLACE TABLE youtube_data2.video_stats_processed_v2 AS
WITH channel_stats AS (
  -- 채널별 평균 조회수와 영상 수 집계
  SELECT
    channel_id,
    AVG(view_count) as channel_avg_views,
    COUNT(*) as channel_video_count
  FROM youtube_data2.video_stats_v1
  GROUP BY channel_id
)
SELECT
  v.video_id,

  -- 타겟 (로그 변환으로 극단값 영향 완화)
  LOG(v.view_count + 1) as log_view_count,

  -- 채널 정보
  LOG(v.subscriber_count + 1) as log_subscribers,
  LOG(c.channel_avg_views + 1) as log_channel_avg_views,
  c.channel_video_count,

  -- 시간 정보
  EXTRACT(DAYOFWEEK FROM v.published_at) as day_of_week,
  EXTRACT(HOUR FROM v.published_at) as hour,
  EXTRACT(MONTH FROM v.published_at) as month,

  -- 제목 분석
  LENGTH(v.title) as title_length,
  REGEXP_CONTAINS(v.title, r'(?i)먹방|mukbang') as has_mukbang,
  REGEXP_CONTAINS(v.title, r'(?i)레시피|recipe') as has_recipe,
  REGEXP_CONTAINS(v.title, r'(?i)리뷰|review') as has_review,
  REGEXP_CONTAINS(v.title, r'(?i)asmr') as has_asmr,
  REGEXP_CONTAINS(v.title, r'(?i)vlog|브이로그') as has_vlog,
  REGEXP_CONTAINS(v.title, r'[!?]{2,}') as has_multiple_punct,

  -- 콘텐츠 정보
  v.duration_seconds,
  ARRAY_LENGTH(SPLIT(v.tags, ',')) as tag_count,
  v.category_id
FROM youtube_data2.video_stats_v1 v
LEFT JOIN channel_stats c ON v.channel_id = c.channel_id
WHERE v.view_count > 0
  AND v.subscriber_count IS NOT NULL;
