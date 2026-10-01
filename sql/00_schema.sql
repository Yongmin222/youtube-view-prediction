-- 수집 테이블 스키마 (프로젝트 보고서 2.2의 15개 컬럼을 DDL로 옮긴 것)
-- 사용 전: 기본 프로젝트를 본인의 GCP 프로젝트로 지정하거나, 아래 테이블명 앞에 프로젝트 ID를 붙여서 실행
CREATE SCHEMA IF NOT EXISTS youtube_data2;

CREATE TABLE IF NOT EXISTS youtube_data2.video_stats_v1 (
  video_id         STRING    OPTIONS(description='영상 고유 식별자'),
  title            STRING    OPTIONS(description='영상 제목'),
  description      STRING    OPTIONS(description='영상 설명 (최대 500자)'),
  channel_id       STRING    OPTIONS(description='채널 고유 식별자'),
  channel_title    STRING    OPTIONS(description='채널명'),
  category_id      STRING    OPTIONS(description='YouTube 카테고리 ID'),
  tags             STRING    OPTIONS(description='영상 태그 (JSON 배열 문자열)'),
  duration         STRING    OPTIONS(description='영상 길이 (ISO 8601 형식)'),
  duration_seconds INT64     OPTIONS(description='영상 길이 (초 단위 변환)'),
  view_count       INT64     OPTIONS(description='조회수 (예측 타겟)'),
  like_count       INT64     OPTIONS(description='좋아요 수'),
  comment_count    INT64     OPTIONS(description='댓글 수'),
  subscriber_count INT64     OPTIONS(description='채널 구독자 수'),
  published_at     TIMESTAMP OPTIONS(description='영상 업로드 일시'),
  collected_at     TIMESTAMP OPTIONS(description='데이터 수집 일시')
);
