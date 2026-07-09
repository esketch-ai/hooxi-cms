import { Wrench } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'

interface PlaceholderPageProps {
  title: string
  subtitle: string
  /** 구현 예정 Phase (플랜 §2.1 우선순위) */
  phase: 'P1' | 'P2' | 'P3'
}

export function PlaceholderPage({ title, subtitle, phase }: PlaceholderPageProps) {
  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader title={title} subtitle={subtitle} />
      <EmptyState
        icon={<Wrench size={36} />}
        title={`${phase} 구현 예정`}
        description={`${title} 화면은 ${phase} 단계에서 구현됩니다.`}
      />
    </div>
  )
}
