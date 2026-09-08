"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { assets } from "@/lib/inventory-data";

const filters = ["All", "Assigned", "New", "Maintenance"] as const;

export function InventoryTable() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<(typeof filters)[number]>("All");

  const rows = useMemo(() => {
    return assets.filter((asset) => {
      const matchesQuery =
        query.trim().length === 0 ||
        [asset.tag, asset.name, asset.owner, asset.location, asset.manufacturer, asset.model]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase());
      const matchesStatus = status === "All" || asset.status === status;
      return matchesQuery && matchesStatus;
    });
  }, [query, status]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-4 border-b border-slate-200 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar ativos, responsáveis ou localização"
            className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none transition focus:border-brand-500"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {filters.map((item) => (
            <button
              key={item}
              onClick={() => setStatus(item)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                status === item
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Tag</th>
              <th className="px-4 py-3 font-medium">Nome</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Responsável</th>
              <th className="px-4 py-3 font-medium">Localização</th>
              <th className="px-4 py-3 font-medium">Fabricante</th>
              <th className="px-4 py-3 font-medium">Origem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((asset) => (
              <tr key={asset.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-semibold text-brand-700">{asset.tag}</td>
                <td className="px-4 py-3">{asset.name}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                    {asset.status}
                  </span>
                </td>
                <td className="px-4 py-3">{asset.owner || "—"}</td>
                <td className="px-4 py-3">{asset.location}</td>
                <td className="px-4 py-3">{asset.manufacturer}</td>
                <td className="px-4 py-3">{asset.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

