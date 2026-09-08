"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import { useEffect } from "react";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md rounded-[28px] border border-slate-200 bg-white p-8 text-center shadow-sm">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600">
          <AlertTriangle className="h-6 w-6" />
        </span>
        <h1 className="mt-4 text-xl font-semibold text-slate-900">Algo deu errado</h1>
        <p className="mt-2 text-sm text-slate-500">
          A tela encontrou um erro inesperado. Você pode tentar novamente ou recarregar a página.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
          >
            <RotateCcw className="h-4 w-4" />
            Tentar novamente
          </button>
          <button
            type="button"
            onClick={() => window.location.assign("/")}
            className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
          >
            Voltar ao início
          </button>
        </div>
      </div>
    </main>
  );
}
