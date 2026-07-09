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
export type ClientType = 'TRANSPORT' | 'FACILITY'
export type ContractStatus = 'ACTIVE' | 'HOLD' | 'END'

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
  created_at?: string
  updated_at?: string
}

// ---------------------------------------------------------------------------
// tb_activity_history — 활동 이력·이슈 (SCR-05·02)
// ---------------------------------------------------------------------------
export type ActivityType = 'CALL' | 'MEETING' | 'SITE_VISIT' | 'EMAIL' | 'ISSUE' | 'KAKAO'
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
export type DocType = 'CONTRACT' | 'REPORT' | 'FORM' | 'PHOTO' | 'ETC'

export interface Document {
  doc_id: string
  client_id?: string | null
  doc_type: DocType
  title: string
  file_url: string
  version: number
  report_id?: string | null
  history_id?: string | null
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

// 보고서 목록 응답 (schemas.ReportListResponse)
export interface ReportSummary {
  target: number
  standby: number
  writing: number
  review: number
  sent: number
  confirmed: number
  canceled: number
}

export interface ReportListResponse {
  period: string
  summary: ReportSummary
  items: ReportDelivery[]
}
