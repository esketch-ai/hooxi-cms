---
name: qaqc-handoff
description: >-
  개발 요건이 완료(구현→검증→리뷰→커밋)되면 관련 기능들의 QAQC(품질 검증)를 기존 QAQC
  워크트리에 위임형(fire-and-forget)으로 넘긴다. "QAQC 넘겨", "QAQC 인계", "품질 검증
  돌려", "개발 완료 → QAQC" 같은 요청이나, dev 루프 마무리(커밋) 직후 QA 인계 시 사용.
  QAQC 워크트리는 Orca 관리이며 로컬 LM Studio(Qwen) 기반 OpenCode 에이전트가 상주한다.
---

# QAQC 인계 (개발 완료 → QAQC 워크트리 위임)

개발 요건 완료 시 관련 기능의 품질 검증(QAQC)을 **상시 QAQC 워크트리**로 위임한다.
**위임형(fire-and-forget)**: 브리프를 전달하고 모니터링하지 않는다. 결과는 QAQC 에이전트가
그 워크트리에서 보고한다. (감독형이 필요하면 사용자가 "QAQC 결과 받아서 반영"처럼 명시할 때만)

## 고정 사실 (이 저장소)
- QAQC 워크트리: Orca `name:QAQC`
  = `9fb53d23-00f6-4bb4-92e9-b62d4ee21cc0::/Users/ssh/orca/workspaces/hooxi-cms/QAQC`
  (branch `esketch-ai/QAQC`). QA 에이전트 = 터미널 제목 **"OpenCode"** (로컬 LM Studio·Qwen).
- Orca CLI 실행 파일: 이 세션에선 `orca` (macOS). 규칙은 `orca skills get orca-cli` 참조.
- 터미널 **핸들은 stale 될 수 있으니 절대 하드코딩하지 말고 매번 재조회**한다. 워크트리
  셀렉터(`name:QAQC`)만 안정적이다.

## 인계 절차

1) Orca 앱 확인: `orca status --json` (ok=false면 `orca open --json`).
2) QA 에이전트 터미널 핸들 재조회 — "OpenCode" 터미널을 찾는다:
   ```
   orca terminal list --worktree name:QAQC --json
   ```
   결과에서 `title`이 `OpenCode`인 항목의 `handle`을 사용. (없으면 사용자에게 QAQC
   에이전트가 안 떠 있다고 알리고 중단 — 임의로 새 에이전트를 만들지 않는다.)
3) 아래 **QAQC 브리프**를 채워 전달(위임, 대기 금지):
   ```
   orca terminal send --terminal <handle> --text "<QAQC 브리프>" --enter --json
   ```
   - `terminal_handle_stale` 반환 시 2)로 돌아가 재조회 후 1회 재전송(옛/새 핸들 동시 전송 금지).
   - `orchestration task-create` / `check --wait` / `dispatch --inject`는 쓰지 않는다(위임형).
4) (선택) QAQC 워크트리 카드에 진행 표시:
   ```
   orca worktree set --worktree name:QAQC --comment "QAQC 인계: <요건 요약> (커밋 <sha7>)" --json
   ```
5) 사용자에게 "무엇을 QAQC로 넘겼는지" 한 줄 보고하고 **모니터링 없이 종료**.

## QAQC 브리프 템플릿 (항상 이 체계로)
```
[QAQC 요청] <요건/기능명> (dev 커밋 <sha7>)

범위:
- 완료 기능: <핵심 기능 요약>
- 변경 파일: <주요 파일 경로들>
- 관련 화면/엔드포인트: <예: 수집 계정 관리, GET /assets ...>

성공 기준:
- 백엔드 pytest 전건 통과, 프론트 빌드 통과, 배포 스모크 정상

검증 항목(7종):
1. 자동 테스트 재실행 — cd backend && python -m pytest -q
2. 빌드 — cd frontend && NODE_OPTIONS= npm run build
3. 스모크 — 로컬/대상 기동 후 핵심 API·화면 동작(로그인·목록·해당 기능)
4. 시나리오/E2E — 이 기능의 대표 사용자 흐름 1~2개 end-to-end
5. 회귀 — 이 변경이 건드린 인접 기능(예: 발송/폴더/정산 등) 정상 여부
6. 규약·보안 — R2-E6(감사 로그·응답에 비밀값 없음), 분류값 tb_code(하드코딩 금지),
   배포 컬럼 추가 시 ensure_schema 반영
7. 엣지케이스 — 빈값/권한/동시성/누락 데이터 등 경계 조건

산출물(반환 형식):
- 통과/실패 목록(심각도순), 각 실패의 재현 절차 + 수정 제안
- 프로그램 원인 vs 외부(데이터·환경) 원인 구분

실패가 있으면 dev(main 워크트리)로 원인·수정안과 함께 반려 요청.
```

## 스코프/주의
- 이 스킬은 **dev 요건 완료 후**(카파시 4원칙 루프의 커밋 단계 뒤)에 QAQC를 넘기는 용도다.
  구현·리뷰 자체를 대신하지 않는다(그건 implementer/verifier/reviewer 서브에이전트).
- 위임형이므로 QAQC 결과를 기다리거나 폴링하지 않는다. 사용자가 결과 반영을 원하면 그때
  QAQC 워크트리에서 결과를 읽어(`orca terminal read --terminal <handle>`) dev 루프로 가져온다.
- QAQC 에이전트/워크트리를 새로 만들지 않는다(상시 워크트리 재사용). 없거나 죽어 있으면
  사용자에게 알리고 중단한다.
