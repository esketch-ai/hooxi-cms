// 사용자 가이드 — /guide 부모 레이아웃. 공유 크롬은 최소화하고 하위 라우트를 Outlet으로 렌더.
import { Outlet } from 'react-router-dom'

export function GuideLayout() {
  return (
    <div className="animate-fade-in">
      <Outlet />
    </div>
  )
}
