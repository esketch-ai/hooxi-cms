# Hooxi-CMS (Carbon Fleet)

탄소감축 컨설팅사의 내부 CMS. 운수사·건물 고객사, 자산·연동, 감축사업·정산, 카카오 상담 등 관리.

- 백엔드: FastAPI(Python 3.9) + SQLAlchemy. `backend/` (routers/·models.py·schemas.py). 테스트 `cd backend && python -m pytest`.
- 프론트: React 19 + TS + Vite + Tailwind v4. `frontend/src/` (features/·lib/·types/). 빌드 `cd frontend && NODE_OPTIONS= npm run build`.
- 배포: main push → Cloud Build → Cloud Run(us-west1, 서비스 hooxi-cms). 현재 테스트베드 계정.
- 규약: 공통 분류/상태값은 공통 코드 마스터(tb_code)로 관리(하드코딩 금지), 배포 테이블 컬럼 추가 시 `ensure_schema` 반영, 감사 로그에 비밀값 금지(R2-E6).

## 개발 4원칙 (Andrej Karpathy) — 이 저장소의 작업 도리(doctrine)

멀티 서브에이전트 실행 구성. 사소하지 않은 기능 추가·버그 수정은 아래 4원칙에 따라 수행하고, 각 역할은 `.claude/agents/`의 서브에이전트에 위임한다.

1. **구현 전 사고 (Think Before Coding)** — 코드 작성 전 가정을 의심하고 숨은 모호함을 명확히 하며 트레이드오프를 먼저 따진다. → `planner`. 모호하면 사용자에게 확인, 추측 금지.
2. **작은 단위로 점진적 진행 (Iterate in Small Steps)** — 한 번에 완성하려 하지 않는다. 아주 작은 증분마다 `implementer`→`verifier`를 **짧게 반복**해 문제를 조기에 잡는다. 큰 덩어리 일괄 구현 후 한 번 검증 금지.
3. **테스트/검증 기반 (Verify with Tests)** — 사람이 일일이 눈으로 확인하지 않는다. 명확한 검증 기준과 자동화 루프(pytest·빌드·스모크)를 설계해 AI가 스스로 오류를 찾고 고친다. → `verifier`. FAIL이면 구현으로 반려해 자가수정.
4. **목표 기반 실행 (Goal-Oriented Execution)** — 세부 단계 지시가 아니라 달성할 **성공 기준(success criteria)** 을 착수 시 명시한다(통과할 테스트/관찰 가능한 동작). 그 기준을 충족할 때까지 2·3의 루프를 **자율적으로** 돈다.

### 실행 루프
0. (원칙4) **성공 기준을 먼저 정의**한다 — 무엇이 통과되면 "완료"인가(테스트·빌드·관찰 가능한 동작).
1. (원칙1) `planner`로 가정·모호함·트레이드오프를 정리한 최소 계획 수립(코드 미수정).
2. (원칙2·3) 작은 증분마다 `implementer`로 구현 → 즉시 `verifier`로 자동 검증. FAIL이면 원인과 함께 구현으로 반려 → 수정 → 재검증.
3. (원칙4) 성공 기준을 모두 충족할 때까지 2를 반복(자율 루프).
4. 기준 충족 후 `reviewer`로 diff 정확성·정합성·보안·규약·단순화 점검. 지적은 커밋 전 반영.
5. 통과 시 커밋/푸시/배포(사용자 지시 시).

### 적용 범위
- **적용**: 새 기능, 라우터/모델/스키마 변경, 다중 파일 리팩터, 데이터 정합성이 걸린 변경.
- **생략(직접 처리)**: 오타·주석·한 줄 설정 등 런타임 표면이 없는 사소한 편집, 단순 조회/질문.
- 독립 작업이 여러 갈래면 서브에이전트를 병렬로, 의존이 있으면 루프 순서를 지킨다.
