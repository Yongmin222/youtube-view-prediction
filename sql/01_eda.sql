-- 탐색적 데이터 분석(EDA) 쿼리 (프로젝트 보고서 3장에 수록된 쿼리)

-- 3.1 데이터 품질 확인 (결과: 68,497건, 결측치 0, 중복 0)
SELECT
  COUNT(*) as total_rows,
  COUNTIF(view_count IS NULL) as null_views,
  COUNTIF(title IS NULL) as null_titles,
  COUNT(DISTINCT video_id) as unique_videos
FROM youtube_data2.video_stats_v1;

-- 3.2 조회수 분포 분석 (결과: 중앙값 42,431회 vs 평균 815,539회, 약 20배 차이 -> 롱테일 분포)
SELECT
  COUNTIF(view_count <= 1000) as views_under_1k,
  COUNTIF(view_count > 1000 AND view_count <= 10000) as views_1k_10k,
  COUNTIF(view_count > 10000 AND view_count <= 100000) as views_10k_100k,
  COUNTIF(view_count > 100000 AND view_count <= 1000000) as views_100k_1m,
  COUNTIF(view_count > 1000000) as views_over_1m,
  APPROX_QUANTILES(view_count, 100)[OFFSET(50)] as median_views
FROM youtube_data2.video_stats_v1;

-- 3.3 시간대별 조회수 패턴 (결과: 토요일 새벽~아침 업로드의 중앙값이 가장 높음)
SELECT
  EXTRACT(DAYOFWEEK FROM published_at) as day_of_week,
  EXTRACT(HOUR FROM published_at) as hour,
  AVG(view_count) as avg_views,
  APPROX_QUANTILES(view_count, 100)[OFFSET(50)] as median_views
FROM youtube_data2.video_stats_v1
GROUP BY 1, 2
ORDER BY median_views DESC;
