"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardHeader, Button, Input, EmptyState } from "@/components/ui/primitives";
import { DataQualityBadge } from "@/components/ui/DataQualityBadge";
import { useApiData } from "@/lib/useApiData";
import { apiFetch, ApiError } from "@/lib/api";
import { DatasetOut, DataQuality, ValidationReportOut } from "@/lib/types";

export default function BacktestDatasetsPage() {
  const { data: datasets, loading, error: datasetsError, reload } = useApiData<DatasetOut[]>("/admin/backtesting/datasets");

  const [name, setName] = useState("");
  const [fileFormat, setFileFormat] = useState<"csv" | "json">("json");
  const [dataQuality, setDataQuality] = useState<DataQuality>("DEMO");
  const [content, setContent] = useState("");
  const [report, setReport] = useState<ValidationReportOut | null>(null);
  const [busy, setBusy] = useState<"validating" | "importing" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setContent(text);
    setFileFormat(file.name.endsWith(".csv") ? "csv" : "json");
    if (!name) setName(file.name);
    setReport(null);
  }

  async function handleValidate() {
    setBusy("validating");
    setError(null);
    try {
      const result = await apiFetch<ValidationReportOut>("/admin/backtesting/validate", {
        method: "POST",
        body: { file_format: fileFormat, content, data_quality: dataQuality },
      });
      setReport(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Validation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function handleImport() {
    setBusy("importing");
    setError(null);
    try {
      await apiFetch("/admin/backtesting/import", {
        method: "POST",
        body: { file_format: fileFormat, content, data_quality: dataQuality, name, source_filename: name },
      });
      setContent("");
      setReport(null);
      setName("");
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Backtest datasets</h1>
        <p className="text-sm text-ink-muted">
          Upload, validate, and import historical snapshot data. VERIFIED datasets require a source on
          every row and are the only data ever used for a &quot;real&quot; backtest result.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Upload a dataset" />
          <div className="space-y-3">
            <Input placeholder="Dataset name" value={name} onChange={(e) => setName(e.target.value)} />
            <input
              type="file"
              accept=".csv,.json"
              onChange={handleFileChange}
              className="w-full text-sm text-ink-muted file:mr-3 file:rounded file:border-0 file:bg-base-panel2 file:px-3 file:py-1.5 file:text-sm file:text-ink"
            />
            <div className="flex items-center gap-2 text-sm">
              <span className="text-ink-muted">Data quality:</span>
              {(["DEMO", "VERIFIED", "ESTIMATED"] as DataQuality[]).map((q) => (
                <button
                  key={q}
                  onClick={() => setDataQuality(q)}
                  className={`rounded border px-2 py-1 text-xs ${
                    dataQuality === q ? "border-signal-early text-signal-early" : "border-base-border text-ink-muted"
                  }`}
                >
                  {q}
                </button>
              ))}
            </div>
            {dataQuality === "DEMO" && (
              <p className="text-xs text-ink-faint">
                Every row will be force-tagged DEMO regardless of what the file says — demo data can never
                accidentally count as verified.
              </p>
            )}

            <div className="flex gap-2">
              <Button variant="secondary" onClick={handleValidate} disabled={!content || busy !== null}>
                {busy === "validating" ? "Validating…" : "Validate"}
              </Button>
              <Button onClick={handleImport} disabled={!report || report.error_rows > 0 || busy !== null}>
                {busy === "importing" ? "Importing…" : "Import"}
              </Button>
            </div>
            {error && <p className="text-sm text-signal-danger">{error}</p>}

            {report && (
              <div className="rounded border border-base-border p-3 text-sm">
                <div className="mb-2 flex gap-4 font-mono text-xs">
                  <span className="text-ink">total {report.total_rows}</span>
                  <span className="text-signal-conviction">valid {report.valid_rows}</span>
                  <span className="text-signal-danger">errors {report.error_rows}</span>
                  <span className="text-signal-watch">dupes {report.duplicate_rows}</span>
                </div>
                {report.errors.length > 0 && (
                  <div className="max-h-40 space-y-1 overflow-y-auto">
                    {report.errors.slice(0, 20).map((e, i) => (
                      <div key={i} className="text-xs text-signal-danger">
                        row {e.row} · {e.field}: {e.message}
                      </div>
                    ))}
                  </div>
                )}
                {report.warnings.length > 0 && (
                  <div className="mt-2 max-h-32 space-y-1 overflow-y-auto border-t border-base-border pt-2">
                    {report.warnings.slice(0, 10).map((w, i) => (
                      <div key={i} className="text-xs text-signal-watch">
                        row {w.row} · {w.field}: {w.message}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Import history" />
          {loading && <p className="text-sm text-ink-muted">Loading…</p>}
          {!loading && datasetsError && (
            <div className="rounded border border-signal-danger/30 bg-signal-danger/10 p-3 text-sm text-signal-danger">
              Couldn&apos;t load datasets: {datasetsError}
            </div>
          )}
          {!loading && datasets && datasets.length === 0 && (
            <EmptyState title="No datasets imported yet" body="Upload a CSV or JSON file to get started." />
          )}
          {!loading && datasets && datasets.length > 0 && (
            <div className="space-y-2">
              {datasets.map((d) => (
                <Link
                  key={d.id}
                  href={`/admin/backtesting/datasets/${d.id}`}
                  className="block rounded border border-base-border p-3 hover:border-ink-faint"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium text-ink">{d.name}</span>
                    <DataQualityBadge quality={d.data_quality} />
                  </div>
                  <div className="text-xs text-ink-faint">
                    {d.valid_row_count}/{d.row_count} rows valid · {d.status} ·{" "}
                    {new Date(d.created_at).toLocaleDateString()}
                  </div>
                </Link>
              ))}
            </div>
          )}
          <div className="mt-4">
            <Link href="/admin/backtesting/run" className="text-sm text-signal-early hover:underline">
              Run a backtest against imported datasets →
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
