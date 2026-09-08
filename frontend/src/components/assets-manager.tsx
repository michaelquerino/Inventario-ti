"use client";

import { Filter, LayoutGrid, Pencil, Plus, Search, Tags, Trash2 } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  createAsset,
  deleteAsset,
  listAssets,
  updateAsset,
  type Asset,
  type AssetPayload,
} from "@/lib/assets-api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pagination } from "@/components/ui/pagination";
import { SkeletonTableRows } from "@/components/ui/skeleton";

type FormState = {
  asset_tag: string;
  screen_asset_tag: string;
  name: string;
  category: string;
  status: string;
  serial_number: string;
  brand: string;
  model: string;
  location: string;
  owner: string;
  department: string;
  notes: string;
};
type AssetsManagerProps = {
  externalQuery?: string;
};

const emptyForm: FormState = {
  asset_tag: "",
  screen_asset_tag: "",
  name: "",
  category: "",
  status: "active",
  serial_number: "",
  brand: "",
  model: "",
  location: "",
  owner: "",
  department: "",
  notes: "",
};

const statusLabel: Record<string, string> = {
  active: "Ativo",
  maintenance: "Manutenção",
  retired: "Baixado",
};

const CATEGORIAS_FIXAS = ["Notebook", "Equipamento Técnico", "Câmera", "Celular", "Impressora"];

const AUTO_REFRESH_MS = 60 * 60 * 1000;
const PAGE_SIZE = 20;

export function AssetsManager({ externalQuery = "" }: AssetsManagerProps) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [compactLayout, setCompactLayout] = useState(true);
  const [viewOnly, setViewOnly] = useState(false);
  const [ativoParaExcluir, setAtivoParaExcluir] = useState<Asset | null>(null);
  const [page, setPage] = useState(1);

  async function loadAssets() {
    setLoading(true);
    setError("");
    try {
      const data = await listAssets();
      setAssets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar ativos");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAssets();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadAssets();
    }, AUTO_REFRESH_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    function handleCreateAssetEvent() {
      openCreateModal();
    }

    window.addEventListener("assets:create-new", handleCreateAssetEvent);
    return () => {
      window.removeEventListener("assets:create-new", handleCreateAssetEvent);
    };
  }, []);

  useEffect(() => {
    setQuery(externalQuery);
  }, [externalQuery]);

  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      const matchesQuery =
        query.trim().length === 0 ||
        [asset.asset_tag, asset.name, asset.owner, asset.location, asset.brand, asset.model]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase());
      const matchesStatus = statusFilter === "all" || asset.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [assets, query, statusFilter]);

  useEffect(() => {
    setPage(1);
  }, [query, statusFilter]);

  const pagedAssets = useMemo(
    () => filteredAssets.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredAssets, page],
  );

  function openCreateModal() {
    setEditingId(null);
    setForm(emptyForm);
    setViewOnly(false);
    setIsModalOpen(true);
  }

  function openEditModal(asset: Asset, readOnly = false) {
    setEditingId(asset.id);
    setForm({
      asset_tag: asset.asset_tag,
      screen_asset_tag: asset.screen_asset_tag || "",
      name: asset.name,
      category: asset.category || "",
      status: asset.status,
      serial_number: asset.serial_number || "",
      brand: asset.brand || "",
      model: asset.model || "",
      location: asset.location || "",
      owner: asset.owner || "",
      department: asset.department || "",
      notes: asset.notes || "",
    });
    setViewOnly(readOnly);
    setIsModalOpen(true);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (viewOnly) return;
    setSaving(true);
    setError("");
    try {
      // Campos opcionais em branco viram null (em vez de serem omitidos), pra
      // realmente limpar o valor salvo — se a chave simplesmente não fosse
      // enviada, o backend interpretava como "não mexer nesse campo" e o
      // valor antigo (ex: uma observação removida) continuava lá.
      const payload = Object.fromEntries(
        Object.entries(form).map(([field, value]) => {
          const trimmed = String(value).trim();
          if (trimmed === "" && field !== "asset_tag" && field !== "name") {
            return [field, null];
          }
          return [field, trimmed];
        }),
      ) as AssetPayload;

      if (editingId === null) {
        await createAsset(payload);
      } else {
        await updateAsset(editingId, payload);
      }

      setIsModalOpen(false);
      await loadAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar ativo");
    } finally {
      setSaving(false);
    }
  }

  function handleDelete(asset: Asset) {
    setAtivoParaExcluir(asset);
  }

  async function handleConfirmarExclusao() {
    if (!ativoParaExcluir) return;
    const id = ativoParaExcluir.id;
    setDeletingId(id);
    setError("");
    try {
      await deleteAsset(id);
      setAtivoParaExcluir(null);
      await loadAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir ativo");
    } finally {
      setDeletingId(null);
    }
  }

  function clearFilters() {
    setQuery("");
    setStatusFilter("all");
  }

  return (
    <div className="rounded-[28px] border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-1 flex-col gap-3 lg:flex-row lg:items-center">
            <div className="relative w-full max-w-xl">
              <Search className="pointer-events-none absolute left-4 top-3.5 h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filtrar por tag, nome, responsável ou localização"
                className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50 pl-10 pr-4 text-sm outline-none focus:border-brand-500"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {[
                { value: "all", label: "Todos" },
                { value: "active", label: "Ativo" },
                { value: "maintenance", label: "Manutenção" },
                { value: "retired", label: "Baixado" },
              ].map((item) => (
                <button
                  key={item.value}
                  onClick={() => setStatusFilter(item.value)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    statusFilter === item.value
                      ? "bg-brand-600 text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={clearFilters}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600"
            >
              <Filter className="h-4 w-4" />
              Limpar filtros
            </button>
            <button
              onClick={() => setCompactLayout((current) => !current)}
              className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-brand-600/20"
            >
              <LayoutGrid className="h-4 w-4" />
              {compactLayout ? "Layout confortável" : "Layout compacto"}
            </button>
            <button
              onClick={openCreateModal}
              className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
            >
              <Plus className="h-4 w-4" />
              Novo ativo
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="border-b border-red-100 bg-red-50 px-5 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="min-w-full table-fixed divide-y divide-slate-200 text-left text-sm">
          <colgroup>
            <col className="w-28" />
            <col className="w-28" />
            <col className="w-44" />
            <col className="w-24" />
            <col className="w-28" />
            <col className="w-28" />
            <col className="w-64" />
            <col className="w-36" />
          </colgroup>
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-5 py-3 font-medium">Patrimônio</th>
              <th className="px-5 py-3 font-medium">Patrimônio Tela</th>
              <th className="px-5 py-3 font-medium">Nome</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Responsável</th>
              <th className="px-5 py-3 font-medium">Localização</th>
              <th className="px-5 py-3 font-medium">Observações</th>
              <th className="px-3 py-3 text-right font-medium">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <SkeletonTableRows columns={8} cellClassName="px-5 py-3" />
            ) : filteredAssets.length === 0 ? (
              <tr>
                <td className="px-5 py-7 text-slate-500" colSpan={8}>
                  Nenhum ativo encontrado.
                </td>
              </tr>
            ) : (
              pagedAssets.map((asset) => (
                <tr key={asset.id} className="hover:bg-slate-50">
                  <td className={`truncate px-5 font-semibold text-brand-700 ${compactLayout ? "py-2" : "py-4"}`}>
                    {asset.asset_tag}
                  </td>
                  <td className={`truncate px-5 ${compactLayout ? "py-2" : "py-4"}`}>
                    {asset.screen_asset_tag || "—"}
                  </td>
                  <td className={`px-5 ${compactLayout ? "py-2" : "py-4"}`}>
                    <div className="truncate font-medium text-slate-900">{asset.name}</div>
                    <div className="truncate text-xs text-slate-400">{asset.model || asset.category || "—"}</div>
                  </td>
                  <td className={`px-5 ${compactLayout ? "py-2" : "py-4"}`}>
                    <span className="inline-block truncate rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
                      {statusLabel[asset.status] || asset.status}
                    </span>
                  </td>
                  <td className={`truncate px-5 ${compactLayout ? "py-2" : "py-4"}`}>{asset.owner || "—"}</td>
                  <td className={`truncate px-5 ${compactLayout ? "py-2" : "py-4"}`}>{asset.location || "—"}</td>
                  <td className={`px-5 ${compactLayout ? "py-2" : "py-4"}`}>
                    {asset.notes ? (
                      <button
                        type="button"
                        onClick={() => openEditModal(asset, true)}
                        className="block w-full truncate text-left text-slate-600 underline decoration-dotted decoration-slate-300 underline-offset-2 hover:text-brand-700 hover:decoration-brand-400"
                        title={asset.notes}
                      >
                        {asset.notes}
                      </button>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className={`px-3 ${compactLayout ? "py-2" : "py-4"}`}>
                    <div className="flex justify-end gap-1.5">
                      <button
                        onClick={() => openEditModal(asset, true)}
                        title="Visualizar sem editar"
                        aria-label={`Visualizar ${asset.name}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
                      >
                        <Search className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => openEditModal(asset)}
                        title="Editar"
                        aria-label={`Editar ${asset.name}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(asset)}
                        disabled={deletingId === asset.id}
                        title={deletingId === asset.id ? "Excluindo..." : "Excluir"}
                        aria-label={deletingId === asset.id ? `Excluindo ${asset.name}` : `Excluir ${asset.name}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalItems={filteredAssets.length} pageSize={PAGE_SIZE} onPageChange={setPage} />

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4">
          <div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-[28px] bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-brand-600">Cadastro</p>
                <h3 className="text-2xl font-semibold text-slate-900">
                  {viewOnly ? "Visualizar ativo" : editingId === null ? "Novo ativo" : "Editar ativo"}
                </h3>
                <p className="text-sm text-slate-500">
                  {viewOnly ? "Somente leitura." : "Tela corporativa de cadastro e edição."}
                </p>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
              >
                Fechar
              </button>
            </div>

            <form className="mt-6 grid gap-4 md:grid-cols-2" onSubmit={handleSave}>
              {[
                ["asset_tag", "Patrimônio"],
                ...(form.category === "Notebook"
                  ? [["screen_asset_tag", "Patrimônio da Tela"]]
                  : []),
                ["name", "Nome"],
                ["category", "Categoria"],
                ["status", "Status"],
                ["serial_number", "Número de série"],
                ["brand", "Fabricante"],
                ["model", "Modelo"],
                ["location", "Localização"],
                ["owner", "Responsável"],
                ["department", "Departamento"],
              ].map(([field, label]) => (
                <label key={field} className="space-y-1 text-sm text-slate-700">
                  <span>{label}</span>
                  {field === "status" ? (
                    <select
                      value={form.status}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, status: event.target.value }))
                      }
                      disabled={viewOnly}
                      className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500"
                    >
                      <option value="active">Ativo</option>
                      <option value="maintenance">Manutenção</option>
                      <option value="retired">Baixado</option>
                    </select>
                  ) : field === "category" ? (
                    <select
                      value={form.category || ""}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          category: event.target.value,
                          screen_asset_tag:
                            event.target.value === "Notebook" ? current.screen_asset_tag : "",
                        }))
                      }
                      disabled={viewOnly}
                      className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500"
                    >
                      <option value="">Selecione...</option>
                      {CATEGORIAS_FIXAS.map((categoria) => (
                        <option key={categoria} value={categoria}>
                          {categoria}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={form[field as keyof FormState] as string}
                      onChange={(event) =>
                        setForm((current) => ({ ...current, [field]: event.target.value }))
                      }
                      readOnly={viewOnly}
                      className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500 disabled:bg-slate-50 read-only:bg-slate-50 read-only:text-slate-500"
                      required={field === "asset_tag" || field === "name"}
                    />
                  )}
                </label>
              ))}

              <label className="space-y-1 text-sm text-slate-700 md:col-span-2">
                <span>Observações</span>
                <textarea
                  value={form.notes}
                  onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                  readOnly={viewOnly}
                  className="min-h-28 w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none focus:border-brand-500 read-only:bg-slate-50 read-only:text-slate-500"
                />
              </label>

              <div className="md:col-span-2 flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
                >
                  {viewOnly ? "Fechar" : "Cancelar"}
                </button>
                {viewOnly ? null : (
                  <button
                    disabled={saving}
                    className="rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {saving ? "Salvando..." : "Salvar"}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={ativoParaExcluir !== null}
        tone="danger"
        title="Excluir ativo?"
        confirmLabel={deletingId !== null ? "Excluindo..." : "Sim, excluir"}
        confirming={deletingId !== null}
        onCancel={() => setAtivoParaExcluir(null)}
        onConfirm={() => void handleConfirmarExclusao()}
        description={
          ativoParaExcluir ? (
            <p>
              O ativo <strong>{ativoParaExcluir.name}</strong> ({ativoParaExcluir.asset_tag}) será excluído
              permanentemente. Essa ação não pode ser desfeita.
            </p>
          ) : null
        }
      />
    </div>
  );
}
