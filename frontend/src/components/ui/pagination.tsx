"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

type PaginationProps = {
  page: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  /** Usa quando o pai já tem padding próprio (evita padding horizontal duplicado). */
  bare?: boolean;
};

export function Pagination({ page, totalItems, pageSize, onPageChange, bare = false }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  if (totalPages <= 1) return null;

  const inicio = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const fim = Math.min(page * pageSize, totalItems);

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 text-sm ${
        bare ? "mt-4 pt-3" : "px-5 py-3"
      }`}
    >
      <p className="text-slate-500">
        {inicio}–{fim} de {totalItems}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Página anterior"
          className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 text-slate-600 disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-slate-600">
          Página {page} de {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Próxima página"
          className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 text-slate-600 disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
