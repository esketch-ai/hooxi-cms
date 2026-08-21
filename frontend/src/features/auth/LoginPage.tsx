// 로그인 — 이메일+PIN 단일 경로(네이버웍스 SSO 은퇴, 2026-08).
// 좌측 브랜드 패널(데스크톱) + 우측: 내부 직원 로그인 카드 / 고객사·투자사 카카오 채널 안내.
// 외부(고객사·투자사)는 여기서 로그인하지 않는다 — 카카오 비즈니스 채널 가입 → 담당자 발급
// 매직링크(알림톡)로 전용 포털에 접속한다.
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import {
  ChatCircleDots,
  ChartLineUp,
  CircleNotch,
  HourglassMedium,
  Leaf,
  LockKey,
  ShieldCheck,
  Truck,
} from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { useLoginConfig } from '../../lib/api/queries'
import { useToast } from '../../components/Toast'

export function LoginPage() {
  const { user, isLoading, isAuthenticated, isPending, pinSet, loginEmail, logout } = useAuth()
  const { data: loginConfig } = useLoginConfig()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [loginPin, setLoginPin] = useState('')
  const [pinRequired, setPinRequired] = useState(false)
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)

  // PIN 설정 스텝 (R2-C11: 최초 ACTIVE 로그인 시 필수)
  const [pin1, setPin1] = useState('')
  const [pin2, setPin2] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  const [pinLoading, setPinLoading] = useState(false)
  const { setPin } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-void">
        <CircleNotch size={28} className="animate-spin text-slatey" />
      </div>
    )
  }

  // 이미 인증(ACTIVE + PIN 설정 완료) 상태로 /login 접근 → 홈
  if (isAuthenticated && pinSet) {
    return <Navigate to="/" replace />
  }

  const handleEmailLogin = async (e: FormEvent) => {
    e.preventDefault()
    setLoginError(null)
    if (!email.trim()) {
      setLoginError('이메일을 입력해 주세요.')
      return
    }
    if (pinRequired && !/^\d{4,6}$/.test(loginPin)) {
      setLoginError('PIN(4~6자리 숫자)을 입력해 주세요.')
      return
    }
    setLoginLoading(true)
    try {
      const result = await loginEmail(email.trim(), pinRequired ? loginPin : undefined)
      if (result.status === 'PIN_REQUIRED') {
        setPinRequired(true)
        return
      }
      if (result.status === 'OK' && result.me?.status === 'ACTIVE' && result.me.pin_set) {
        navigate('/', { replace: true })
      }
      // PENDING·PIN 미설정은 아래 렌더 분기에서 처리
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        setLoginError('PIN이 올바르지 않습니다.')
      } else if (isAxiosError(error) && error.response?.status === 403) {
        setLoginError('회사 계정(@hooxipartners.com)으로만 로그인할 수 있습니다.')
      } else {
        setLoginError('로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.')
      }
    } finally {
      setLoginLoading(false)
    }
  }

  const handlePinSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setPinError(null)
    if (!/^\d{4,6}$/.test(pin1)) {
      setPinError('PIN은 4~6자리 숫자로 입력해 주세요.')
      return
    }
    if (pin1 !== pin2) {
      setPinError('두 PIN이 일치하지 않습니다.')
      return
    }
    setPinLoading(true)
    try {
      await setPin(pin1)
      showToast('PIN이 설정되었습니다.', 'success')
      navigate('/', { replace: true })
    } catch {
      setPinError('PIN 설정에 실패했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setPinLoading(false)
    }
  }

  const inputCls =
    'h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
  const pinInputCls =
    'h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-center text-lg tracking-[0.5em] text-bone focus:border-white/30 focus:outline-none'

  return (
    <div className="min-h-dvh bg-void lg:grid lg:grid-cols-[1.1fr_1fr]">
      {/* ── 좌: 브랜드 패널(데스크톱) — 서비스 정체성 ── */}
      <aside className="hero-horizon relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-white/15 backdrop-blur">
            <Leaf size={22} weight="fill" className="text-white" />
          </span>
          <div>
            <p className="text-lg font-semibold tracking-tight text-white">Hooxi Partners</p>
            <p className="text-xs text-white/70">Carbon Fleet Management</p>
          </div>
        </div>

        <div>
          <h1 className="max-w-md text-3xl leading-snug font-bold tracking-tight text-white">
            탄소감축 사업의 시작부터 정산까지,
            <br />한 곳에서.
          </h1>
          <ul className="mt-8 space-y-4 text-sm text-white/85">
            <li className="flex items-center gap-3">
              <Truck size={18} className="shrink-0" />
              운수사·차량·계약대수 — 고객과 자산을 한 번에
            </li>
            <li className="flex items-center gap-3">
              <ChartLineUp size={18} className="shrink-0" />
              감축량·시세·정산 — 숫자가 흐름으로 보이는 경영 관찰
            </li>
            <li className="flex items-center gap-3">
              <ShieldCheck size={18} className="shrink-0" />
              부서별 권한·감사 로그 — 안전한 공동 운영
            </li>
          </ul>
        </div>

        <p className="text-xs text-white/60">
          © Hooxi Partners · 내부 관리 시스템(CMS)
        </p>
      </aside>

      {/* ── 우: 로그인/안내 ── */}
      <main className="flex min-h-dvh items-center justify-center px-4 py-10">
        <div className="w-full max-w-md space-y-4">
          {/* 모바일 브랜드(좌 패널이 숨는 화면) */}
          <div className="mb-2 text-center lg:hidden">
            <div className="hero-horizon mb-3 inline-flex h-14 w-14 items-center justify-center rounded-[18px]">
              <Leaf size={26} weight="fill" className="text-white" />
            </div>
            <div className="flex items-center justify-center gap-2.5">
              <img
                src="/hooxipartners_logo_trans.png"
                alt="Hooxi Partners"
                className="h-9 w-auto dark:brightness-0 dark:invert"
              />
              <span className="text-xl font-semibold tracking-tight text-red-600 dark:text-red-500">
                CMS
              </span>
            </div>
          </div>

          <div className="animate-fade-in rounded-[24px] border border-hairline bg-graphite p-8">
            {isPending ? (
              /* 승인 대기 화면 (status=PENDING) */
              <div className="text-center">
                <HourglassMedium size={40} className="mx-auto mb-4 text-amber-400" />
                <h2 className="text-lg font-bold text-bone">가입 요청이 접수되었습니다</h2>
                <p className="mt-2 text-sm leading-relaxed text-ash">
                  관리자 승인 후 이용할 수 있습니다.
                  <br />
                  승인이 완료되면 알림으로 안내됩니다.
                </p>
                <p className="mt-4 text-xs text-slatey">{user?.email}</p>
                <button
                  type="button"
                  onClick={logout}
                  className="mt-6 w-full rounded-full border border-hairline px-4 py-2.5 text-sm font-medium text-bone hover:bg-elevate"
                >
                  다른 계정으로 로그인
                </button>
              </div>
            ) : isAuthenticated && !pinSet ? (
              /* PIN 설정 스텝 (최초 ACTIVE 로그인) */
              <form onSubmit={handlePinSubmit}>
                <div className="mb-5 text-center">
                  <LockKey size={36} className="mx-auto mb-3 text-bone" />
                  <h2 className="text-lg font-bold text-bone">PIN 설정</h2>
                  <p className="mt-1 text-sm text-ash">
                    로그인·민감 정보 열람에 사용할 PIN(4~6자리 숫자)을 설정해 주세요.
                  </p>
                </div>
                <label className="mb-1 block text-xs font-medium text-ash">PIN 입력</label>
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={6}
                  value={pin1}
                  onChange={(e) => setPin1(e.target.value.replace(/\D/g, ''))}
                  className={`mb-3 ${pinInputCls}`}
                />
                <label className="mb-1 block text-xs font-medium text-ash">PIN 다시 입력</label>
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={6}
                  value={pin2}
                  onChange={(e) => setPin2(e.target.value.replace(/\D/g, ''))}
                  className={pinInputCls}
                />
                {pinError && <p className="mt-2 text-sm text-rose-400">{pinError}</p>}
                <button
                  type="submit"
                  disabled={pinLoading}
                  className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-primary text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
                >
                  {pinLoading && <CircleNotch size={16} className="animate-spin" />}
                  PIN 설정 완료
                </button>
              </form>
            ) : (
              /* 내부 직원 로그인 — 이메일 + PIN */
              <div>
                <h2 className="text-lg font-bold text-bone">직원 로그인</h2>
                <p className="mt-1 mb-5 text-sm text-ash">
                  회사 이메일로 로그인하세요. 최초 로그인은 관리자 승인 후 이용할 수 있습니다.
                </p>
                <form onSubmit={handleEmailLogin}>
                  <label className="mb-1 block text-xs font-medium text-ash">회사 이메일</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value)
                      setPinRequired(false)
                      setLoginPin('')
                    }}
                    placeholder="name@hooxipartners.com"
                    autoComplete="username"
                    className={inputCls}
                    aria-label="회사 이메일"
                  />
                  {pinRequired && (
                    <>
                      <label className="mt-3 mb-1 block text-xs font-medium text-ash">
                        PIN (4~6자리)
                      </label>
                      <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="current-password"
                        maxLength={6}
                        value={loginPin}
                        onChange={(e) => setLoginPin(e.target.value.replace(/\D/g, ''))}
                        autoFocus
                        className={pinInputCls}
                        aria-label="PIN"
                      />
                    </>
                  )}
                  {loginError && <p className="mt-2 text-sm text-rose-400">{loginError}</p>}
                  <button
                    type="submit"
                    disabled={loginLoading}
                    className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-primary text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
                  >
                    {loginLoading && <CircleNotch size={16} className="animate-spin" />}
                    로그인
                  </button>
                </form>
              </div>
            )}
          </div>

          {/* 고객사·투자사 — 카카오 채널 가입·포털 접속(행동 버튼 포함) */}
          {!isPending && !(isAuthenticated && !pinSet) && (
            <div className="rounded-[24px] border border-hairline bg-graphite p-7">
              <div className="mb-3 flex items-center gap-3">
                <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#FEE500]">
                  <ChatCircleDots size={22} weight="fill" className="text-[#191919]" />
                </span>
                <h3 className="text-base font-bold text-bone">고객사·투자사이신가요?</h3>
              </div>
              <ol className="mb-4 space-y-1.5 text-sm leading-relaxed text-ash">
                <li>
                  <b className="text-bone">1.</b> 카카오톡에서{' '}
                  <b className="text-bone">후시파트너스 채널</b>을 추가합니다.
                </li>
                <li>
                  <b className="text-bone">2.</b> 담당자 확인 후 <b className="text-bone">알림톡으로
                  포털 이용권 링크</b>를 보내드립니다.
                </li>
                <li>
                  <b className="text-bone">3.</b> 링크를 누르면 끝 — 아이디·비밀번호가 없습니다.
                </li>
              </ol>
              <div className="flex flex-col gap-2 sm:flex-row">
                {loginConfig?.kakao_channel_url && (
                  <a
                    href={loginConfig.kakao_channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex h-11 flex-1 items-center justify-center gap-2 rounded-full bg-[#FEE500] text-sm font-bold text-[#191919] hover:brightness-95"
                  >
                    <ChatCircleDots size={18} weight="fill" />
                    카카오톡 채널 추가하기
                  </a>
                )}
                <a
                  href="/portal/login"
                  className="flex h-11 flex-1 items-center justify-center gap-2 rounded-full border border-hairline text-sm font-semibold text-bone hover:bg-elevate"
                >
                  포털 접속하기
                </a>
              </div>
              <p className="mt-3 text-center text-xs text-slatey">
                이미 링크를 받으셨다면 알림톡(또는 메일)의 버튼으로 바로 접속됩니다.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
