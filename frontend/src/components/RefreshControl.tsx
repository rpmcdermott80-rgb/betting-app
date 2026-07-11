import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { RefreshRun, RefreshTrigger } from "../lib/types";

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function RefreshControl() {
  const [run, setRun] = useState<RefreshRun | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchLatest() {
    try {
      const data = await apiGet<RefreshRun | null>("/refresh/latest");
      setRun(data);
      return data;
    } catch {
      return null;
    }
  }

  useEffect(() => {
    fetchLatest();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (run?.status === "running" && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        const latest = await fetchLatest();
        if (latest && latest.status !== "running" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 5000);
    }
  }, [run?.status]);

  async function trigger() {
    setTriggering(true);
    try {
      await apiPost<RefreshTrigger>("/refresh/trigger", {});
      await fetchLatest();
    } finally {
      setTriggering(false);
    }
  }

  const isRunning = run?.status === "running";

  return (
    <div className="mb-4 flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm">
      <span className="text-slate-400">
        {run == null && "No refresh has run yet"}
        {run != null && isRunning && `Refreshing… started ${timeAgo(run.started_at)}`}
        {run != null && !isRunning && (
          <>
            Last refresh: {run.finished_at ? timeAgo(run.finished_at) : "—"}{" "}
            <span className={run.status === "failed" ? "text-red-400" : "text-emerald-400"}>({run.status})</span>
          </>
        )}
      </span>
      <button
        onClick={trigger}
        disabled={isRunning || triggering}
        className="rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isRunning ? "Running…" : "Refresh now"}
      </button>
    </div>
  );
}
