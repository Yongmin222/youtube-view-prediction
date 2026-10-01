# YouTube 영상 조회수 예측 모델 (GCP)

> 채널 특성과 메타데이터 기반 End-to-End ML 파이프라인
> Google Cloud × 천안과학산업진흥원 Google Cloud 엔지니어 양성과정 **최종 프로젝트** (2025.12.08 ~ 2025.12.26)

YouTube 크리에이터가 영상을 올리기 **전에** 알 수 있는 정보만으로 조회수를 예측합니다.
YouTube Data API로 데이터를 수집하고, BigQuery에서 분석·전처리한 뒤, BigQuery ML과 Vertex AI AutoML로 모델을 만들어 Vertex AI Endpoint(REST API)로 배포했습니다.

| 항목 | 결과 |
|---|---|
| 수집 데이터 | 음식/요리 영상 68,497개, 15개 컬럼 |
| Feature Engineering | 17개 Feature 생성 |
| 모델 성능 | R² 0.28 → 0.80 (186% 향상) |
| 문제 해결 | Data Leakage 발견 및 해결 (R² 0.95 → 0.74) |
| 배포 | Vertex AI Endpoint API 서비스화 |

> **참고**: 이 프로젝트는 교육과정에서 제공한 GCP 계정으로 진행했고, 계정이 종료되어 BigQuery 테이블과 Vertex AI 모델은 삭제되었습니다.
> 그래서 이 저장소는 **수집 코드, SQL, 결과 기록**을 보관합니다. 상세 보고서 원본은 [`docs/project-report.pdf`](./docs/project-report.pdf)에 있습니다.

---

## 파이프라인

```
YouTube API → BigQuery 저장 → EDA → Feature Engineering → 모델 학습 → Vertex AI 배포
```

| 단계 | 사용 기술 |
|---|---|
| 데이터 수집 | Python, YouTube Data API v3 |
| 데이터 저장 | Google BigQuery |
| 데이터 분석 | BigQuery SQL, EDA |
| 머신러닝 | BigQuery ML (Linear Regression, Boosted Tree), Vertex AI AutoML |
| 모델 배포 | Vertex AI Endpoint (REST API) |

## 1차 시도에서 최종 결과까지

처음 만든 파이프라인(1차)은 데이터가 17,073건이었고 수집 컬럼이 5개(video_id, 제목, 조회수, 업로드 일시, 수집 일시)뿐이었습니다.
결과는 **R² 0.001**로, 모델이 거의 설명력이 없었습니다. 실패 원인을 직접 정리했습니다.

| 1차의 문제 | 2차(최종)에서 한 것 |
|---|---|
| 피처 부족 (구독자 수, 태그 등 없음) | API 컬럼을 5개 → 15개로 확장 (구독자 수, 영상 길이, 태그, 카테고리 등) |
| 이상치 미처리 (조회수 3.2억 영상이 학습을 왜곡) | 로그 변환 적용 |
| 데이터 양 부족 (17,073건) | 68,497건으로 확대 |

## 데이터 수집

음식/요리 관련 채널과 영상의 메타데이터를 수집합니다. (코드: [`collector/youtube_food_collector.py`](./collector/youtube_food_collector.py))

```
11개 키워드로 영상 검색 → 채널 ID 수집
        ↓
채널 이름/설명에 음식 키워드가 있는 채널만 선별
        ↓
선별된 채널의 최근 영상을 채널당 최대 600개 수집
        ↓
영상 제목·설명 기준 2중 필터 (포함 키워드 1개 이상 + 제외 키워드 없음)
        ↓
video_id 기준 중복 제거 후 BigQuery 저장
```

수집 컬럼 15개 (스키마 DDL: [`sql/00_schema.sql`](./sql/00_schema.sql))

| 구분 | 컬럼 |
|---|---|
| 영상 | video_id, title, description, category_id, tags, duration, duration_seconds, published_at, collected_at |
| 채널 | channel_id, channel_title, subscriber_count |
| 반응 | **view_count (예측 타겟)**, like_count, comment_count |

## EDA에서 발견한 것

쿼리: [`sql/01_eda.sql`](./sql/01_eda.sql)

**1. 조회수는 극단적인 롱테일 분포입니다.** 중앙값 42,431회, 평균 815,539회로 약 20배 차이가 났고, 최댓값은 12억 6천만 회였습니다.
→ 극단값이 모델 학습을 왜곡하므로 **로그 변환**을 하기로 결정했습니다.

| 조회수 구간 | 영상 수 | 비율 |
|---|---|---|
| 0 ~ 1천 | 4,484 | 6.5% |
| 1천 ~ 1만 | 14,578 | 21.3% |
| 1만 ~ 10만 | 24,355 | 35.5% |
| 10만 ~ 100만 | 19,628 | 28.6% |
| 100만 이상 | 5,452 | 8.0% |

**2. 채널 규모가 조회수를 압도합니다.**

| 채널 평균 조회수 | 영상 수 | 실제 평균 조회수 | 배수 |
|---|---|---|---|
| 1만 미만 | 7,436 | 4,341회 | 1x |
| 1만 ~ 10만 | 21,783 | 46,632회 | 11x |
| 10만 ~ 100만 | 33,845 | 348,304회 | 80x |
| 100만 이상 | 5,418 | 7,941,224회 | 1,830x |

→ 채널 평균 조회수(`log_channel_avg_views`)를 핵심 Feature로 추가했습니다.

**3. 시간 패턴.** 토요일 새벽~아침 업로드 영상의 중앙값 조회수가 가장 높았습니다. 평균은 극단값에 흔들려 중앙값 기준으로 판단했고, 요일과 시간을 Feature로 추가했습니다.

## Feature Engineering (17개)

SQL: [`sql/02_feature_engineering.sql`](./sql/02_feature_engineering.sql)
설계 원칙은 세 가지입니다. ① 업로드 **전**에 알 수 있는 정보만 사용, ② 수치형으로 변환, ③ 로그 변환으로 극단값 영향 최소화.

| 카테고리 | Feature |
|---|---|
| 채널 정보 | log_subscribers, log_channel_avg_views, channel_video_count |
| 시간 정보 | day_of_week, hour, month |
| 제목 분석 | title_length, has_mukbang, has_recipe, has_review, has_asmr, has_vlog, has_multiple_punct, has_special_chars |
| 콘텐츠 정보 | duration_seconds, tag_count, category_id |

## Data Leakage 발견과 해결

초기 모델에서 예상보다 높은 **R² 0.95**가 나와 의심했습니다.

1. like_count, comment_count를 포함해서 학습 → R² 0.95
2. "너무 좋은데?" 하고 시간 순서를 검토
3. 좋아요와 댓글은 조회수의 **결과**임을 발견 (영상 업로드 → 시청 → 좋아요 → 댓글 순으로 발생)
4. 두 컬럼을 제외하고 재학습 → R² 0.74

예측 시점에 알 수 없는 정보가 들어가면 실제로는 쓸 수 없는 "가짜 성능"이 나옵니다. 높은 성능이 나와도 실제 사용 시나리오 기준으로 비판적으로 검토해야 한다는 교훈을 얻었습니다.

## 모델링과 성능

| 단계 | 변경 사항 | R² | MAE | 개선율 |
|---|---|---|---|---|
| 베이스라인 | 숫자 컬럼만, 전처리 없음 | 0.28 | - | - |
| 전처리 추가 | 로그 변환 + Feature Engineering | 0.42 | 1.34 | +50% |
| 알고리즘 변경 | Linear → Boosted Tree | 0.74 | 0.92 | +164% |
| AutoML | Vertex AI AutoML 자동 최적화 | 0.80 | 0.79 | +186% |

**Feature 중요도** (BigQuery ML `ML.FEATURE_IMPORTANCE`)

| 순위 | Feature | 중요도 | 해석 |
|---|---|---|---|
| 1 | duration_seconds | 735 | 영상 길이가 조회수에 큰 영향 |
| 2 | log_channel_avg_views | 680 | 채널 평균이 개별 영상 예측의 핵심 |
| 3 | channel_video_count | 500 | 채널 활동량도 중요한 지표 |
| 4 | log_subscribers | 495 | 구독자 수의 영향력 |
| 5 | tag_count | 335 | 태그 개수도 검색 노출에 영향 |

채널 파워(log_channel_avg_views + log_subscribers + channel_video_count)가 전체 중요도의 약 45%, 콘텐츠 특성(duration_seconds, tag_count)이 약 25%, 제목 키워드(has_mukbang, has_recipe 등)가 약 15%였습니다.
**"누가 올리느냐"가 "무슨 내용이냐"보다 조회수에 더 큰 영향을 줍니다.**

## 배포와 시나리오 테스트

학습한 모델을 Vertex AI Endpoint(us-central1)에 배포해 REST API로 실시간 예측이 가능하게 했습니다. 입력은 17개 Feature(JSON), 출력은 로그 스케일의 조회수입니다.

| 시나리오 | 예측 조회수 | 비고 |
|---|---|---|
| 대형 채널(100만 구독) + 먹방 | 121,122회 | 기준 시나리오 |
| 대형 채널(100만 구독) + 레시피 | 121,122회 | 키워드 영향 없음 |
| 대형 채널(100만 구독) + 주말 | 121,122회 | 시간 영향 없음 |
| 소형 채널(1만 구독) + 먹방 | 2,684회 | 대형 채널과 약 45배 차이 |
| 소형 채널(1만 구독) + 레시피 | 2,461회 | 키워드에 따라 약 9% 차이 |

## 인사이트

1. **채널 성장이 최우선입니다.** 조회수의 약 45%는 채널 파워가 결정하므로, 신규 크리에이터는 키워드 최적화보다 채널 성장에 집중해야 합니다.
2. **대형 채널은 자유롭습니다.** 키워드나 업로드 시간을 바꿔도 예측값이 변하지 않았습니다.
3. **소형 채널은 키워드 선택이 약 9% 차이를 만듭니다.** 이 데이터에서는 "먹방"이 "레시피"보다 유리했습니다.

## 한계점과 알려진 이슈

정직하게 적어둔 부분입니다.

| 항목 | 내용 |
|---|---|
| 평가 방식 | R² 0.80은 모델 학습(ML) 실행 후 산출된 평가 결과값입니다. 다만 학습/테스트 데이터를 어떻게 나눴는지는 보고서에 기록되어 있지 않습니다. |
| 음식 영상 판별 | 키워드 기반 필터라서 음식 영상이 아닌데 포함되거나, 키워드가 없는 음식 영상이 빠질 수 있습니다. |
| 구독자 수 누락 | 검색으로 찾았지만 음식 채널 필터를 통과하지 못한 채널의 영상은 `subscriber_count`가 0으로 저장됩니다. |
| tags 저장 형식 | 수집 코드는 태그를 JSON 배열 문자열(`["a","b"]`)로 저장합니다. 그래서 `SPLIT(tags, ',')`로 센 `tag_count`는 태그가 없는 영상(`[]`)도 1개로 계산합니다. |
| 복원된 SQL | 원본 SQL 전문이 남아 있지 않아 `02_feature_engineering.sql`은 보고서의 Feature 표를 바탕으로 복원했고, `has_special_chars`는 수식을 알 수 없어 포함하지 않았습니다. |
| 데이터 삭제 | 교육용 계정 종료로 BigQuery 테이블과 배포 모델은 더 이상 존재하지 않아 결과를 그대로 재현할 수는 없습니다. |

## 향후 확장 계획

- 웹 UI 개발: 일반 사용자도 쉽게 예측할 수 있는 인터페이스
- 썸네일 분석: Vision AI로 이미지 Feature 추가
- 실시간 트렌드 반영: 시계열 Feature와 모델 재학습 파이프라인

## 저장소 구조

```
youtube-view-prediction/
├── README.md
├── requirements.txt
├── collector/
│   └── youtube_food_collector.py      # YouTube API → BigQuery 수집기
├── sql/
│   ├── 00_schema.sql                  # 수집 테이블 스키마
│   ├── 01_eda.sql                     # EDA 쿼리
│   └── 02_feature_engineering.sql     # 전처리 테이블 (복원본)
└── docs/
    └── project-report.pdf             # 프로젝트 최종 보고서
```

## 수집 코드 실행 방법

```bash
pip install -r requirements.txt

# API 키와 프로젝트 ID는 코드에 쓰지 않고 환경변수로 전달
export YOUTUBE_API_KEY="발급받은 API 키"
export GCP_PROJECT_ID="사용할 GCP 프로젝트 ID"

# 1) BigQuery에 테이블 생성 (sql/00_schema.sql 실행)
# 2) 수집 실행
python collector/youtube_food_collector.py
```

YouTube Data API 일일 할당량이 있으므로 한 번에 많은 채널을 수집하면 중간에 멈출 수 있습니다.
