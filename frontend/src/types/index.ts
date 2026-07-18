// 도메인 타입 — backend/models.py(tb_*) snake_case 필드명 그대로 (SCREEN_DESIGN_PLAN §6)

export type UserRole = 'ADMIN' | 'MANAGER' | 'STAFF'
export type UserStatus = 'PENDING' | 'ACTIVE' | 'INACTIVE'

export interface User {
  user_id: string
  email: string
  name: string
  position?: string | null
  auth_provider?: string | null
  role: UserRole
  status: UserStatus
  pin_set: boolean
  last_login_at?: string | null
  created_at?: string
  updated_at?: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type?: string
}

export interface AuthorizeResponse {
  /** 백엔드 schemas.AuthorizeResponse — authorize_url + state */
  authorize_url?: string
  state?: string
  /** 구버전 호환 */
  url?: string
}

// 공통 목록 응답
export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface AuditFields {
  created_by?: string | null
  created_by_name?: string | null
  created_at?: string | null
  updated_by?: string | null
  updated_by_name?: string | null
  updated_at?: string | null
}

// ---------------------------------------------------------------------------
// tb_client — 고객사 마스터 (SCR-03)
// ---------------------------------------------------------------------------
// 구분(client_type)은 공통 코드 마스터(tb_code, category=CLIENT_TYPE)로 관리 →
// 특정 리터럴로 고정하지 않고 문자열. 표시명은 useCodes('CLIENT_TYPE')로 해석.
export type ClientType = string
// 공통 코드 마스터(CONTRACT_STATUS)로 관리 → 문자열. 표시는 useCodes/StatusBadge로 해석.
export type ContractStatus = string

/** 공통 코드 마스터 (tb_code / GET /codes) */
export interface Code {
  code_id: string
  category: string
  code: string
  label: string
  color?: string | null // 시맨틱 팔레트명(emerald/amber/...)
  extra?: string | null // 부가값 — AGENCY는 기본 접속 URL
  sort_order: number
  active: string // Y/N
  is_system: string // Y/N
  is_locked?: boolean // 시스템 로직 참조 — 삭제·비활성 불가
  usage_count?: number | null
}

export interface Client {
  client_id: string
  client_type: ClientType
  company_name: string
  biz_reg_no?: string | null
  region?: string | null
  address?: string | null
  ceo_name?: string | null
  ceo_contact_phone?: string | null
  ceo_contact_email?: string | null
  main_contact_name?: string | null
  main_contact_phone?: string | null
  main_contact_email?: string | null
  contract_status: ContractStatus
  contract_date?: string | null
  keyman?: string | null
  manager_id?: string | null
  report_yn?: string | null
  lat?: number | null
  lng?: number | null
  created_at?: string
  updated_at?: string
  // 목록 응답 보강 필드 (routers/clients.py ClientListItem)
  manager_name?: string | null
  success_fee_rate?: number | null
  last_activity_at?: string | null
  /** 이번 달 보고서 상태 미니 배지 (STANDBY/WRITING/…) */
  report_status_this_month?: string | null
  /** 상세 응답 — 월간 보고서 구독 설정 (ClientDetailOut) */
  subscriptions?: ReportSubscription[]
}

/** 월간 보고서 설정 입력 (schemas.ReportSubscriptionIn) */
export interface ReportSubscriptionIn {
  report_type: string
  channel: 'EMAIL' | 'KAKAO' | 'BOTH'
  due_day?: number | null
  active?: string
  /** 메일 제목/본문 커스텀 — null이면 전역 기본 템플릿(tb_config) 사용 */
  mail_subject?: string | null
  mail_body?: string | null
}

/** 고객사 등록/수정 폼 payload (schemas.ClientCreate/ClientUpdate) */
export interface ClientPayload {
  client_type: ClientType
  company_name: string
  biz_reg_no?: string
  region?: string
  address?: string
  ceo_name?: string
  ceo_contact_phone?: string
  ceo_contact_email?: string
  main_contact_name?: string
  main_contact_phone?: string
  main_contact_email?: string
  contract_status: ContractStatus
  contract_date?: string | null
  keyman?: string
  manager_id?: string
  report_yn?: string
  /** 월간 보고서 설정 (tb_report_subscription upsert) */
  subscription?: ReportSubscriptionIn | null
}

// tb_report_subscription — 보고서 구독 설정
export interface ReportSubscription {
  sub_id: string
  client_id: string
  report_type: string
  channel: 'EMAIL' | 'KAKAO' | 'BOTH'
  due_day?: number | null
  active?: string
  /** 메일 제목/본문 커스텀 — null이면 전역 기본 템플릿(tb_config) 사용 */
  mail_subject?: string | null
  mail_body?: string | null
  created_at?: string
  updated_at?: string
}

// tb_report_recipient — 보고서 수신자 (schemas.RecipientOut, R2-B8)
export interface ReportRecipient {
  recipient_id: string
  client_id: string
  name?: string | null
  email: string
  cc_yn?: string | null // Y=CC / N=TO
  sub_id?: string | null // null=전 보고서 유형 공통
  created_at?: string
  updated_at?: string
}

// ---------------------------------------------------------------------------
// tb_activity_history — 활동 이력·이슈 (SCR-05·02)
// ---------------------------------------------------------------------------
// 공통 코드 마스터(ACTIVITY_TYPE)로 관리 → 문자열. 신규 유형 추가 가능.
export type ActivityType = string
export type IssueStatus = 'OPEN' | 'IN_PROGRESS' | 'HOLD' | 'CLOSED'
export type IssuePriority = 'URGENT' | 'NORMAL'
export type RetentionStage =
  | 'AWARENESS'
  | 'INTEREST'
  | 'REVIEW'
  | 'DECISION'
  | 'ONBOARDING'
  | 'UTILIZATION'
  | 'RENEWAL'
  | 'EXPANSION'

export interface ActivityHistory {
  history_id: string
  client_id?: string | null
  manager_id: string
  created_by?: string | null
  activity_date: string
  activity_type: ActivityType
  retention_stage?: RetentionStage | string | null
  issue_status?: IssueStatus | null
  priority?: IssuePriority | null
  due_date?: string | null
  next_action?: string | null
  next_action_done?: string | null
  related_history_id?: string | null
  title: string
  content?: string | null
  main_needs?: string | null
  created_at?: string
  updated_at?: string
  /** 자동 적재 건 표식 (보고서 발송·일정 완료 — 백엔드 부여) */
  is_auto?: boolean
  // 조인 보강
  client_name?: string | null
  manager_name?: string | null
  created_by_name?: string | null
}

export interface ActivityPayload {
  client_id?: string | null
  activity_date: string
  activity_type: ActivityType
  retention_stage?: string | null
  issue_status?: IssueStatus | null
  priority?: IssuePriority | null
  due_date?: string | null
  next_action?: string | null
  title: string
  content?: string | null
  main_needs?: string | null
  manager_id?: string | null
}

// tb_issue_comment — 이슈 코멘트 스레드 (SCR-02 Drawer)
export interface IssueComment {
  comment_id: string
  history_id: string
  manager_id: string
  comment_type: 'COMMENT' | 'STATUS_CHANGE' | 'ASSIGN'
  content?: string | null
  created_at: string
  manager_name?: string | null
}

// ---------------------------------------------------------------------------
// tb_schedule — 일정 (SCR-11)
// ---------------------------------------------------------------------------
export type ScheduleType = 'MEETING' | 'CALL' | 'SITE_VISIT' | 'REPORT_DUE' | 'INTERNAL'
export type ScheduleStatus = 'PLANNED' | 'DONE' | 'CANCELED'

export interface Schedule {
  schedule_id: string
  client_id?: string | null
  manager_id: string
  schedule_type: ScheduleType
  title: string
  start_at: string
  end_at?: string | null
  location?: string | null
  memo?: string | null
  status: ScheduleStatus
  recur_rule?: string | null
  recur_until?: string | null
  parent_schedule_id?: string | null
  history_id?: string | null
  created_at?: string
  updated_at?: string
  client_name?: string | null
  manager_name?: string | null
  /** Click-to-Call용 고객사 담당자 전화 (조인 보강) */
  client_phone?: string | null
}

export interface SchedulePayload {
  client_id?: string | null
  manager_id?: string | null
  schedule_type: ScheduleType
  title: string
  start_at: string
  end_at?: string | null
  location?: string | null
  memo?: string | null
  recur_rule?: string | null
}

// ---------------------------------------------------------------------------
// tb_report_delivery — 월간 보고서 발송 (SCR-12)
// ---------------------------------------------------------------------------
export type ReportStatus =
  | 'STANDBY'
  | 'WRITING'
  | 'REVIEW'
  | 'APPROVED'
  | 'SENT'
  | 'CONFIRMED'
  | 'CANCELED'
  | 'MERGED'

export interface ReportDelivery {
  report_id: string
  client_id: string
  period: string // 'YYYY-MM'
  report_type: string
  status: ReportStatus
  canceled_reason?: string | null
  due_date?: string | null
  sent_at?: string | null
  sent_channel?: 'EMAIL' | 'KAKAO' | 'BOTH' | null
  confirmed_at?: string | null
  confirm_basis?: string | null
  doc_id?: string | null
  pinned_doc_id?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  manager_id?: string | null
  created_at?: string
  updated_at?: string
  // 조인 보강 (schemas.ReportRow / ReportDetailOut)
  client_name?: string | null
  client_type?: string | null
  manager_name?: string | null
  latest_doc?: Document | null
  send_logs?: ReportSendLog[]
  documents?: Document[]
}

// tb_report_send_log — 발송 이력 (append-only)
export interface ReportSendLog {
  send_id: string
  report_id: string
  seq: number
  sent_doc_id?: string | null
  recipients?: string | null
  channel?: string | null
  result?: 'SUCCESS' | 'FAIL' | 'BOUNCED' | string | null
  result_updated_at?: string | null
  confirmed_at?: string | null
  confirm_basis?: string | null
  confirmed_by?: string | null
  sent_by?: string | null
  reason?: string | null
  created_at: string
  sent_by_name?: string | null
}

// ---------------------------------------------------------------------------
// tb_document — 문서 아카이브 (SCR-13)
// ---------------------------------------------------------------------------
export type DocType = 'CONTRACT' | 'REPORT' | 'FORM' | 'PHOTO' | 'SIGN' | 'ETC'

export interface Document {
  doc_id: string
  client_id?: string | null
  doc_type: DocType
  title: string
  file_url: string
  version: number
  report_id?: string | null
  history_id?: string | null
  asset_id?: string | null
  uploaded_by?: string | null
  created_at: string
  uploaded_by_name?: string | null
  client_name?: string | null
}

// ---------------------------------------------------------------------------
// tb_asset — 자산·연동 (SCR-03D 자산 탭 축약형, 본 화면은 P2)
// ---------------------------------------------------------------------------
export interface Asset {
  asset_id: string
  client_id: string
  asset_group: string
  asset_type?: string | null
  quantity?: number | null
  main_spec?: string | null
  telemetry_yn?: string | null
  location_info?: string | null
  status?: string | null
  agency_name?: string | null
  site_url?: string | null
  auth_type?: string | null
  login_id?: string | null
  usage_purpose?: string | null
  /** 인증정보(암호화분) 설정 여부 — 값은 미노출, reveal은 P2 */
  has_credentials?: boolean
  created_at?: string
  updated_at?: string
  // 목록 조인 보강
  client_name?: string | null
}

/** 자산 등록/수정 payload (schemas.AssetCreate/AssetUpdate) — 인증 정보는 입력 시에만 전송 */
export interface AssetPayload {
  client_id: string
  asset_group: string
  asset_type?: string | null
  quantity?: number | null
  main_spec?: string | null
  telemetry_yn?: string
  location_info?: string | null
  status?: string
  agency_name?: string | null
  site_url?: string | null
  auth_type?: string
  login_id?: string | null
  /** ID_PW=비밀번호 / API_KEY=토큰 — 변경 시에만 전송(저장 후 재조회 불가, reveal만) */
  auth_value?: string
  usage_purpose?: string | null
}

/** POST /batch/account-check 응답 (schemas.AccountCheckResponse) — 계정 월별 점검 배치 결과 */
export interface AccountCheckResponse {
  period: string
  targets: number
  created: number
  skipped: number
  unreachable: number
}

/** POST /assets/{id}/reveal-auth 응답 (schemas.AssetRevealOut) — 평문 일시 복호화 */
export interface RevealAuthResponse {
  asset_id: string
  auth_type?: string | null
  login_id?: string | null
  auth_value: string
  revealed_at: string
}

// ---------------------------------------------------------------------------
// tb_project — 감축 사업 (SCR-06)
// ---------------------------------------------------------------------------
/** 진행 상태 — 백엔드 저장 값 그대로 한국어 (schemas._PROJECT_STATUS_PATTERN) */
export type ProjectStatus = '기획' | '등록완료' | '모니터링' | '검증' | '발급완료'

export interface Project {
  project_id: string
  client_id?: string | null // 묶음 사업 시 대표사
  project_name: string
  reg_code?: string | null // 예: R-2020-KR-03-000528
  project_status: ProjectStatus | string
  reg_date?: string | null
  credit_start_date?: string | null
  credit_end_date?: string | null
  credit_period_type?: string | null
  mon_start_date?: string | null
  mon_end_date?: string | null
  mon_cycle?: string | null
  expected_issue_date?: string | null
  expected_credits?: number | null
  unit_price?: number | null // 수기 단가 (§10.3) — 미입력 시 "미정"
  price_source?: string | null
  issued_credits?: number | null // 확정 발급량 (R2-A1)
  issued_at?: string | null
  manager_id?: string | null
  created_at?: string
  updated_at?: string
  // 조인 보강 (schemas.ProjectListItem / ProjectDetailOut)
  manager_name?: string | null
  /** 참여 고객사 수 (목록 응답) */
  client_count?: number
  /** 상세 응답 — 참여 고객사 매핑 목록 */
  clients?: ProjectClientMap[]
  /** 상세 응답 — 배분율 합계 (100% 검증 UI용) */
  allocation_total?: number
}

export interface ProjectPayload {
  client_id?: string | null
  project_name: string
  reg_code?: string | null
  project_status: string
  reg_date?: string | null
  credit_start_date?: string | null
  credit_end_date?: string | null
  credit_period_type?: string | null
  mon_start_date?: string | null
  mon_end_date?: string | null
  mon_cycle?: string | null
  expected_issue_date?: string | null
  expected_credits?: number | null
  unit_price?: number | null
  issued_credits?: number | null
  issued_at?: string | null
  manager_id?: string | null
}

// ---------------------------------------------------------------------------
// tb_project_client_map — 참여 고객사 매핑·정산 (SCR-06 상세 / SCR-07)
// ---------------------------------------------------------------------------
export type SettlementStatus = 'STANDBY' | 'BILLED' | 'COMPLETED'

export interface ProjectClientMap {
  map_id: string
  project_id: string
  client_id: string
  asset_id?: string | null
  allocation_ratio?: number | null // 배분 비율(%)
  success_fee_rate?: number | null // 성공 보수율(%) 🔒
  expected_amount?: number | null // 서버 계산 (§10.3) 🔒 — 단가 미입력 시 null="미정"
  settlement_status?: SettlementStatus | string | null
  billed_at?: string | null
  completed_at?: string | null
  paid_amount?: number | null
  payment_type?: string | null
  created_at?: string
  updated_at?: string
  // 조인 보강 (schemas.ProjectMapOut / SettlementRow / ClientProjectRow)
  client_name?: string | null
  /** 연결 자산 요약 (분류·제원) */
  asset_summary?: string | null
  project_name?: string | null
  /** 사업 진행 상태 (고객사 상세 '참여 사업·정산' 탭 — schemas.ClientProjectRow) */
  project_status?: string | null
  unit_price?: number | null
  expected_credits?: number | null
}

/** 매핑 등록/수정 payload (schemas.ProjectMapIn) — 동일 고객사는 upsert */
export interface MappingPayload {
  client_id: string
  asset_id?: string | null
  allocation_ratio: number
  success_fee_rate: number
}

// ---------------------------------------------------------------------------
// 대시보드 (SCR-01) — GET /dashboard/stats (schemas.DashboardStats)
// ---------------------------------------------------------------------------
export interface DashboardKpi {
  total_clients: number
  client_delta: number
  report_target: number
  report_sent: number
  urgent_open_issues: number
  contract_hold_clients: number
  expected_billing_amount?: number | null
}

export interface FunnelStage {
  stage: string
  count: number
}

export interface DashboardStats {
  period: string
  kpi: DashboardKpi
  funnel: FunnelStage[]
  recent_activities: ActivityHistory[]
  open_issues: ActivityHistory[]
}

// ---------------------------------------------------------------------------
// tb_chat_thread / tb_chat_message / tb_kakao_contact — 카카오톡 상담 관제 (SCR-08)
// ---------------------------------------------------------------------------
export type ChatMode = 'AI' | 'HUMAN'
export type ChatThreadStatus = 'OPEN' | 'WAITING' | 'CLOSED'
export type ChatSenderType = 'CUSTOMER' | 'AI' | 'STAFF' | 'SYSTEM'
/** POST /chat/threads/{id}/reply 응답 delivery */
export type ChatDelivery = 'SENT' | 'FAILED' | 'NOT_CONFIGURED'

export interface ChatThread {
  thread_id: string
  client_id?: string | null
  kakao_contact_id?: string | null
  mode: ChatMode
  status: ChatThreadStatus
  last_message_at?: string | null
  assigned_manager_id?: string | null
  created_at?: string
  updated_at?: string
  // 조인 보강 (백엔드 리스트 응답)
  client_name?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  contract_status?: string | null
  asset_summary?: string | null
  assigned_manager_name?: string | null
  last_message_preview?: string | null
  unread_count?: number | null
}

export interface ChatMessage {
  message_id: string
  thread_id: string
  sender_type: ChatSenderType
  sender_id?: string | null
  content?: string | null
  created_at: string
  // 조인·부가 필드 (백엔드 부여 시)
  sender_name?: string | null
  delivery_status?: string | null // SENT/FAILED/NOT_CONFIGURED
}

/** POST /chat/threads/{id}/reply 응답 */
export interface ChatReplyResponse {
  delivery: ChatDelivery
  message?: ChatMessage | null
  message_id?: string | null
  detail?: string | null
}

/** GET /chat/badge — LNB 뱃지 (직원 연결 대기 건수) */
export interface ChatBadge {
  waiting: number
}

export type KakaoContactStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'BLOCKED'

export interface KakaoContact {
  contact_id: string
  kakao_user_key?: string
  client_id?: string | null
  name?: string | null
  phone?: string | null
  contact_role?: string | null
  status: KakaoContactStatus
  requested_at?: string | null
  approved_by?: string | null
  approved_at?: string | null
  memo?: string | null
  created_at?: string
  updated_at?: string
  client_name?: string | null
}

// 보고서 목록 응답 (schemas.ReportListResponse)
export interface ReportSummary {
  target: number
  standby: number
  writing: number
  review: number
  approved: number
  sent: number
  confirmed: number
  canceled: number
}

export interface ReportListResponse {
  period: string
  summary: ReportSummary
  items: ReportDelivery[]
}

// ---------------------------------------------------------------------------
// tb_segment — 세그먼트 보고서 발송 (SCR-12 확장, backend/routers/segments.py)
// ---------------------------------------------------------------------------
/** 세그먼트 조건 — 축 간 AND, 축 내 IN(OR). 빈 축은 전체 */
export interface SegmentCriteria {
  region?: string[]
  client_type?: string[]
  contract_status?: string[]
  project_id?: string[]
  asset_group?: string[]
  settlement_status?: string[]
}

export interface Segment {
  segment_id: string
  name: string
  description?: string | null
  criteria: SegmentCriteria
  active?: string | null
  manager_id?: string | null
  manager_name?: string | null
  mail_subject?: string | null
  mail_body?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 세그먼트 생성/수정 (schemas.SegmentIn) */
export interface SegmentPayload {
  name: string
  description?: string | null
  criteria: SegmentCriteria
  mail_subject?: string | null
  mail_body?: string | null
}

export interface SegmentPreviewItem {
  client_id: string
  company_name: string
  client_type?: string | null
  region?: string | null
  /** 수신 가능 — 공통 수신자 또는 주 담당자 이메일 보유 */
  can_receive: boolean
}

export interface SegmentPreviewResponse {
  total: number
  items: SegmentPreviewItem[]
}

/** 조건 축 선택지 — region만 서버 제공(나머지는 /codes·/projects 재사용) */
export interface SegmentFacets {
  regions: string[]
}

/** 발송 요청 (schemas.SegmentSendRequest) — criteria는 즉석 발송에서만 */
export interface SegmentSendPayload {
  doc_ids: string[]
  subject?: string
  body?: string
  criteria?: SegmentCriteria
}

export interface SegmentSendDetail {
  client_id: string
  client_name?: string | null
  result: 'SUCCESS' | 'FAIL'
  reason?: string | null
}

/** 발송 실행 응답 — 카운트 요약 + 고객사별 결과 */
export interface SegmentSendResponse {
  send_id: string
  target_count: number
  sent_count: number
  failed_count: number
  details: SegmentSendDetail[]
}

/** 발송 실행 이력 행 (tb_segment_send) */
export interface SegmentSend {
  send_id: string
  segment_id?: string | null
  criteria_snapshot?: string | null // 발송 시점 조건 JSON
  doc_ids?: string | null // JSON 배열 문자열
  subject?: string | null
  body?: string | null
  target_count: number
  sent_count: number
  failed_count: number
  sent_by?: string | null
  sent_by_name?: string | null
  created_at?: string | null
}

/** 발송 이력 상세의 고객사별 로그 행 (tb_segment_send_log) */
export interface SegmentSendLog {
  log_id: string
  client_id: string
  client_name?: string | null
  recipients?: string | null // 수신자 스냅샷 JSON
  channel?: string | null
  result?: string | null
  reason?: string | null
  created_at?: string | null
}

/** 발송 이력 상세 — 실행 행 + 고객사별 로그 목록 */
export interface SegmentSendDetailOut extends SegmentSend {
  logs: SegmentSendLog[]
}

// ── 엑셀 일괄 등록 (SCR-03/04 imports) — backend schemas.Import* 대응 ──

export type ImportEntity = 'clients' | 'assets'

/** 컬럼 안내 (schemas.ImportColumnOut) — 업로드 가이드·양식 설명용 */
export interface ImportColumn {
  field: string
  label: string
  required: boolean
  code_category?: string | null // tb_code 카테고리 (라벨/코드 양방향 수용)
  resolver?: string | null // user_by_name/client_by_name — 이름으로 입력
  yn: boolean // Y/N 컬럼
  allowed_values?: string[] | null // 고정값 컬럼 허용 표기
  example?: string | null
}

export interface ImportSpec {
  entity: string
  label: string
  max_rows: number
  filename: string
  columns: ImportColumn[]
}

/** 행 단위 검증 결과 — row는 엑셀 실제 행 번호(헤더=1, 데이터 2부터) */
export interface ImportRowResult {
  row: number
  status: 'OK' | 'ERROR'
  data: Record<string, string | null> // 라벨 → 정규화된 저장 예정 값(표시용)
  errors: string[]
  warnings: string[]
}

/** 미리보기(DB 무변경) — commit 전 전 행 검증 결과 */
export interface ImportPreview {
  entity: string
  total_rows: number
  valid_rows: number
  error_rows: number
  unknown_columns: string[]
  /** 파일 수준 안내 — 예시 행 스킵 등 */
  warnings?: string[] // 스펙에 없는 헤더(무시됨) — 경고
  rows: ImportRowResult[]
}

/** 반영 결과 — 유효 행만 생성(부분 반영), 오류 행은 건너뜀 */
export interface ImportCommitResult {
  entity: string
  created: number
  skipped: number
  errors: ImportRowResult[]
}
