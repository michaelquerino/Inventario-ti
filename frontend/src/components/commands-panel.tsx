"use client";

import { Ban, BookmarkPlus, CheckSquare, Clock, DownloadCloud, FileBadge2, ShieldAlert, Square, Trash2 } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  cancelCommand,
  createCommand,
  createCommandTemplate,
  deleteCommand,
  deleteCommandTemplate,
  getAgentUpdateScript,
  listCommands,
  listCommandTemplates,
  type CommandTemplate,
  type RemoteCommand,
} from "@/lib/commands-api";
import type { MonitoringItem } from "@/lib/monitoring-api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pagination } from "@/components/ui/pagination";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { SkeletonCards } from "@/components/ui/skeleton";

type CommandsPanelProps = {
  monitoringItems: MonitoringItem[];
};

const statusLabel: Record<RemoteCommand["status"], string> = {
  pendente: "Pendente",
  executando: "Executando",
  concluido: "Concluído",
  erro: "Erro",
};

const statusTone: Record<RemoteCommand["status"], BadgeTone> = {
  pendente: "neutral",
  executando: "warning",
  concluido: "success",
  erro: "danger",
};

const filtroStatusOpcoes: Array<{ value: "todos" | RemoteCommand["status"]; label: string }> = [
  { value: "todos", label: "Todos" },
  { value: "pendente", label: "Pendentes" },
  { value: "executando", label: "Executando" },
  { value: "concluido", label: "Concluídos" },
  { value: "erro", label: "Erro" },
];

const certStoreOpcoes = [
  { value: "Root", label: "Autoridades Raiz Confiáveis" },
  { value: "CA", label: "Autoridades Intermediárias" },
  { value: "TrustedPeople", label: "Pessoas Confiáveis" },
];

const certEscopoOpcoes: Array<{ value: "CurrentUser" | "LocalMachine"; label: string }> = [
  { value: "CurrentUser", label: "Usuário atual (sem admin)" },
  { value: "LocalMachine", label: "Máquina local (requer admin)" },
];

const HISTORICO_PAGE_SIZE = 15;

const pastaBaseOpcoes: Array<{ value: string; label: string; expr: string }> = [
  { value: "Temp", label: "Temporária (%TEMP%)", expr: "$env:TEMP" },
  { value: "Desktop", label: "Área de trabalho", expr: "([Environment]::GetFolderPath('Desktop'))" },
  { value: "Documents", label: "Documentos", expr: "([Environment]::GetFolderPath('MyDocuments'))" },
];

const EXTENSOES_CERTIFICADO = [".cer", ".crt", ".pem", ".der"];
const EXTENSOES_PFX = [".pfx", ".p12"];

// O arquivo vira base64 embutido dentro do próprio comando PowerShell, que é
// executado via `powershell -Command <texto>` (linha de comando do Windows,
// limite prático de ~32.700 caracteres). 20 KB de arquivo vira ~27 KB em
// base64, deixando folga suficiente pro resto do script.
const TAMANHO_MAX_ARQUIVO = 20 * 1024;

function arrayBufferParaBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binario = "";
  const tamanhoBloco = 0x8000;
  for (let i = 0; i < bytes.length; i += tamanhoBloco) {
    binario += String.fromCharCode(...bytes.subarray(i, i + tamanhoBloco));
  }
  return btoa(binario);
}

function escaparLiteralPs(texto: string): string {
  return texto.replace(/'/g, "''");
}

function gerarScriptArquivo(
  base64: string,
  nomeArquivo: string,
  pastaBaseExpr: string,
  subpasta: string,
  instalarComoCertificado: boolean,
  store: string,
  escopo: "CurrentUser" | "LocalMachine",
  ehPfx: boolean,
  senhaPfx: string,
): string {
  const nomeSeguro = escaparLiteralPs(nomeArquivo.replace(/[^a-zA-Z0-9 ._-]/g, "") || "arquivo");
  const subpastaLimpa = subpasta.trim();
  // Só é seguro apagar/ocultar a pasta inteira quando ela foi criada só pra
  // essa operação (subpasta dedicada). Sem subpasta, o arquivo cai direto na
  // pasta base (Desktop/Documentos/Temp) e só ELE é ocultado/removido depois
  // -- nunca a pasta base inteira.
  const temSubpastaDedicada = subpastaLimpa.length > 0;
  const pastaExpr = temSubpastaDedicada
    ? `(Join-Path ${pastaBaseExpr} '${escaparLiteralPs(subpastaLimpa)}')`
    : pastaBaseExpr;

  const linhas = [
    `$b64 = '${base64}'`,
    "$bytes = [Convert]::FromBase64String($b64)",
    `$pastaDestino = ${pastaExpr}`,
    "$destino = Join-Path $pastaDestino '" + nomeSeguro + "'",
    "New-Item -ItemType Directory -Force -Path $pastaDestino | Out-Null",
  ];

  if (temSubpastaDedicada) {
    linhas.push(
      "$itemPasta = Get-Item -LiteralPath $pastaDestino -Force",
      "$itemPasta.Attributes = $itemPasta.Attributes -bor [IO.FileAttributes]::Hidden",
    );
  }

  linhas.push(
    "[IO.File]::WriteAllBytes($destino, $bytes)",
    "$itemArquivo = Get-Item -LiteralPath $destino -Force",
    "$itemArquivo.Attributes = $itemArquivo.Attributes -bor [IO.FileAttributes]::Hidden",
  );

  const linhaLimpeza = temSubpastaDedicada
    ? "Remove-Item -LiteralPath $pastaDestino -Force -Recurse -ErrorAction SilentlyContinue"
    : "Remove-Item -LiteralPath $destino -Force -ErrorAction SilentlyContinue";

  if (instalarComoCertificado && ehPfx) {
    linhas.push(
      `$senhaSegura = ConvertTo-SecureString -String '${escaparLiteralPs(senhaPfx)}' -AsPlainText -Force`,
      `Import-PfxCertificate -FilePath $destino -CertStoreLocation 'Cert:\\${escopo}\\My' -Password $senhaSegura | Out-Null`,
      linhaLimpeza,
      `Write-Output 'Certificado PFX instalado em ${escopo}\\My e arquivo temporário removido.'`,
    );
  } else if (instalarComoCertificado) {
    linhas.push(
      `Import-Certificate -FilePath $destino -CertStoreLocation 'Cert:\\${escopo}\\${store}' | Out-Null`,
      linhaLimpeza,
      `Write-Output 'Certificado instalado em ${escopo}\\${store} e arquivo temporário removido.'`,
    );
  } else {
    linhas.push(
      "",
      "# <<< Cole aqui o comando de instalação, usando $destino como caminho do arquivo. Ex:",
      "# Import-PfxCertificate -FilePath $destino -CertStoreLocation Cert:\\CurrentUser\\My -Password (ConvertTo-SecureString 'SUA_SENHA' -AsPlainText -Force)",
      "",
      linhaLimpeza,
      'Write-Output "Arquivo processado e removido: $destino"',
    );
  }

  return linhas.join("\n");
}

function abrirEmNovaJanela(conteudo: string): void {
  const blob = new Blob([conteudo], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const novaJanela = window.open(url, "_blank", "noopener,noreferrer");
  if (!novaJanela) {
    URL.revokeObjectURL(url);
    return;
  }
  // dá tempo da nova janela carregar o conteúdo antes de liberar a memória do blob
  window.setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function primeiraLinha(texto: string): string {
  return texto.split("\n")[0] || texto;
}

function toLocalDatetimeInputMin(): string {
  const now = new Date();
  now.setSeconds(0, 0);
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

export function CommandsPanel({ monitoringItems }: CommandsPanelProps) {
  const [displayNames, setDisplayNames] = useState<Record<string, string>>({});
  const [comando, setComando] = useState("");
  const [filtro, setFiltro] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [agendar, setAgendar] = useState(false);
  const [agendadoPara, setAgendadoPara] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");
  const [historico, setHistorico] = useState<RemoteCommand[]>([]);
  const [historicoCarregando, setHistoricoCarregando] = useState(true);
  const [carregandoScriptAtualizacao, setCarregandoScriptAtualizacao] = useState(false);
  const [templates, setTemplates] = useState<CommandTemplate[]>([]);
  const [templatesCarregando, setTemplatesCarregando] = useState(true);
  const [salvandoTemplate, setSalvandoTemplate] = useState(false);
  const [nomeTemplate, setNomeTemplate] = useState("");
  const [templateSelecionadoId, setTemplateSelecionadoId] = useState("");
  const [modo, setModo] = useState<"usuario" | "admin">("usuario");
  const [filtroStatus, setFiltroStatus] = useState<"todos" | RemoteCommand["status"]>("todos");
  const [excluindoId, setExcluindoId] = useState<number | null>(null);
  const [cancelandoId, setCancelandoId] = useState<number | null>(null);
  const [abaHistorico, setAbaHistorico] = useState<"recentes" | "pendentes_offline">("recentes");
  const [arquivoEscolhido, setArquivoEscolhido] = useState<{ nome: string; base64: string } | null>(null);
  const [pastaBase, setPastaBase] = useState(pastaBaseOpcoes[0].value);
  const [subpastaDestino, setSubpastaDestino] = useState("");
  const [instalarComoCertificado, setInstalarComoCertificado] = useState(false);
  const [certStore, setCertStore] = useState("Root");
  const [certEscopo, setCertEscopo] = useState<"CurrentUser" | "LocalMachine">("CurrentUser");
  const [senhaPfx, setSenhaPfx] = useState("");
  const [processandoArquivo, setProcessandoArquivo] = useState(false);
  const [confirmacaoEnvio, setConfirmacaoEnvio] = useState<{ comandoTexto: string; agendadoIso?: string } | null>(
    null,
  );
  const [historicoPage, setHistoricoPage] = useState(1);

  const arquivoEhPfx = useMemo(() => {
    if (!arquivoEscolhido) return false;
    const extensao = arquivoEscolhido.nome.slice(arquivoEscolhido.nome.lastIndexOf(".")).toLowerCase();
    return EXTENSOES_PFX.includes(extensao);
  }, [arquivoEscolhido]);

  useEffect(() => {
    const nomes: Record<string, string> = {};
    for (const item of monitoringItems) {
      nomes[item.numero_serie] = item.usuario || item.numero_serie;
    }
    setDisplayNames(nomes);
  }, [monitoringItems]);

  const onlineStatusMap = useMemo(() => {
    const mapa: Record<string, MonitoringItem["online_status"]> = {};
    for (const item of monitoringItems) {
      mapa[item.numero_serie] = item.online_status;
    }
    return mapa;
  }, [monitoringItems]);

  async function refreshHistorico() {
    setHistoricoCarregando(true);
    try {
      const dados = await listCommands(undefined, 100);
      setHistorico(dados);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao carregar histórico de comandos");
    } finally {
      setHistoricoCarregando(false);
    }
  }

  useEffect(() => {
    void refreshHistorico();
  }, []);

  // Atualização automática: pra acompanhar Pendente -> Executando -> Concluído/Erro
  // sem precisar ficar clicando em "Atualizar" enquanto o agente processa o comando.
  // Pendente de notebook offline não entra nessa conta: não tem previsão de rodar
  // (só no próximo checkin, que pode nunca vir), então não justifica ficar recarregando.
  useEffect(() => {
    const temPendencia = historico.some(
      (cmd) =>
        cmd.status === "executando" ||
        (cmd.status === "pendente" && onlineStatusMap[cmd.numero_serie] === "online"),
    );
    const intervalo = window.setInterval(() => {
      void refreshHistorico();
    }, temPendencia ? 5000 : 20000);

    return () => window.clearInterval(intervalo);
  }, [historico, onlineStatusMap]);

  async function refreshTemplates() {
    setTemplatesCarregando(true);
    try {
      const dados = await listCommandTemplates();
      setTemplates(dados);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao carregar biblioteca de comandos");
    } finally {
      setTemplatesCarregando(false);
    }
  }

  useEffect(() => {
    void refreshTemplates();
  }, []);

  async function handleSalvarTemplate() {
    const comandoTexto = comando.trim();
    const nome = nomeTemplate.trim();
    if (!comandoTexto) {
      setErro("Digite um comando antes de salvar na biblioteca.");
      return;
    }
    if (!nome) {
      setErro("Digite um nome para salvar o comando na biblioteca.");
      return;
    }

    setErro("");
    setSucesso("");
    setSalvandoTemplate(true);
    try {
      await createCommandTemplate(nome, comandoTexto);
      setSucesso(`Comando "${nome}" salvo na biblioteca.`);
      setNomeTemplate("");
      await refreshTemplates();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao salvar comando na biblioteca");
    } finally {
      setSalvandoTemplate(false);
    }
  }

  function handleSelecionarTemplate(id: string) {
    setTemplateSelecionadoId(id);
    const tpl = templates.find((t) => String(t.id) === id);
    if (tpl) setComando(tpl.comando);
  }

  async function handleExcluirTemplateSelecionado() {
    if (!templateSelecionadoId) return;
    setErro("");
    try {
      await deleteCommandTemplate(Number(templateSelecionadoId));
      setTemplateSelecionadoId("");
      await refreshTemplates();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao excluir comando salvo");
    }
  }

  function ehPendenteOffline(cmd: RemoteCommand): boolean {
    return cmd.status === "pendente" && onlineStatusMap[cmd.numero_serie] !== "online";
  }

  const historicoRecentes = useMemo(() => historico.filter((cmd) => !ehPendenteOffline(cmd)), [historico, onlineStatusMap]);
  const historicoPendentesOffline = useMemo(
    () => historico.filter((cmd) => ehPendenteOffline(cmd)),
    [historico, onlineStatusMap],
  );

  const historicoFiltrado = useMemo(() => {
    const base = abaHistorico === "recentes" ? historicoRecentes : historicoPendentesOffline;
    if (filtroStatus === "todos" || abaHistorico === "pendentes_offline") return base;
    return base.filter((cmd) => cmd.status === filtroStatus);
  }, [historicoRecentes, historicoPendentesOffline, abaHistorico, filtroStatus]);

  useEffect(() => {
    setHistoricoPage(1);
  }, [abaHistorico, filtroStatus]);

  const historicoPaginado = useMemo(
    () => historicoFiltrado.slice((historicoPage - 1) * HISTORICO_PAGE_SIZE, historicoPage * HISTORICO_PAGE_SIZE),
    [historicoFiltrado, historicoPage],
  );

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(historicoFiltrado.length / HISTORICO_PAGE_SIZE));
    if (historicoPage > totalPages) setHistoricoPage(totalPages);
  }, [historicoFiltrado.length, historicoPage]);

  async function handleExcluirComando(cmd: RemoteCommand) {
    setErro("");
    setExcluindoId(cmd.id);
    try {
      await deleteCommand(cmd.id);
      await refreshHistorico();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao excluir comando");
    } finally {
      setExcluindoId(null);
    }
  }

  async function handleCancelarComando(cmd: RemoteCommand) {
    setErro("");
    setCancelandoId(cmd.id);
    try {
      await cancelCommand(cmd.id);
      await refreshHistorico();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao cancelar comando");
    } finally {
      setCancelandoId(null);
    }
  }

  const notebooksFiltrados = useMemo(() => {
    const termo = filtro.trim().toLowerCase();
    const copia = [...monitoringItems].sort((a, b) =>
      (displayNames[a.numero_serie] || "").localeCompare(displayNames[b.numero_serie] || ""),
    );
    if (!termo) return copia;
    return copia.filter((item) => {
      const nome = (displayNames[item.numero_serie] || "").toLowerCase();
      return nome.includes(termo) || item.numero_serie.toLowerCase().includes(termo) || (item.modelo || "").toLowerCase().includes(termo);
    });
  }, [monitoringItems, filtro, displayNames]);

  const nomesSelecionadosResumo = useMemo(() => {
    const nomes = Array.from(selecionados).map((serie) => displayNames[serie] || serie);
    const LIMITE = 4;
    if (nomes.length <= LIMITE) return nomes.join(", ");
    return `${nomes.slice(0, LIMITE).join(", ")} e mais ${nomes.length - LIMITE}`;
  }, [selecionados, displayNames]);

  const todosFiltradosSelecionados =
    notebooksFiltrados.length > 0 && notebooksFiltrados.every((item) => selecionados.has(item.numero_serie));

  function alternarSelecao(numeroSerie: string) {
    setSelecionados((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(numeroSerie)) {
        proximo.delete(numeroSerie);
      } else {
        proximo.add(numeroSerie);
      }
      return proximo;
    });
  }

  function alternarTodos() {
    setSelecionados((atual) => {
      if (todosFiltradosSelecionados) {
        const proximo = new Set(atual);
        for (const item of notebooksFiltrados) proximo.delete(item.numero_serie);
        return proximo;
      }
      const proximo = new Set(atual);
      for (const item of notebooksFiltrados) proximo.add(item.numero_serie);
      return proximo;
    });
  }

  async function preencherScriptAtualizacao() {
    setErro("");
    setSucesso("");
    setCarregandoScriptAtualizacao(true);
    try {
      const script = await getAgentUpdateScript();
      setComando(script);
      setSucesso(
        "Script de atualização carregado no campo de comando. Confira e selecione os notebooks antes de enviar.",
      );
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao carregar script de atualização");
    } finally {
      setCarregandoScriptAtualizacao(false);
    }
  }

  async function handleArquivoEscolhido(event: ChangeEvent<HTMLInputElement>) {
    const arquivo = event.target.files?.[0];
    event.target.value = "";
    if (!arquivo) return;

    setErro("");
    setSucesso("");

    if (arquivo.size > TAMANHO_MAX_ARQUIVO) {
      setErro(
        `Arquivo muito grande (${Math.ceil(arquivo.size / 1024)} KB). O limite é ~${Math.floor(TAMANHO_MAX_ARQUIVO / 1024)} KB, porque ele viaja embutido dentro do próprio comando.`,
      );
      return;
    }

    setProcessandoArquivo(true);
    try {
      const buffer = await arquivo.arrayBuffer();
      const base64 = arrayBufferParaBase64(buffer);
      setArquivoEscolhido({ nome: arquivo.name, base64 });
      setPastaBase(pastaBaseOpcoes[0].value);
      setSubpastaDestino("");
      setSenhaPfx("");
      const extensao = arquivo.name.slice(arquivo.name.lastIndexOf(".")).toLowerCase();
      setInstalarComoCertificado(EXTENSOES_CERTIFICADO.includes(extensao) || EXTENSOES_PFX.includes(extensao));
      setSucesso(`Arquivo "${arquivo.name}" carregado. Ajuste o destino se quiser e clique em "Gerar comando".`);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao ler o arquivo");
    } finally {
      setProcessandoArquivo(false);
    }
  }

  function handleGerarComandoArquivo() {
    if (!arquivoEscolhido) return;
    setErro("");
    setSucesso("");

    if (instalarComoCertificado && arquivoEhPfx && !senhaPfx.trim()) {
      setErro("Informe a senha do certificado PFX.");
      return;
    }

    const pastaBaseExpr = pastaBaseOpcoes.find((opcao) => opcao.value === pastaBase)?.expr ?? pastaBaseOpcoes[0].expr;
    const script = gerarScriptArquivo(
      arquivoEscolhido.base64,
      arquivoEscolhido.nome,
      pastaBaseExpr,
      subpastaDestino,
      instalarComoCertificado,
      certStore,
      certEscopo,
      arquivoEhPfx,
      senhaPfx,
    );
    setComando(script);
    if (instalarComoCertificado && certEscopo === "LocalMachine") {
      setModo("admin");
    }
    setSucesso(
      `Comando gerado a partir de "${arquivoEscolhido.nome}"${
        instalarComoCertificado && certEscopo === "LocalMachine" ? " (modo Administrador)" : ""
      }. Selecione os notebooks e clique em Enviar comando.`,
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErro("");
    setSucesso("");

    const comandoTexto = comando.trim();
    if (!comandoTexto) {
      setErro("Digite um comando.");
      return;
    }
    if (selecionados.size === 0) {
      setErro("Selecione ao menos um notebook.");
      return;
    }
    if (agendar && !agendadoPara) {
      setErro("Escolha a data/hora do agendamento, ou desmarque a opção.");
      return;
    }

    const agendadoIso = agendar && agendadoPara ? new Date(agendadoPara).toISOString() : undefined;
    setConfirmacaoEnvio({ comandoTexto, agendadoIso });
  }

  async function handleConfirmarEnvio() {
    if (!confirmacaoEnvio) return;
    const { comandoTexto, agendadoIso } = confirmacaoEnvio;

    setEnviando(true);
    try {
      await createCommand(Array.from(selecionados), comandoTexto, agendadoIso, modo);
      setSucesso(
        `Comando enviado para ${selecionados.size} notebook(s)${agendadoIso ? ", agendado" : ""}${modo === "admin" ? " — modo administrador" : ""}.`,
      );
      setComando("");
      setConfirmacaoEnvio(null);
      await refreshHistorico();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao enviar comando");
      setConfirmacaoEnvio(null);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="min-w-0 rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm font-medium text-brand-600">Comandos</p>
        <h3 className="text-2xl font-semibold text-slate-900">Executar comando remoto</h3>
        <p className="text-sm text-slate-500">
          Roda via PowerShell no(s) notebook(s) selecionado(s), no próximo checkin do agente (até ~1 minuto). Use com
          cuidado — não há confirmação extra antes de executar.
        </p>

        {erro ? <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{erro}</p> : null}
        {sucesso ? <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{sucesso}</p> : null}

        <form className="mt-4 min-w-0 space-y-4" onSubmit={handleSubmit}>
          <div className="min-w-0 space-y-2 rounded-2xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={templateSelecionadoId}
                onChange={(event) => handleSelecionarTemplate(event.target.value)}
                className="h-9 min-w-0 flex-1 rounded-xl border border-slate-200 px-3 text-xs outline-none focus:border-brand-500 sm:flex-none sm:w-52"
              >
                <option value="">
                  {templatesCarregando
                    ? "Carregando biblioteca..."
                    : templates.length === 0
                      ? "Biblioteca vazia"
                      : "Carregar da biblioteca..."}
                </option>
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.nome}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void handleExcluirTemplateSelecionado()}
                disabled={!templateSelecionadoId}
                title="Excluir comando selecionado da biblioteca"
                aria-label="Excluir comando selecionado da biblioteca"
                className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>

              <input
                value={nomeTemplate}
                onChange={(event) => setNomeTemplate(event.target.value)}
                placeholder="Nome p/ salvar comando atual"
                className="h-9 min-w-0 flex-1 rounded-xl border border-slate-200 px-3 text-xs outline-none focus:border-brand-500 sm:flex-none sm:w-44"
              />
              <button
                type="button"
                onClick={() => void handleSalvarTemplate()}
                disabled={salvandoTemplate}
                title="Salvar comando atual na biblioteca"
                className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-60"
              >
                <BookmarkPlus className="h-3.5 w-3.5" />
                {salvandoTemplate ? "Salvando..." : "Salvar"}
              </button>

              <button
                type="button"
                onClick={() => void preencherScriptAtualizacao()}
                disabled={carregandoScriptAtualizacao}
                className="ml-auto inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-60"
              >
                <DownloadCloud className="h-3.5 w-3.5" />
                {carregandoScriptAtualizacao ? "Gerando..." : "Atualizar agente"}
              </button>
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <FileBadge2 className="h-4 w-4 flex-shrink-0 text-slate-500" />
              <span className="text-xs font-medium text-slate-700">Escolher um arquivo</span>
              <label className="inline-flex cursor-pointer items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                {processandoArquivo ? "Lendo arquivo..." : arquivoEscolhido ? "Trocar arquivo..." : "Escolher arquivo..."}
                <input
                  type="file"
                  className="hidden"
                  disabled={processandoArquivo}
                  onChange={(event) => void handleArquivoEscolhido(event)}
                />
              </label>
              {arquivoEscolhido ? (
                <span className="truncate text-xs text-slate-500">{arquivoEscolhido.nome}</span>
              ) : (
                <span className="text-xs text-slate-400">Gera um comando que leva o arquivo até o notebook (até ~20 KB).</span>
              )}
            </div>

            {arquivoEscolhido ? (
              <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2">
                <select
                  value={pastaBase}
                  onChange={(event) => setPastaBase(event.target.value)}
                  className="h-8 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500"
                >
                  {pastaBaseOpcoes.map((opcao) => (
                    <option key={opcao.value} value={opcao.value}>
                      {opcao.label}
                    </option>
                  ))}
                </select>
                <input
                  value={subpastaDestino}
                  onChange={(event) => setSubpastaDestino(event.target.value)}
                  placeholder="Subpasta oculta (opcional, ex: certificado)"
                  className="h-8 min-w-0 flex-1 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500 sm:flex-none sm:w-56"
                />
                <label className="flex items-center gap-1.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={instalarComoCertificado}
                    onChange={(event) => setInstalarComoCertificado(event.target.checked)}
                  />
                  {arquivoEhPfx
                    ? "Instalar certificado PFX automaticamente (Import-PfxCertificate)"
                    : "Instalar certificado público automaticamente (Import-Certificate)"}
                </label>
                {instalarComoCertificado && arquivoEhPfx ? (
                  <>
                    <select
                      value={certEscopo}
                      onChange={(event) => setCertEscopo(event.target.value as "CurrentUser" | "LocalMachine")}
                      className="h-8 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500"
                    >
                      {certEscopoOpcoes.map((opcao) => (
                        <option key={opcao.value} value={opcao.value}>
                          {opcao.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="password"
                      value={senhaPfx}
                      onChange={(event) => setSenhaPfx(event.target.value)}
                      placeholder="Senha do certificado PFX"
                      className="h-8 min-w-0 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500 sm:w-48"
                    />
                  </>
                ) : instalarComoCertificado ? (
                  <>
                    <select
                      value={certEscopo}
                      onChange={(event) => setCertEscopo(event.target.value as "CurrentUser" | "LocalMachine")}
                      className="h-8 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500"
                    >
                      {certEscopoOpcoes.map((opcao) => (
                        <option key={opcao.value} value={opcao.value}>
                          {opcao.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={certStore}
                      onChange={(event) => setCertStore(event.target.value)}
                      className="h-8 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500"
                    >
                      {certStoreOpcoes.map((opcao) => (
                        <option key={opcao.value} value={opcao.value}>
                          {opcao.label}
                        </option>
                      ))}
                    </select>
                  </>
                ) : null}
                <button
                  type="button"
                  onClick={handleGerarComandoArquivo}
                  className="ml-auto rounded-xl bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white"
                >
                  Gerar comando
                </button>
              </div>
            ) : null}
          </div>

          <label className="block min-w-0 space-y-1 text-sm text-slate-700">
            <span>Comando (PowerShell)</span>
            <textarea
              value={comando}
              onChange={(event) => setComando(event.target.value)}
              placeholder="Ex: Get-Service | Where-Object Status -eq 'Stopped'"
              className="min-h-28 w-full min-w-0 resize-y break-words rounded-2xl border border-slate-200 px-4 py-3 font-mono text-sm outline-none focus:border-brand-500"
            />
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={agendar} onChange={(event) => setAgendar(event.target.checked)} />
            <Clock className="h-4 w-4" />
            Agendar para um horário específico
          </label>

          {agendar ? (
            <input
              type="datetime-local"
              value={agendadoPara}
              min={toLocalDatetimeInputMin()}
              onChange={(event) => setAgendadoPara(event.target.value)}
              className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500 sm:w-64"
            />
          ) : null}

          <div className="space-y-1">
            <span className="text-sm text-slate-700">Executar como</span>
            <div className="flex flex-wrap gap-2">
              <label
                className={`flex flex-1 cursor-pointer items-center gap-2 rounded-2xl border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-brand-500 focus-within:ring-offset-2 ${
                  modo === "usuario" ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600"
                }`}
              >
                <input
                  type="radio"
                  name="modo-execucao"
                  className="sr-only"
                  checked={modo === "usuario"}
                  onChange={() => setModo("usuario")}
                />
                <span>
                  <span className="block font-semibold">Usuário local</span>
                  <span className="block text-xs opacity-80">Padrão — roda com o privilégio de quem está logado.</span>
                </span>
              </label>
              <label
                className={`flex flex-1 cursor-pointer items-center gap-2 rounded-2xl border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-amber-500 focus-within:ring-offset-2 ${
                  modo === "admin" ? "border-amber-500 bg-amber-50 text-amber-800" : "border-slate-200 text-slate-600"
                }`}
              >
                <input
                  type="radio"
                  name="modo-execucao"
                  className="sr-only"
                  checked={modo === "admin"}
                  onChange={() => setModo("admin")}
                />
                <ShieldAlert className="h-4 w-4 flex-shrink-0" />
                <span>
                  <span className="block font-semibold">Administrador</span>
                  <span className="block text-xs opacity-80">
                    Privilégio total (SYSTEM). Só funciona em notebooks com a tarefa elevada configurada.
                  </span>
                </span>
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-slate-700">
                Notebooks <span className="text-slate-400">({selecionados.size} selecionado(s))</span>
              </span>
              <button
                type="button"
                onClick={alternarTodos}
                className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700"
              >
                {todosFiltradosSelecionados ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
                Todos
              </button>
            </div>
            <input
              value={filtro}
              onChange={(event) => setFiltro(event.target.value)}
              placeholder="Filtrar por usuário, nº série ou modelo"
              className="mt-2 h-10 w-full rounded-2xl border border-slate-200 px-4 text-sm outline-none focus:border-brand-500"
            />
            <div className="mt-2 max-h-64 space-y-1 overflow-auto rounded-2xl border border-slate-200 p-2">
              {notebooksFiltrados.length === 0 ? (
                <p className="px-2 py-4 text-center text-sm text-slate-500">Nenhum notebook encontrado.</p>
              ) : (
                notebooksFiltrados.map((item) => (
                  <label
                    key={item.numero_serie}
                    className="flex items-center gap-2 rounded-xl px-2 py-2 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selecionados.has(item.numero_serie)}
                      onChange={() => alternarSelecao(item.numero_serie)}
                    />
                    <span className="font-medium text-slate-900">{displayNames[item.numero_serie]}</span>
                    <span className="text-xs text-slate-400">
                      {item.numero_serie} · {item.modelo || "—"}
                    </span>
                    <Badge tone={item.online_status === "online" ? "success" : "danger"} size="sm" className="ml-auto">
                      {item.online_status === "online" ? "Online" : "Offline"}
                    </Badge>
                  </label>
                ))
              )}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              disabled={enviando}
              className="rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
            >
              {enviando ? "Enviando..." : "Enviar comando"}
            </button>
          </div>
        </form>
      </section>

      <ConfirmDialog
        open={confirmacaoEnvio !== null}
        tone={modo === "admin" ? "danger" : "default"}
        title={
          modo === "admin"
            ? `Executar como Administrador em ${selecionados.size} notebook(s)?`
            : `Executar comando em ${selecionados.size} notebook(s)?`
        }
        confirmLabel={enviando ? "Enviando..." : "Sim, executar"}
        confirming={enviando}
        onCancel={() => setConfirmacaoEnvio(null)}
        onConfirm={() => void handleConfirmarEnvio()}
        description={
          confirmacaoEnvio ? (
            <div className="space-y-2">
              {modo === "admin" ? (
                <p className="font-medium text-red-700">
                  Este comando roda com privilégio total (SYSTEM) — sem sandbox, sem confirmação do usuário do
                  notebook.
                </p>
              ) : null}
              <p>
                Destino:{" "}
                {nomesSelecionadosResumo}
              </p>
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-100 px-2 py-1.5 font-mono text-xs text-slate-700">
                {confirmacaoEnvio.comandoTexto}
              </pre>
              {confirmacaoEnvio.agendadoIso ? (
                <p className="text-xs text-slate-500">
                  Agendado para {new Date(confirmacaoEnvio.agendadoIso).toLocaleString("pt-BR")}.
                </p>
              ) : (
                <p className="text-xs text-slate-500">Roda no próximo checkin do agente (até ~1 minuto).</p>
              )}
            </div>
          ) : null
        }
      />

      <section className="min-w-0 rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">Histórico</h3>
            <p className="text-xs text-slate-400">
              {abaHistorico === "recentes"
                ? "Atualiza sozinho enquanto houver comando pendente (notebook online) ou executando."
                : "Sem previsão de execução — só rodam quando o notebook voltar a ficar online."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {abaHistorico === "recentes" ? (
              <select
                value={filtroStatus}
                onChange={(event) => setFiltroStatus(event.target.value as typeof filtroStatus)}
                className="h-8 rounded-xl border border-slate-200 px-2 text-xs outline-none focus:border-brand-500"
              >
                {filtroStatusOpcoes.map((opcao) => (
                  <option key={opcao.value} value={opcao.value}>
                    {opcao.label}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              onClick={() => void refreshHistorico()}
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700"
            >
              Atualizar agora
            </button>
          </div>
        </div>

        <div className="mt-3 flex gap-1 rounded-xl bg-slate-100 p-1 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setAbaHistorico("recentes")}
            className={`flex-1 rounded-lg px-3 py-1.5 ${
              abaHistorico === "recentes" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
            }`}
          >
            Histórico ({historicoRecentes.length})
          </button>
          <button
            type="button"
            onClick={() => setAbaHistorico("pendentes_offline")}
            className={`flex-1 rounded-lg px-3 py-1.5 ${
              abaHistorico === "pendentes_offline" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
            }`}
          >
            Pendentes offline ({historicoPendentesOffline.length})
          </button>
        </div>

        {historicoCarregando ? (
          <div className="mt-3">
            <SkeletonCards count={3} />
          </div>
        ) : historicoFiltrado.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            {historico.length === 0 ? "Nenhum comando enviado ainda." : "Nenhum comando para esse filtro."}
          </p>
        ) : (
          <div className="mt-3 max-h-[70vh] space-y-3 overflow-auto">
            {historicoPaginado.map((cmd) => (
              <div key={cmd.id} className="rounded-2xl border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-sm font-medium text-slate-900">
                    {displayNames[cmd.numero_serie] || cmd.numero_serie}
                    {cmd.modo === "admin" ? (
                      <span
                        title="Executado com privilégio total (SYSTEM)"
                        className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-800"
                      >
                        <ShieldAlert className="h-3 w-3" />
                        Admin
                      </span>
                    ) : null}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Badge tone={statusTone[cmd.status]}>
                      {statusLabel[cmd.status]}
                      {cmd.status === "erro" && cmd.codigo_saida !== null ? ` (código ${cmd.codigo_saida})` : ""}
                    </Badge>
                    {cmd.status === "pendente" ? (
                      <button
                        type="button"
                        onClick={() => void handleExcluirComando(cmd)}
                        disabled={excluindoId === cmd.id}
                        title="Excluir comando pendente"
                        aria-label="Excluir comando pendente"
                        className="inline-flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                    {cmd.status === "executando" ? (
                      <button
                        type="button"
                        onClick={() => void handleCancelarComando(cmd)}
                        disabled={cancelandoId === cmd.id}
                        title="Cancelar comando preso em execução"
                        aria-label="Cancelar comando preso em execução"
                        className="inline-flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                      >
                        <Ban className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => abrirEmNovaJanela(cmd.comando)}
                  title="Clique para ver o comando completo em uma nova janela"
                  className="mt-1 block w-full truncate rounded-lg bg-slate-100 px-2 py-1 text-left font-mono text-xs text-slate-700 hover:bg-slate-200"
                >
                  {primeiraLinha(cmd.comando)}
                </button>
                <p className="mt-1 text-xs text-slate-400">
                  {new Date(cmd.criado_em).toLocaleString("pt-BR")}
                  {cmd.criado_por ? ` · ${cmd.criado_por}` : ""}
                  {cmd.agendado_para ? ` · agendado para ${new Date(cmd.agendado_para).toLocaleString("pt-BR")}` : ""}
                </p>
                {cmd.resultado ? (
                  <button
                    type="button"
                    onClick={() => abrirEmNovaJanela(cmd.resultado || "")}
                    title="Clique para ver o resultado completo em uma nova janela"
                    className="mt-2 block w-full truncate rounded-xl bg-slate-950 px-3 py-2 text-left font-mono text-xs text-slate-100 hover:bg-slate-800"
                  >
                    {primeiraLinha(cmd.resultado)}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}

        <Pagination
          page={historicoPage}
          totalItems={historicoFiltrado.length}
          pageSize={HISTORICO_PAGE_SIZE}
          onPageChange={setHistoricoPage}
          bare
        />
      </section>
    </div>
  );
}
