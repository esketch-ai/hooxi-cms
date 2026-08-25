// 세금계산서 원장 API 훅 — backend /tax-invoices 계약 준수
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  TaxInvoiceCommitResponse,
  TaxInvoiceFilters,
  TaxInvoiceListResponse,
  TaxInvoicePreviewResponse,
  TaxInvoiceSummary,
  TaxInvoiceIssueCounts,
} from './types'

export function useTaxInvoices(filters: TaxInvoiceFilters) {
  return useQuery({
    queryKey: ['tax-invoices', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.direction) params.direction = filters.direction
      if (filters.search) params.search = filters.search
      if (filters.issue) params.issue = filters.issue
      const { data } = await api.get<TaxInvoiceListResponse>('/tax-invoices', { params })
      return data
    },
    placeholderData: (prev) => prev,
  })
}

export function useTaxInvoiceSummary(range: { date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: ['tax-invoices', 'summary', range],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (range.date_from) params.date_from = range.date_from
      if (range.date_to) params.date_to = range.date_to
      const { data } = await api.get<TaxInvoiceSummary>('/tax-invoices/summary', { params })
      return data
    },
    placeholderData: (prev) => prev,
  })
}

export function useTaxInvoiceIssueCounts(range: { date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: ['tax-invoices', 'issue-counts', range],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (range.date_from) params.date_from = range.date_from
      if (range.date_to) params.date_to = range.date_to
      const { data } = await api.get<TaxInvoiceIssueCounts>('/tax-invoices/issue-counts', { params })
      return data
    },
  })
}

function toFormData(files: File[]): FormData {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  return fd
}

export function usePreviewTaxInvoices() {
  return useMutation({
    mutationFn: async (files: File[]) => {
      const { data } = await api.post<TaxInvoicePreviewResponse>(
        '/tax-invoices/preview',
        toFormData(files),
      )
      return data
    },
  })
}

export function useCommitTaxInvoices() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      const { data } = await api.post<TaxInvoiceCommitResponse>(
        '/tax-invoices/commit',
        toFormData(files),
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tax-invoices'] }),
  })
}

// Dropbox 정산 폴더 스캔 — folder 비우면 백엔드 config 기본값 사용
export function usePreviewScan() {
  return useMutation({
    mutationFn: async (folder: string) => {
      const { data } = await api.post<TaxInvoicePreviewResponse>(
        '/tax-invoices/scan/preview',
        null,
        { params: folder ? { folder } : {} },
      )
      return data
    },
  })
}

export function useCommitScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (folder: string) => {
      const { data } = await api.post<TaxInvoiceCommitResponse>(
        '/tax-invoices/scan/commit',
        null,
        { params: folder ? { folder } : {} },
      )
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tax-invoices'] }),
  })
}
