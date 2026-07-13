import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { CircleNotch, HourglassMedium, Leaf, LockKey } from '@phosphor-icons/react'
import { useAuth, WorksNotReadyError } from '../../app/AuthProvider'
import { useToast } from '../../components/Toast'

export function LoginPage() {
  const {
    user,
    isLoading,
    isAuthenticated,
    isPending,
    pinSet,
    loginEmail,
    loginWithWorks,
    logout,
  } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [worksLoading, setWorksLoading] = useState(false)
  const [worksNotice, setWorksNotice] = useState<string | null>(null)
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

  // 이미 인증(ACTIVE + PIN 설정 완료) 상태로 /login 접근 → /dashboard
  if (isAuthenticated && pinSet) {
    return <Navigate to="/dashboard" replace />
  }

  const handleWorksLogin = async () => {
    setWorksNotice(null)
    setWorksLoading(true)
    try {
      await loginWithWorks() // 성공 시 리다이렉트되므로 이후 코드는 실행되지 않음
    } catch (error) {
      if (error instanceof WorksNotReadyError) {
        setWorksNotice('네이버웍스 연동 준비 중입니다. 잠시 후 다시 시도해 주세요.')
      } else {
        setWorksNotice('로그인을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.')
      }
    } finally {
      setWorksLoading(false)
    }
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
        navigate('/dashboard', { replace: true })
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
      navigate('/dashboard', { replace: true })
    } catch {
      setPinError('PIN 설정에 실패했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setPinLoading(false)
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-void px-4">
      <div className="w-full max-w-md">
        {/* 브랜드 — hero horizon 그라데이션 배지 + 로고 */}
        <div className="mb-6 text-center">
          <div className="hero-horizon mb-4 inline-flex h-16 w-16 items-center justify-center rounded-[20px]">
            <Leaf size={30} weight="fill" className="text-white" />
          </div>
          <div className="flex justify-center">
            <img
              src="/Hooxi-CMS_logo_trans.png"
              alt="Hooxi CMS"
              className="h-10 w-auto rounded-md dark:bg-white dark:px-2 dark:py-1"
            />
          </div>
          <p className="mt-2 text-sm text-ash">내부 관리 시스템</p>
        </div>

        <div className="animate-fade-in rounded-[24px] border border-hairline bg-graphite p-8">
          {isPending ? (
            /* 승인 대기 화면 (status=PENDING) */
            <div className="text-center">
              <HourglassMedium size={40} className="mx-auto mb-4 text-amber-400" />
              <h1 className="text-lg font-bold text-bone">
                가입 요청이 접수되었습니다
              </h1>
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
                <h1 className="text-lg font-bold text-bone">PIN 설정</h1>
                <p className="mt-1 text-sm text-ash">
                  미팅 모드·민감 정보 열람에 사용할 PIN(4~6자리 숫자)을 설정해
                  주세요.
                </p>
              </div>
              <label className="mb-1 block text-xs font-medium text-ash">
                PIN 입력
              </label>
              <input
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={6}
                value={pin1}
                onChange={(e) => setPin1(e.target.value.replace(/\D/g, ''))}
                className="mb-3 h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-center text-lg tracking-[0.5em] text-bone focus:border-white/30 focus:outline-none"
              />
              <label className="mb-1 block text-xs font-medium text-ash">
                PIN 다시 입력
              </label>
              <input
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={6}
                value={pin2}
                onChange={(e) => setPin2(e.target.value.replace(/\D/g, ''))}
                className="h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-center text-lg tracking-[0.5em] text-bone focus:border-white/30 focus:outline-none"
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
            /* 로그인 — 이메일+PIN (회사 도메인 제한) + 네이버웍스 SSO(보조) */
            <div>
              <form onSubmit={handleEmailLogin}>
                <label className="mb-1 block text-xs font-medium text-ash">
                  회사 이메일
                </label>
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
                  className="h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
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
                      className="h-11 w-full rounded-[10px] border border-hairline bg-elevate px-3 text-center text-lg tracking-[0.5em] text-bone focus:border-white/30 focus:outline-none"
                      aria-label="PIN"
                    />
                  </>
                )}
                {loginError && (
                  <p className="mt-2 text-sm text-rose-400">{loginError}</p>
                )}
                <button
                  type="submit"
                  disabled={loginLoading}
                  className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-primary text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
                >
                  {loginLoading && <CircleNotch size={16} className="animate-spin" />}
                  로그인
                </button>
              </form>

              <div className="my-5 flex items-center gap-3">
                <div className="h-px flex-1 bg-elevate-strong" />
                <span className="text-xs text-slatey">또는</span>
                <div className="h-px flex-1 bg-elevate-strong" />
              </div>

              <button
                type="button"
                onClick={handleWorksLogin}
                disabled={worksLoading}
                className="flex h-11 w-full items-center justify-center gap-2.5 rounded-lg bg-[#03c75a] text-sm font-semibold text-white hover:brightness-95 disabled:opacity-60"
              >
                {worksLoading ? (
                  <CircleNotch size={18} className="animate-spin" />
                ) : (
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-white text-xs font-black text-[#03c75a]">
                    N
                  </span>
                )}
                네이버웍스로 로그인
              </button>
              {worksNotice && (
                <p className="mt-3 rounded-[10px] border border-amber-400/25 bg-amber-500/15 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                  {worksNotice}
                </p>
              )}
              <p className="mt-4 text-center text-xs leading-relaxed text-slatey">
                회사 계정(@hooxipartners.com)으로 로그인합니다
                <br />
                최초 로그인 시 가입 신청 후 관리자 승인이 필요합니다
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
