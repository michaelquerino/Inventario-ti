"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { login } from "@/lib/api";
import { isSelfRegisterEnabled } from "@/lib/auth-config";
import { setToken } from "@/lib/session";

export default function LoginPage() {
  const selfRegisterEnabled = isSelfRegisterEnabled();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const token = await login(email, password);
      setToken(token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.3em] text-brand-600">
          IT Manager
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">Acessar sistema</h1>
        <p className="mt-2 text-sm text-slate-500">
          Entre com sua conta administrativa para gerenciar ativos, auditoria e monitoramento.
        </p>

        <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">E-mail</label>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
              placeholder="admin@empresa.com"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Senha</label>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
              placeholder="••••••••"
              required
            />
          </div>

          {error ? (
            <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
          ) : null}

          <button
            disabled={loading}
            className="h-11 w-full rounded-xl bg-brand-600 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        {selfRegisterEnabled ? (
          <p className="mt-6 text-center text-sm text-slate-600">
            Nao tem conta?{" "}
            <Link href="/register" className="font-semibold text-brand-600 hover:text-brand-700">
              Cadastre-se
            </Link>
          </p>
        ) : (
          <p className="mt-6 text-center text-sm text-slate-600">
            Cadastro de novos usuarios esta desabilitado neste ambiente inicial (single-admin).
          </p>
        )}
      </div>
    </main>
  );
}
