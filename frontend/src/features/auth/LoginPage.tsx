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
    loginDev,
    loginWithWorks,
    logout,
  } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [worksLoading, setWorksLoading] = useState(false)
  const [worksNotice, setWorksNotice] = useState<string | null>(null)
  const [devEmail, setDevEmail] = useState('')
  const [devLoading, setDevLoading] = useState(false)
  const [devError, setDevError] = useState<string | null>(null)

  // PIN 설정 스텝 (R2-C11: 최초 ACTIVE 로그인 시 필수)
  const [pin1, setPin1] = useState('')
  const [pin2, setPin2] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  const [pinLoading, setPinLoading] = useState(false)
  const { setPin } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-slate-50">
        <CircleNotch size={28} className="animate-spin text-slate-400" />
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

  const handleDevLogin = async (e: FormEvent) => {
    e.preventDefault()
    setDevError(null)
    if (!devEmail.trim()) {
      setDevError('이메일을 입력해 주세요.')
      return
    }
    setDevLoading(true)
    try {
      const me = await loginDev(devEmail.trim())
      if (me.status === 'ACTIVE' && me.pin_set) {
        navigate('/dashboard', { replace: true })
      }
      // PENDING·PIN 미설정은 아래 렌더 분기에서 처리
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        setDevError('로그인할 수 없는 계정입니다.')
      } else {
        setDevError('로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.')
      }
    } finally {
      setDevLoading(false)
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
    <div className="flex min-h-dvh items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        {/* 브랜드 */}
        <div className="mb-6 text-center">
          <div className="mb-2 inline-flex items-center gap-2">
            <Leaf size={28} weight="fill" className="text-emerald-500" />
            <span className="text-2xl font-bold tracking-tight text-slate-900">
              Carbon Fleet
            </span>
          </div>
          <p className="text-sm text-slate-500">Hooxi CMS 내부 시스템</p>
        </div>

        <div className="animate-fade-in rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          {isPending ? (
            /* 승인 대기 화면 (status=PENDING) */
            <div className="text-center">
              <HourglassMedium size={40} className="mx-auto mb-4 text-amber-500" />
              <h1 className="text-lg font-bold text-slate-900">
                가입 요청이 접수되었습니다
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                관리자 승인 후 이용할 수 있습니다.
                <br />
                승인이 완료되면 알림으로 안내됩니다.
              </p>
              <p className="mt-4 text-xs text-slate-400">{user?.email}</p>
              <button
                type="button"
                onClick={logout}
                className="mt-6 w-full rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
              >
                다른 계정으로 로그인
              </button>
            </div>
          ) : isAuthenticated && !pinSet ? (
            /* PIN 설정 스텝 (최초 ACTIVE 로그인) */
            <form onSubmit={handlePinSubmit}>
              <div className="mb-5 text-center">
                <LockKey size={36} className="mx-auto mb-3 text-slate-700" />
                <h1 className="text-lg font-bold text-slate-900">PIN 설정</h1>
                <p className="mt-1 text-sm text-slate-500">
                  미팅 모드·민감 정보 열람에 사용할 PIN(4~6자리 숫자)을 설정해
                  주세요.
                </p>
              </div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                PIN 입력
              </label>
              <input
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={6}
                value={pin1}
                onChange={(e) => setPin1(e.target.value.replace(/\D/g, ''))}
                className="mb-3 h-11 w-full rounded-lg border border-slate-200 px-3 text-center text-lg tracking-[0.5em] focus:border-slate-500 focus:outline-none"
              />
              <label className="mb-1 block text-xs font-medium text-slate-600">
                PIN 다시 입력
              </label>
              <input
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                maxLength={6}
                value={pin2}
                onChange={(e) => setPin2(e.target.value.replace(/\D/g, ''))}
                className="h-11 w-full rounded-lg border border-slate-200 px-3 text-center text-lg tracking-[0.5em] focus:border-slate-500 focus:outline-none"
              />
              {pinError && <p className="mt-2 text-sm text-rose-600">{pinError}</p>}
              <button
                type="submit"
                disabled={pinLoading}
                className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-800 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
              >
                {pinLoading && <CircleNotch size={16} className="animate-spin" />}
                PIN 설정 완료
              </button>
            </form>
          ) : (
            /* 로그인 (네이버웍스 SSO — 유일한 진입 수단) */
            <div>
              <button
                type="button"
                onClick={handleWorksLogin}
                disabled={worksLoading}
                className="flex h-12 w-full items-center justify-center gap-2.5 rounded-lg bg-[#03c75a] text-sm font-semibold text-white hover:brightness-95 disabled:opacity-60"
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
                <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                  {worksNotice}
                </p>
              )}
              <p className="mt-4 text-center text-xs leading-relaxed text-slate-400">
                회사 계정(@hooxipartners.com)으로 로그인합니다
                <br />
                문의: 시스템 관리자(내선)
              </p>

              {/* 개발 로그인 — DEV 빌드에서만 노출 */}
              {import.meta.env.DEV && (
                <form
                  onSubmit={handleDevLogin}
                  className="mt-6 border-t border-dashed border-slate-200 pt-5"
                >
                  <p className="mb-2 text-xs font-semibold tracking-wider text-slate-400 uppercase">
                    개발 로그인 (DEV 전용)
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      value={devEmail}
                      onChange={(e) => setDevEmail(e.target.value)}
                      placeholder="name@hooxipartners.com"
                      className="h-10 flex-1 rounded-lg border border-slate-200 px-3 text-sm focus:border-slate-500 focus:outline-none"
                      aria-label="개발 로그인 이메일"
                    />
                    <button
                      type="submit"
                      disabled={devLoading}
                      className="h-10 shrink-0 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                    >
                      {devLoading ? (
                        <CircleNotch size={16} className="animate-spin" />
                      ) : (
                        '로그인'
                      )}
                    </button>
                  </div>
                  {devError && (
                    <p className="mt-2 text-sm text-rose-600">{devError}</p>
                  )}
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
