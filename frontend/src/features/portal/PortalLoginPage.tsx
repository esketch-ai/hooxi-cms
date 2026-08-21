// Phase 4 포털 로그인 — 매직 링크 토큰(쿼리 ?token= / 해시 #token=) 자동 검증.
import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { CircleNotch, Leaf, WarningCircle } from '@phosphor-icons/react'
import { usePortalAuth } from './PortalAuthProvider'
import { useLoginConfig } from '../../lib/api/queries'

/** URL 쿼리(?token=) 또는 해시(#token=)에서 매직 토큰 추출 */
function readMagicToken(): string | null {
  const query = new URLSearchParams(window.location.search).get('token')
  if (query) return query
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : ''
  return new URLSearchParams(hash).get('token')
}

/** 검증 후 URL에서 토큰 흔적 제거 */
function stripTokenFromUrl() {
  window.history.replaceState(null, '', window.location.pathname)
}

export function PortalLoginPage() {
  const { data: loginConfig } = useLoginConfig()
  const kakaoUrl = loginConfig?.kakao_channel_url ?? null
  const { me, isLoading, verifyMagic } = usePortalAuth()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'checking' | 'verifying' | 'error'>('checking')
  const attempted = useRef(false)

  useEffect(() => {
    if (isLoading || me || attempted.current) return
    attempted.current = true
    const token = readMagicToken()
    if (!token) {
      setStatus('error')
      return
    }
    setStatus('verifying')
    verifyMagic(token)
      .then(() => {
        stripTokenFromUrl()
        navigate('/portal', { replace: true })
      })
      .catch(() => {
        stripTokenFromUrl()
        setStatus('error')
      })
  }, [isLoading, me, verifyMagic, navigate])

  // 이미 로그인된 상태로 접근 → 바로 포털
  if (me) return <Navigate to="/portal" replace />

  return (
    <div className="flex min-h-dvh items-center justify-center bg-void px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="hero-horizon mb-4 inline-flex h-16 w-16 items-center justify-center rounded-[20px]">
            <Leaf size={30} weight="fill" className="text-white" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-bone">후시 파트너 포털</h1>
        </div>

        <div className="animate-fade-in rounded-[24px] border border-hairline bg-graphite p-8 text-center">
          {status === 'error' ? (
            <div>
              <WarningCircle size={40} className="mx-auto mb-4 text-amber-400" />
              <p className="text-sm font-semibold text-bone">
                접속 링크가 없거나, 만료·무효 상태입니다.
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ash">
                포털은 담당자가 보내드린 <b className="text-bone">알림톡(또는 메일)의 링크</b>로
                접속합니다. 링크가 만료되었다면 재발급을 요청해 주세요.
              </p>
              {kakaoUrl && (
                <a
                  href={kakaoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-full bg-[#FEE500] text-sm font-bold text-[#191919] hover:brightness-95"
                >
                  카카오톡 채널로 문의·가입하기
                </a>
              )}
            </div>
          ) : (
            <div className="py-4">
              <CircleNotch size={28} className="mx-auto animate-spin text-slatey" />
              <p className="mt-4 text-sm text-ash">로그인 확인 중…</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
