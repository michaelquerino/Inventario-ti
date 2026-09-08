"use client";

import type { FormEvent } from "react";
import { useEffect } from "react";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { register } from "@/lib/api";
import { isSelfRegisterEnabled } from "@/lib/auth-config";

export default function RegisterPage() {
  const selfRegisterEnabled = isSelfRegisterEnabled();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!selfRegisterEnabled) {
      router.replace("/login");
    }
  }, [router, selfRegisterEnabled]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await register({ full_name: fullName, email, password });
      setSuccess("Cadastro realizado. Voce ja pode entrar.");
      setTimeout(() => router.push("/login"), 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no cadastro");
    } finally {
      setLoading(false);
    }
  }

  if (!selfRegisterEnabled) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
        <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-2xl">
          <h1 className="text-2xl font-semibold text-slate-900">Cadastro desabilitado</h1>
          <p className="mt-2 text-sm text-slate-600">
            Este ambiente opera em modo single-admin. Redirecionando para o login.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.3em] text-brand-600">
          IT Manager
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">Criar conta</h1>
        <p className="mt-2 text-sm text-slate-500">Preencha os dados para solicitar acesso.</p>

        <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Nome completo</label>
            <input
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              type="text"
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
              placeholder="Nome Sobrenome"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">E-mail</label>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
              placeholder="usuario@empresa.com"
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

          {error ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
          {success ? (
            <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p>
          ) : null}

          <button
            disabled={loading}
            className="h-11 w-full rounded-xl bg-brand-600 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {loading ? "Criando..." : "Criar conta"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          Ja tem conta?{" "}
          <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-700">
            Entrar
          </Link>
        </p>
      </div>
    </main>
  );
}
