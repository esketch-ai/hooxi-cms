// 세금계산서 원장 API 훅 — backend /tax-invoices 계약 준수
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  TaxInvoiceCommitResponse,
  TaxInvoiceFilters,
  TaxInvoiceListResponse,
  TaxInvoicePreviewResponse,
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
      const { data } = await api.get<TaxInvoiceListResponse>('/tax-invoices', { params })
      return data
    },
    placeholderData: (prev) => prev,
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
