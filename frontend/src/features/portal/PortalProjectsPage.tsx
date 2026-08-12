// Phase 4 포털 — 참여 프로젝트 목록
import { Link } from 'react-router-dom'
import { CaretRight, FolderOpen } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCards } from '../../components/Skeleton'
import { StatusBadge } from '../../components/StatusBadge'
import { usePortalProjects } from './api'

export function PortalProjectsPage() {
  const { data, isLoading, isError } = usePortalProjects()

  return (
    <div className="space-y-5">
      <PageHeader title="참여 프로젝트" subtitle="참여 중인 감축 사업의 진행 현황을 확인하세요." />

      {isLoading ? (
        <SkeletonCards count={3} />
      ) : isError ? (
        <EmptyState
          icon={<FolderOpen size={40} />}
          title="목록을 불러오지 못했습니다"
          description="잠시 후 다시 시도해 주세요."
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          icon={<FolderOpen size={40} />}
          title="참여 중인 프로젝트가 없습니다"
          description="새로운 사업 참여가 확정되면 이곳에 표시됩니다."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.map((p) => (
            <Link
              key={p.project_id}
              to={`/portal/projects/${p.project_id}`}
              className="group flex items-center justify-between gap-3 rounded-3xl border border-hairline bg-graphite p-5 hover:border-hairline-strong hover:bg-elevate"
            >
              <div className="min-w-0">
                <p className="truncate text-base font-semibold text-bone">{p.project_name}</p>
                <div className="mt-2">
                  <StatusBadge domain="project" value={p.project_status} />
                </div>
              </div>
              <CaretRight size={18} className="shrink-0 text-slatey group-hover:text-bone" />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
