"use client";

import { CheckCircle2, LifeBuoy } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { getAgentIdentity, type AgentIdentity } from "@/lib/agent-identity";
import { createTicket } from "@/lib/tickets-api";

const categorias = ["Hardware", "Software", "Rede/Internet", "Acesso/Senha", "Outro"];

type EstadoIdentidade = "verificando" | "encontrada" | "nao_encontrada";

export default function ChamadosPage() {
  const [estadoIdentidade, setEstadoIdentidade] = useState<EstadoIdentidade>("verificando");
  const [identidade, setIdentidade] = useState<AgentIdentity | null>(null);
  const [usuarioManual, setUsuarioManual] = useState("");
  const [titulo, setTitulo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [categoria, setCategoria] = useState(categorias[0]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [enviado, setEnviado] = useState(false);

  useEffect(() => {
    let ativo = true;
    getAgentIdentity().then((resultado) => {
      if (!ativo) return;
      if (resultado && resultado.numero_serie) {
        setIdentidade(resultado);
        setEstadoIdentidade("encontrada");
      } else {
        setEstadoIdentidade("nao_encontrada");
      }
    });
    return () => {
      ativo = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErro("");

    if (!titulo.trim() || !descricao.trim()) {
      setErro("Preencha o título e a descrição do chamado.");
      return;
    }
    if (estadoIdentidade === "nao_encontrada" && !usuarioManual.trim()) {
      setErro("Não conseguimos identificar seu notebook automaticamente. Informe seu nome.");
      return;
    }

    setEnviando(true);
    try {
      await createTicket({
        numero_serie: identidade?.numero_serie ?? null,
        usuario: identidade?.usuario || usuarioManual.trim() || null,
        patrimonio: identidade?.patrimonio ?? null,
        titulo: titulo.trim(),
        descricao: descricao.trim(),
        categoria,
      });
      setEnviado(true);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao enviar o chamado. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  if (enviado) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
        <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-2xl">
          <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-500" />
          <h1 className="mt-4 text-2xl font-semibold text-slate-900">Chamado enviado</h1>
          <p className="mt-2 text-sm text-slate-500">
            Recebemos sua solicitação e a equipe de TI vai analisar em breve.
          </p>
          <button
            onClick={() => {
              setEnviado(false);
              setTitulo("");
              setDescricao("");
              setCategoria(categorias[0]);
            }}
            className="mt-6 h-11 w-full rounded-xl bg-brand-600 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            Abrir outro chamado
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <div className="w-full max-w-lg rounded-3xl bg-white p-8 shadow-2xl">
        <div className="flex items-center gap-2 text-brand-600">
          <LifeBuoy className="h-5 w-5" />
          <p className="text-sm font-semibold uppercase tracking-[0.3em]">Suporte de TI</p>
        </div>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">Abrir chamado</h1>
        <p className="mt-2 text-sm text-slate-500">
          Descreva o problema ou solicitação. Não é necessário fazer login.
        </p>

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          {estadoIdentidade === "verificando" ? (
            <p className="text-slate-500">Identificando seu notebook...</p>
          ) : estadoIdentidade === "encontrada" ? (
            <p className="text-slate-700">
              Abrindo como <span className="font-semibold">{identidade?.usuario || identidade?.numero_serie}</span>
              {identidade?.patrimonio ? ` · patrimônio ${identidade.patrimonio}` : ""}
            </p>
          ) : (
            <div>
              <p className="text-amber-700">
                Não conseguimos identificar seu notebook automaticamente (agente não encontrado nesta máquina).
              </p>
              <label className="mt-2 block text-sm font-medium text-slate-700">Seu nome</label>
              <input
                value={usuarioManual}
                onChange={(event) => setUsuarioManual(event.target.value)}
                className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-brand-500"
                placeholder="Como podemos te chamar"
              />
            </div>
          )}
        </div>

        <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Categoria</label>
            <select
              value={categoria}
              onChange={(event) => setCategoria(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
            >
              {categorias.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Título</label>
            <input
              value={titulo}
              onChange={(event) => setTitulo(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-brand-500"
              placeholder="Resumo curto do problema"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Descrição</label>
            <textarea
              value={descricao}
              onChange={(event) => setDescricao(event.target.value)}
              rows={5}
              className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-brand-500"
              placeholder="Descreva com detalhes o que está acontecendo"
              required
            />
          </div>

          {erro ? <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{erro}</p> : null}

          <button
            disabled={enviando}
            className="h-11 w-full rounded-xl bg-brand-600 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {enviando ? "Enviando..." : "Enviar chamado"}
          </button>
        </form>
      </div>
    </main>
  );
}
