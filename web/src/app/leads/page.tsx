
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

const STAGES = ["new", "contacted", "replied", "meeting", "won", "lost"] as const;
type Stage = (typeof STAGES)[number];

type Lead = {
  id: number;
  name: string;
  company: string | null;
  industry: string | null;
  city: string | null;
  email: string | null;
  phone: string | null;
  source: string | null;
  stage: Stage;
  notes: string | null;
};

const emptyForm = {
  name: "",
  company: "",
  industry: "",
  city: "",
  email: "",
  phone: "",
  source: "Manual",
  stage: "new" as Stage,
  notes: "",
};

const stageStyle: Record<Stage, string> = {
  new: "bg-blue-50 text-blue-700",
  contacted: "bg-violet-50 text-violet-700",
  replied: "bg-amber-50 text-amber-700",
  meeting: "bg-cyan-50 text-cyan-700",
  won: "bg-emerald-50 text-emerald-700",
  lost: "bg-rose-50 text-rose-700",
};

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [userId, setUserId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const headers = useMemo(
    () => ({
      "Content-Type": "application/json",
      "X-User-ID": userId,
    }),
    [userId]
  );

  const loadLeads = useCallback(async () => {
    if (!userId) return;

    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_URL}/leads`, { headers });
      if (!response.ok) throw new Error("Could not load leads.");

      const data = await response.json();
      setLeads(data.leads ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, [headers, userId]);

  useEffect(() => {
    const storedId = localStorage.getItem("outrivo_user_id");

    if (!storedId) {
      setError("User ID not found. Please open the Assistant first.");
      setLoading(false);
      return;
    }

    setUserId(storedId);
  }, []);

  useEffect(() => {
    if (userId) loadLeads();
  }, [userId, loadLeads]);

  const filteredLeads = useMemo(() => {
    return leads.filter((lead) => {
      const matchesStage = filter === "all" || lead.stage === filter;
      const query = search.toLowerCase();

      const matchesSearch = [
        lead.name,
        lead.company,
        lead.email,
        lead.industry,
        lead.city,
      ]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(query));

      return matchesStage && matchesSearch;
    });
  }, [leads, filter, search]);

  function openAddForm() {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
  }

  function openEditForm(lead: Lead) {
    setEditingId(lead.id);
    setForm({
      name: lead.name ?? "",
      company: lead.company ?? "",
      industry: lead.industry ?? "",
      city: lead.city ?? "",
      email: lead.email ?? "",
      phone: lead.phone ?? "",
      source: lead.source ?? "",
      stage: lead.stage,
      notes: lead.notes ?? "",
    });
    setShowForm(true);
  }

  async function saveLead(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      const isEditing = editingId !== null;
      const response = await fetch(
        isEditing ? `${API_URL}/leads/${editingId}` : `${API_URL}/leads`,
        {
          method: isEditing ? "PATCH" : "POST",
          headers,
          body: JSON.stringify(form),
        }
      );

      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Could not save lead.");
      }

      setShowForm(false);
      setForm(emptyForm);
      setEditingId(null);
      await loadLeads();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save lead.");
    } finally {
      setSaving(false);
    }
  }

  async function changeStage(id: number, stage: Stage) {
    setError("");

    try {
      const response = await fetch(`${API_URL}/leads/${id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ stage }),
      });

      if (!response.ok) throw new Error("Could not update lead status.");
      await loadLeads();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  }

  async function deleteLead(id: number) {
    if (!window.confirm("Are you sure you want to delete this lead?")) return;

    setError("");

    try {
      const response = await fetch(`${API_URL}/leads/${id}`, {
        method: "DELETE",
        headers,
      });

      if (!response.ok) throw new Error("Could not delete lead.");
      await loadLeads();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  }

  const counts = {
    total: leads.length,
    new: leads.filter((lead) => lead.stage === "new").length,
    contacted: leads.filter((lead) => lead.stage === "contacted").length,
    won: leads.filter((lead) => lead.stage === "won").length,
  };

  return (
    <div className="min-h-screen bg-[#f8f8fc] text-slate-800">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white px-6 py-7 md:block">
        <a href="/" className="text-2xl font-bold tracking-tight text-[#6756c9]">
          outrivo<span className="text-slate-400">.</span>
        </a>

        <p className="mb-5 mt-12 text-xs font-semibold uppercase tracking-widest text-slate-400">
          Workspace
        </p>

        <nav className="space-y-2 text-sm">
          {[
            ["Overview", "/dashboard"],
            ["AI Assistant", "/assistant"],
            ["Leads", "/leads"],
            ["Outreach", "/outreach"],
            ["History", "/history"],
          ].map(([label, href]) => (
            <a
              key={href}
              href={href}
              className={`block rounded-xl px-4 py-3 ${
                href === "/leads"
                  ? "bg-[#f0edff] font-semibold text-[#6756c9]"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {label}
            </a>
          ))}
        </nav>

        <div className="absolute bottom-7 left-6 right-6">
          <a
            href="/settings"
            className="block rounded-xl px-4 py-3 text-sm text-slate-600 hover:bg-slate-50"
          >
            Settings
          </a>
        </div>
      </aside>

      <main className="px-5 py-8 md:ml-64 md:px-10">
        <div className="mx-auto max-w-7xl">
          <header className="mb-9 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm text-slate-400">Workspace / Leads</p>
              <h1 className="mt-2 text-3xl font-bold tracking-tight">
                Lead Management
              </h1>
              <p className="mt-2 text-sm text-slate-500">
                Organize prospects and track your sales pipeline.
              </p>
            </div>

            <button
              onClick={openAddForm}
              className="rounded-xl bg-[#6756c9] px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#5745b7]"
            >
              + Add Lead
            </button>
          </header>

          {error && (
            <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              {error}
            </div>
          )}

          <section className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Total Leads", value: counts.total },
              { label: "New Leads", value: counts.new },
              { label: "Contacted", value: counts.contacted },
              { label: "Won", value: counts.won },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
              >
                <p className="text-sm text-slate-500">{item.label}</p>
                <p className="mt-3 text-3xl font-bold">{item.value}</p>
              </div>
            ))}
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-col gap-4 border-b border-slate-100 p-5 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="font-semibold">Your Leads</h2>
                <p className="mt-1 text-xs text-slate-400">
                  {filteredLeads.length} leads displayed
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search leads..."
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-[#8878df]"
                />

                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm outline-none"
                >
                  <option value="all">All statuses</option>
                  {STAGES.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage.charAt(0).toUpperCase() + stage.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {loading ? (
              <div className="p-16 text-center text-sm text-slate-400">
                Loading your leads...
              </div>
            ) : filteredLeads.length === 0 ? (
              <div className="px-6 py-20 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#f0edff] text-2xl text-[#6756c9]">
                  +
                </div>
                <h3 className="font-semibold">No leads found</h3>
                <p className="mt-2 text-sm text-slate-400">
                  Add your first lead to start managing your pipeline.
                </p>
                <button
                  onClick={openAddForm}
                  className="mt-5 rounded-xl bg-[#6756c9] px-5 py-2.5 text-sm font-semibold text-white"
                >
                  Add your first lead
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="px-5 py-4">Lead</th>
                      <th className="px-5 py-4">Company</th>
                      <th className="px-5 py-4">Industry</th>
                      <th className="px-5 py-4">Status</th>
                      <th className="px-5 py-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredLeads.map((lead) => (
                      <tr key={lead.id} className="hover:bg-slate-50/70">
                        <td className="px-5 py-4">
                          <p className="font-semibold">{lead.name}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            {lead.email || lead.phone || "No contact details"}
                          </p>
                        </td>
                        <td className="px-5 py-4">{lead.company || "—"}</td>
                        <td className="px-5 py-4">{lead.industry || "—"}</td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded-full px-3 py-1.5 text-xs font-semibold ${stageStyle[lead.stage]}`}
                          >
                            {lead.stage}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="flex justify-end gap-2">
                            <select
                              value={lead.stage}
                              onChange={(e) =>
                                changeStage(lead.id, e.target.value as Stage)
                              }
                              aria-label={`Change status for ${lead.name}`}
                              className="max-w-28 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
                            >
                              {STAGES.map((stage) => (
                                <option key={stage} value={stage}>
                                  {stage}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={() => openEditForm(lead)}
                              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs hover:bg-slate-50"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => deleteLead(lead.id)}
                              className="rounded-lg border border-rose-100 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </main>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/40 p-4">
          <form
            onSubmit={saveLead}
            className="my-8 w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl"
          >
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">
                  {editingId ? "Edit Lead" : "Add New Lead"}
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  Enter the prospect's details below.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-lg px-3 py-2 text-slate-400 hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {(
                [
                  ["name", "Full name", true],
                  ["company", "Company", false],
                  ["email", "Email address", false],
                  ["phone", "Phone", false],
                  ["industry", "Industry", false],
                  ["city", "City", false],
                  ["source", "Lead source", false],
                ] as const
              ).map(([key, label, required]) => (
                <label key={key} className="text-sm font-medium text-slate-600">
                  {label}
                  <input
                    required={required}
                    type={key === "email" ? "email" : "text"}
                    value={form[key]}
                    onChange={(e) =>
                      setForm({ ...form, [key]: e.target.value })
                    }
                    className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-[#8878df]"
                  />
                </label>
              ))}

              <label className="text-sm font-medium text-slate-600">
                Pipeline status
                <select
                  value={form.stage}
                  onChange={(e) =>
                    setForm({ ...form, stage: e.target.value as Stage })
                  }
                  className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-normal"
                >
                  {STAGES.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage}
                    </option>
                  ))}
                </select>
              </label>

              <label className="text-sm font-medium text-slate-600 sm:col-span-2">
                Notes
                <textarea
                  rows={3}
                  value={form.notes}
                  onChange={(e) =>
                    setForm({ ...form, notes: e.target.value })
                  }
                  className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-[#8878df]"
                />
              </label>
            </div>

            <div className="mt-7 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-xl bg-[#6756c9] px-6 py-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                {saving ? "Saving..." : editingId ? "Save Changes" : "Add Lead"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
