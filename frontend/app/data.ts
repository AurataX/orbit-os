"use client";

import { useSyncExternalStore } from "react";

export const base = process.env.NEXT_PUBLIC_API ?? "";
export const dimensions = ["cpu", "page", "disk", "place"] as const;
export type Dimension = typeof dimensions[number];
export type Policies = Record<Dimension, string>;
export type Config = Policies & { seed: number; n_tasks: number; ram: number; vram: number };
export const baseline: Config = {
  seed: 42, n_tasks: 40, ram: 60, vram: 16, cpu: "FCFS", page: "FIFO", disk: "FCFS", place: "ADAPTIVE",
};
export const labels: Record<Dimension, string> = { cpu: "CPU scheduler", page: "Paging", disk: "Disk I/O", place: "Placement" };
export const workload = { interactive: "Interactive", ai: "AI / LLM", dev: "Compile", background: "Background" };
export type Kind = keyof typeof workload;
export type Options = Record<Dimension, string[]> & {
  defaults: Policies; ram: number; vram: number; crisis_queue: number; max_ticks: number; token_required: boolean;
};
export type Task = { id: number; kind: Kind; state: string; placement: string; priority: number; burst: number; left: number };
export type Event = {
  index: number; tick: number; kind: string; subsystem: string; level: string;
  pid: number | null; task_kind: Kind | null; info: string; text: string;
};
export type Summary = {
  avg_wait: number; inter_p95_resp: number; inter_p95_turn: number; makespan: number; unfinished: number;
  killed: number; "cpu_util_%": number; page_faults: number; disk_busy: number; head_moved: number;
  gpu_stall: number; gpu_busy: number; bus_busy: number; crisis_at: number | string;
};
export type RequestIO = { task: number; track: number };
export type Snapshot = {
  tick: number; running: number | null; ready: number; blocked: number; vram_wait: number;
  ram_used: number; ram_total: number; vram_used: number; vram_total: number; disk_queue: number;
  gpu_queue: number; gpu_running: number | null; bus_busy: boolean;
  ram_frames?: [number, number][]; vram_held?: Record<string, number>; bus_task?: number | null;
  disk?: { head: number; current: RequestIO | null; queue: RequestIO[] };
};
export type Frame = {
  snapshot: Snapshot; status: {
    done: boolean; timed_out: boolean; crisis_at: number | null; policies: Policies; branch: string;
    playing: boolean; checkpoints: number[]; manual: number[];
  };
  metrics: { cpu_util: number; busy_ticks: number; page_faults: number; inter_p95_resp: number | null };
  tasks: Task[]; events: Event[]; summary: Summary | null; cursor: number; log_base: number;
  revision: number; generation: number; action_count: number; action_version: number; config?: Config; request?: number;
};
export type Action = { tick: number; action: string; params: Record<string, unknown>; effect: string | null; branch: string };
export type Branch = {
  id: string; label: string; parent: string | null; rewound_to: number | null;
  tick: number; policies: Policies; summary: Summary | null;
};
export type Tables = Record<Dimension, (Summary & { policy: string })[]>;
export const lanes = ["CPU", "GPU", "Bus", "Disk"] as const;
export type Lane = typeof lanes[number];
type Occupant = { pid: number; kind: Kind } | null;
type Sample = { tick: number; response: number | null; occupancy: Partial<Record<Lane, Occupant>> };
type State = { frame: Frame | null; samples: Sample[]; events: Event[] };
const empty: State = { frame: null, samples: [], events: [] };

export async function api<T>(path: string, body?: unknown, token = "", signal?: AbortSignal): Promise<T> {
  const res = await fetch(base + path, {
    method: body === undefined ? "GET" : "POST", cache: "no-store", signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json", "X-Orbit-Token": token },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(error => {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Can't reach the simulation server. Check the connection and retry.");
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map(entry => `${entry.loc.at(-1)}: ${entry.msg}`).join(" · ")
      : `Request failed (${res.status}).`);
  }
  return res.json();
}

export function createStore() {
  let state = empty;
  let scheduled = 0;
  const listeners = new Set<() => void>();
  function notify() {
    if (!scheduled) scheduled = requestAnimationFrame(() => {
      scheduled = 0;
      listeners.forEach(listener => listener());
    });
  }
  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    get: () => state,
    reset() { state = empty; notify(); },
    ingest(frame: Frame) {
      const prior = state.frame;
      const sameRun = prior?.generation === frame.generation;
      const sameBranch = sameRun && prior.status.branch === frame.status.branch;
      // HTTP and WS may deliver the same revision in either order. Merge events by absolute index.
      if (!sameBranch && prior && frame.revision < prior.revision) return;
      const oldEvents = sameBranch ? state.events : [];
      let events = oldEvents;
      const base = Math.max(frame.log_base, sameBranch ? prior.log_base : 0);
      if (frame.events.length || (oldEvents[0] && oldEvents[0].index < base)) {
        const incoming = frame.events.filter(event => event.index >= base);
        const kept = oldEvents.filter(event => event.index >= base);
        if (incoming.length && kept.at(-1) && incoming[0].index <= kept.at(-1)!.index) {
          const merged = new Map(kept.map(event => [event.index, event]));
          incoming.forEach(event => merged.set(event.index, event));
          events = merged.size === oldEvents.length && kept.length === oldEvents.length
            ? oldEvents : [...merged.values()].sort((a, b) => a.index - b.index);
        } else {
          events = [...kept, ...incoming];
        }
      }
      if (prior && frame.revision < prior.revision) {
        if (events !== oldEvents) { state = { ...state, events }; notify(); }
        return;
      }

      if (sameRun && prior.config) frame = { ...frame, config: prior.config };
      const s = frame.snapshot;
      if (prior?.revision === frame.revision && prior.snapshot.ram_frames && !s.ram_frames) {
        frame = { ...frame, snapshot: prior.snapshot };
      }
      let samples = sameBranch ? state.samples : sameRun ? state.samples.filter(sample => sample.tick <= s.tick) : [];
      if (s.tick !== samples.at(-1)?.tick || !sameBranch ||
          (frame.snapshot.ram_frames && frame.snapshot !== prior?.snapshot)) {
        samples = [...samples];
        const occupancy: Sample["occupancy"] = {};
        const kinds = new Map(frame.tasks.map(task => [task.id, task.kind]));
        const devices = { CPU: s.running, GPU: s.gpu_running, Bus: s.bus_task, Disk: s.disk ? s.disk.current?.task ?? null : undefined };
        for (const lane of lanes) {
          const pid = devices[lane];
          if (pid !== undefined) {
            const kind = pid === null ? undefined : kinds.get(pid);
            occupancy[lane] = kind && pid !== null ? { pid, kind } : null;
          }
        }
        const previous = samples.at(-1);
        const sample = { tick: s.tick, response: frame.metrics.inter_p95_resp, occupancy };
        if (previous?.tick === s.tick) samples[samples.length - 1] = { ...sample, occupancy: { ...previous.occupancy, ...occupancy } };
        else samples.push(sample);
      }
      state = { frame, events, samples };
      notify();
    },
  };
}

export type Store = ReturnType<typeof createStore>;
export function useData<T>(store: Store, select: (state: State) => T): T {
  return useSyncExternalStore(store.subscribe, () => select(store.get()), () => select(empty));
}

export function saveFile(name: string, data: string, type: string) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const errorText = (error: unknown) => error instanceof Error ? error.message : "Something went wrong.";
