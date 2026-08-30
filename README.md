# 항공권 데일리 스캐너

Travelpayouts Data API 로 매일 항공권을 수집해 대시보드를 만든다.
GitHub Actions 가 매일 07:00 KST 에 실행하고 GitHub Pages 로 배포한다.

## 설치

**1. 레포 만들기 (공개)**

이 폴더 전체를 새 레포에 올린다.

```
scanner.py
README.md
.github/workflows/daily.yml
```

**2. 토큰 등록**

레포 → Settings → Secrets and variables → Actions → New repository secret

- Name: `TP_TOKEN`
- Secret: Travelpayouts 토큰 32자리

**토큰을 코드나 README 에 직접 쓰지 않는다.** `scanner.py` 의 `DEFAULT_TOKEN` 은
비어 있어야 한다. 공개 레포에 토큰이 올라가면 즉시 재발급해야 한다.

**3. Pages 켜기**

레포 → Settings → Pages → Source 를 **GitHub Actions** 로 설정.

**4. 첫 실행**

Actions 탭 → "항공권 데일리 스캔" → Run workflow.

성공하면 `https://<사용자명>.github.io/<레포명>/` 에서 대시보드가 열린다.

## 스케줄

`.github/workflows/daily.yml` 의 cron 은 **UTC 기준**이다.

| KST | cron (UTC) |
|---|---|
| 07:00 | `0 22 * * *` |
| 08:00 | `0 23 * * *` |
| 21:00 | `0 12 * * *` |

GitHub 의 예약 실행은 부하에 따라 **수 분에서 한 시간까지 밀릴 수 있다.**
정시 실행이 보장되지 않으므로 분 단위 정확도가 필요하면 다른 방법을 써야 한다.

## 상태 파일

`flight-deals/state/price_history.json` 이 변동추적(신규/하락/상승/소멸)의 근거다.
워크플로가 매 실행마다 레포로 커밋하므로 지우면 추적이 초기화된다.

**공개 레포이므로 이 파일에서 관심 노선과 가격 이력이 그대로 보인다.**

## 수동 실행

```
python scanner.py            # 오늘 로테이션
python scanner.py --all      # 전 노선
python scanner.py --raw      # API 응답 구조 확인
```

로컬 실행 시 토큰은 환경변수 또는 저장 파일에서 읽는다.

```
python scanner.py --save-token <토큰>
```

## 알려진 한계

- **Travelpayouts 는 캐시 데이터**다. 실시간 판매가가 아니며 등급 상한은 B다.
  예약 전 판매처에서 직접 확인해야 한다.
- `depart_date` 월 필터와 `one_way` 파라미터가 API 에서 무시된다.
  왕복 기간 통제는 `length` 가 담당하며 코드에서 박수 검증을 다시 한다.
- **청주(CJJ) 캐시가 얇다.** ICN 대비 6% 수준이라 결과가 비거나 표본이
  적을 수 있다. 표본 수는 화면의 `표본 N` 으로 확인한다.
- API 가 공항코드를 도시코드로 접어서 응답한다 (ICN→SEL, KIX→OSA).
