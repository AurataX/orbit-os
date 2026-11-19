"use client";

import { useState } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, Bookmark, Boxes, CheckCircle2, CircleAlert, Clock3,
  Cpu, Gauge, HardDrive, Layers3, ListChecks, MemoryStick, Radio, RotateCcw, TerminalSquare, Waypoints, Zap,
} from "lucide-react";
import { useData, type Store, type Options, type Action, type Task, type Snapshot } from "./data";
import { KindDot } from "./ui";

const fmt = (value: number) => value.toLocaleString("en-US");

function TickStat({ store }: { store: Store }) {
  const tick = useData(store, s => s.frame?.snapshot.tick);
  return <Stat name="Simulation tick" value={tick === undefined ? "—" : fmt(tick)} meta="Elapsed simulated time" icon={Clock3} tone="violet" />;
}

function FinishedStat({ store }: { store: Store }) {
  const done = useData(store, s => s.frame?.tasks.filter(task => task.state === "done").length);
  const count = useData(store, s => s.frame?.tasks.length);
  const killed = useData(store, s => s.frame?.tasks.filter(task => task.state === "killed").length);
  return <Stat name="Tasks completed" value={done === undefined ? "—" : done} suffix={count ? `/ ${count}` : undefined}
    meta={killed ? `${killed} terminated` : "Across four workload classes"} icon={Layers3} tone="blue" />;
}

function CpuStat({ store }: { store: Store }) {
  const cpu = useData(store, s => s.frame?.metrics.cpu_util);
  const busy = useData(store, s => s.frame?.metrics.busy_ticks);
  return <Stat name="CPU utilization" value={cpu === undefined ? "—" : `${cpu}%`}
    meta={busy === undefined ? "Share of ticks spent busy" : `${fmt(busy)} busy CPU ticks`} icon={Activity} tone="mint" />;
}

function CrisisStat({ store }: { store: Store }) {
  const crisis = useData(store, s => s.frame?.status.crisis_at ?? null);
  const ready = useData(store, s => !!s.frame);
  return <Stat name="Crisis status" value={crisis !== null ? "Detected" : ready ? "Stable" : "—"}
    meta={crisis === null ? "Disk queue monitored" : `Marked at tick ${fmt(crisis)}`}
    icon={crisis === null ? CheckCircle2 : CircleAlert} tone={crisis === null ? "peach" : "coral"} />;
}

function Stat({ name, value, suffix, meta, icon: Icon, tone }: {
  name: string; value: string | number; suffix?: string; meta: string; icon: typeof Clock3; tone: string;
}) {
  return <section className={`stat ${tone}`} aria-label={name}>
    <div className="stat-title"><span className="stat-icon"><Icon size={16} /></span><span>{name}</span></div>
    <div className="stat-number">{value} {suffix && <small>{suffix}</small>}</div>
    <div className="stat-meta">{meta}</div>
  </section>;
}

const noSnapshot: Pick<Snapshot, "running" | "ready" | "blocked" | "vram_wait" | "ram_used" | "ram_total" |
  "vram_used" | "vram_total" | "disk_queue" | "gpu_queue" | "gpu_running" | "bus_busy"> = {
  running: null, ready: 0, blocked: 0, vram_wait: 0, ram_used: 0, ram_total: 0,
  vram_used: 0, vram_total: 0, disk_queue: 0, gpu_queue: 0, gpu_running: null, bus_busy: false,
};

function Machine({ store, options, openResources, inspect }: {
  store: Store; options: Options | null; openResources: () => void; inspect: (pid: number) => void;
}) {
  const s = useData(store, data => data.frame?.snapshot);
  const playing = useData(store, data => data.frame?.status.playing ?? false);
  const faults = useData(store, data => data.frame?.metrics.page_faults);
  const v = s ?? noSnapshot;
  const ram = !!s && v.ram_used >= v.ram_total && v.blocked > 0;
  const disk = !!options && v.disk_queue >= options.crisis_queue;
  const vram = v.vram_wait > 0;
  const cpuIdle = v.running === null && v.blocked > 0;
  const route = disk ? "Disk queue at crisis threshold" : ram && cpuIdle ? "Disk waits coincide with an idle CPU"
    : ram ? "RAM full · tasks waiting on disk" : vram ? "VRAM pressure · GPU work waiting"
    : v.blocked ? "Page faults are sending work to disk" : "No resource bottleneck at this tick";
  const nodes = [
    { name: "CPU", icon: Cpu, value: v.running === null ? "Idle" : `PID ${v.running}`, note: `${v.ready} ready`, pid: v.running, active: cpuIdle },
    { name: "Transfer bus", icon: Waypoints, value: v.bus_busy ? "Copying" : "Idle", note: "CPU ↔ GPU" },
    { name: "GPU", icon: Boxes, value: v.gpu_running === null ? "Idle" : `PID ${v.gpu_running}`, note: `${v.gpu_queue} queued`, pid: v.gpu_running, active: vram },
    { name: "RAM", icon: MemoryStick, value: `${v.ram_used} / ${v.ram_total}`, note: `${faults ?? 0} page faults`, active: ram, open: true },
    { name: "Disk I/O", icon: HardDrive, value: `${v.disk_queue} pending`, note: `${v.blocked} blocked`, active: ram || disk, open: true },
    { name: "VRAM", icon: Layers3, value: `${v.vram_used} / ${v.vram_total}`, note: `${v.vram_wait} waiting`, active: vram, open: true },
  ];
  return <section className="panel machine" aria-labelledby="machine-title">
    <header className="panel-head">
      <div className="heading-with-icon"><span className="panel-icon"><Cpu size={18} /></span>
        <div><h2 id="machine-title">Live machine</h2><p>Resource topology</p></div></div>
      <span className={`pill machine-state ${playing ? "active" : ""}`}><Radio size={13} />{playing ? "Live" : s ? "Snapshot" : "Offline"}</span>
    </header>
    <div className="topology">
      <svg viewBox="0 0 300 200" preserveAspectRatio="none" aria-hidden="true" className="topology-wires">
        <path d="M50 50H250 M50 150V50 M250 150V50 M50 150H150V100H50" />
        <path className={v.bus_busy ? "wire-active" : ""} d="M50 50H250" />
        <path className={ram ? "wire-danger" : ""} d="M50 150H150" />
        <path className={disk || cpuIdle ? "wire-danger" : ""} d="M150 150V100H50V50" />
        <path className={vram ? "wire-danger" : ""} d="M250 150V50" />
      </svg>
      {nodes.map(({ name, icon: Icon, value, note, pid, active, open }) => {
        const content = <><span className="node-label"><Icon size={14} />{name}</span>
          <strong>{s ? value : "—"}</strong><small>{s ? note : ""}</small></>;
        return open || pid != null
          ? <button key={name} className={`node ${active ? "pressure" : ""}`} type="button" onClick={() => pid != null ? inspect(pid) : openResources()}>{content}</button>
          : <div key={name} className={`node ${active ? "pressure" : ""}`}>{content}</div>;
      })}
    </div>
    <footer className="machine-foot">
      <span className={disk || ram || vram ? "warning-text" : ""}><span className="signal-dot" />{s ? route : "Create a session to see resource flow"}</span>
      <button type="button" className="machine-link" onClick={openResources}>Inspect <ArrowRight size={14} /></button>
    </footer>
  </section>;
}

function Trend({ store, disabled, rewind, replay }: {
  store: Store; disabled: boolean; rewind: (tick: number) => void; replay: () => void;
}) {
  const samples = useData(store, s => s.samples);
  const tick = useData(store, s => s.frame?.snapshot.tick ?? 0);
  const frame = useData(store, s => s.frame);
  const crisis = frame?.status.crisis_at;
  const checkpoints = frame?.status.checkpoints ?? [0];
  const manual = frame?.status.manual ?? [];
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const chosen = Math.min(selected ?? tick, tick);
  const nearest = checkpoints.findLast(value => value <= chosen) ?? 0;
  const points = samples.filter(sample => sample.response !== null);
  const duration = Math.max(40, tick);
  const ymax = Math.max(8, ...points.map(point => point.response ?? 0));
  const width = 300, chartTop = 16, chartBase = 120;
  const x = (t: number) => 6 + t / duration * (width - 12);
  const y = (r: number) => chartTop + (1 - r / ymax) * (chartBase - chartTop);
  const interval = Math.max(1, Math.ceil(points.length / 320));
  const plotted = points.filter((_, index) => index % interval === 0 || index === points.length - 1);
  const line = plotted.map(point => `${x(point.tick)},${y(point.response!)}`).join(" ");
  const area = points.length ? `${x(points[0].tick)},${chartBase} ${line} ${x(points.at(-1)!.tick)},${chartBase}` : "";
  const probe = hover ?? (selected === null ? null : chosen);
  const highlighted = probe === null ? points.at(-1) : points.reduce<typeof points[number] | undefined>(
    (closest, point) => !closest || Math.abs(point.tick - probe) < Math.abs(closest.tick - probe) ? point : closest, undefined);
  const dots = checkpoints.filter((value, index) => value === nearest || manual.includes(value) ||
    index % Math.max(1, Math.ceil(checkpoints.length / 20)) === 0);
  return <section className="panel trend" aria-labelledby="trend-title">
    <header className="panel-head"><div className="heading-with-icon"><span className="panel-icon"><Activity size={18} /></span>
      <div><h2 id="trend-title">Interactive response</h2><p>P95 to first CPU dispatch · observed frames</p></div></div>
      <span className="pill chart-unit">Ticks</span>
    </header>
    <div className="trend-reading"><strong>{highlighted?.response ?? "—"}</strong><span>{highlighted ? `at tick ${highlighted.tick}` : "Waiting for a dispatch"}</span></div>
    <div className="chart">
      <div className="y-axis"><span>{ymax}</span><span>{Math.round(ymax / 2)}</span><span>0</span></div>
      <svg viewBox="0 0 300 132" preserveAspectRatio="none" role="img" aria-label="Interactive response history"
        onPointerMove={event => {
          const b = event.currentTarget.getBoundingClientRect();
          setHover(((event.clientX - b.left) / b.width * width - 6) / (width - 12) * duration);
        }} onPointerLeave={() => setHover(null)}>
        <defs><linearGradient id="response-line"><stop stopColor="#9580fc" /><stop offset="1" stopColor="#ff9e90" /></linearGradient>
          <linearGradient id="response-area" x2="0" y2="1" gradientUnits="objectBoundingBox">
            <stop stopColor="#a387ff" stopOpacity=".39" /><stop offset="1" stopColor="#a387ff" stopOpacity="0" />
          </linearGradient></defs>
        {[chartTop, (chartTop + chartBase) / 2, chartBase].map(row => <line key={row} x1="0" x2={width} y1={row} y2={row} className="chart-grid" />)}
        {area && <><polygon points={area} fill="url(#response-area)" /><polyline points={line} fill="none" stroke="url(#response-line)"
          strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></>}
        {crisis != null && <line x1={x(crisis)} x2={x(crisis)} y1="5" y2={chartBase} className="chart-crisis" />}
        {highlighted?.response != null && <circle cx={x(highlighted.tick)} cy={y(highlighted.response)} r="4" className="chart-point" />}
      </svg>
    </div>
    <div className="chart-axis"><span>0</span><span>{Math.floor(duration / 2)}</span><span>{duration}</span></div>
    <div className="timeline">
      <div className="timeline-title"><span><Bookmark size={13} /> Timeline</span><span>Tick {fmt(chosen)} <span className="muted">· save {fmt(nearest)}</span></span></div>
      <div className="scrub-track">
        <div className="scrub-inner" aria-hidden="true">
          {dots.map(value => <i key={value} title={`Checkpoint ${value}`}
            className={manual.includes(value) || value === nearest ? "marked" : ""} style={{ left: `${value / Math.max(1, tick) * 100}%` }} />)}
          {crisis != null && <b title={`Crisis at ${crisis}`} style={{ left: `${crisis / Math.max(1, tick) * 100}%` }}>⚑</b>}
        </div>
        <input type="range" aria-label="Timeline tick" aria-valuetext={`Tick ${chosen}, nearest checkpoint ${nearest}`}
          min={0} max={Math.max(1, tick)} value={chosen} disabled={!tick || disabled}
          onChange={event => setSelected(Number(event.target.value))} />
      </div>
      <div className="timeline-buttons">
        <button type="button" className="button compact" disabled={disabled || !frame} onClick={() => {
          rewind(chosen);
          setSelected(null);
        }}><RotateCcw size={14} /> Rewind here</button>
        <button type="button" className="button compact accent-soft" disabled={disabled || !frame} onClick={replay}>Replay with… <ArrowRight size={13} /></button>
      </div>
    </div>
  </section>;
}

export function GaugeCard({ store }: { store: Store }) {
  const s = useData(store, data => data.frame?.snapshot);
  return <section className="panel pressure-card">
    <header className="panel-head"><div className="heading-with-icon"><span className="panel-icon"><Gauge size={18} /></span>
      <div><h2>Memory pressure</h2><p>Frame occupancy</p></div></div></header>
    <div className="gauges">
      {[["RAM", s?.ram_used, s?.ram_total], ["VRAM", s?.vram_used, s?.vram_total]].map(([label, used, total]) => {
        const ratio = typeof total === "number" && total > 0 && typeof used === "number" ? Math.round(used / total * 100) : null;
        return <div className={`gauge ${label === "RAM" ? "ram-gauge" : "vram-gauge"}`} key={label}>
          <div className="gauge-ring" style={{ "--fill": `${Math.min(ratio ?? 0, 100)}%` } as React.CSSProperties}>
            <strong>{ratio === null ? "—" : `${ratio}%`}</strong>
          </div>
          <div><b>{label}</b><small>{used ?? "—"} / {total ?? "—"} frames</small></div>
        </div>;
      })}
    </div>
  </section>;
}

function TaskQueues({ store, inspect }: { store: Store; inspect: (pid: number) => void }) {
  const s = useData(store, data => data.frame?.snapshot);
  const tasks = useData(store, data => data.frame?.tasks);
  const active: Task[] = tasks?.filter(task => !["new", "done", "killed"].includes(task.state)) ?? [];
  const shown = [...active.filter(task => task.id === s?.running || task.id === s?.gpu_running),
    ...active.filter(task => task.id !== s?.running && task.id !== s?.gpu_running)].slice(0, 4);
  return <section className="panel queue-card">
    <header className="panel-head"><div className="heading-with-icon"><span className="panel-icon"><ListChecks size={18} /></span>
      <div><h2>Queues</h2><p>CPU, GPU and storage</p></div></div></header>
    <div className="queue-counts"><span><b>{s?.ready ?? "—"}</b> CPU ready</span><span><b>{s?.gpu_queue ?? "—"}</b> GPU queued</span><span><b>{s?.disk_queue ?? "—"}</b> Disk I/O</span></div>
    {shown.length ? <div className="small-tasks">{shown.map(task =>
      <button className="task-chip" key={task.id} type="button" onClick={() => inspect(task.id)}>
        <KindDot kind={task.kind} /> PID {task.id} <span>{task.state}</span>
      </button>)}</div> : <p className="quiet">No active processes in the queues.</p>}
  </section>;
}

function EventFeed({ store, openKernel }: { store: Store; openKernel: () => void }) {
  const events = useData(store, data => data.events);
  const recent = events.slice(-4).reverse();
  return <section className="panel event-feed">
    <header className="panel-head"><div className="heading-with-icon"><span className="panel-icon"><TerminalSquare size={18} /></span>
      <div><h2>Recent kernel events</h2><p>Live scheduler and device activity</p></div></div>
      <button type="button" className="text-button" onClick={openKernel}>Kernel log <ArrowRight size={14} /></button>
    </header>
    {recent.length ? <ol>{recent.map(event => <li key={event.index}>
      <span className={`level ${event.level.toLowerCase()}`}>{event.level}</span>
      <span>t{event.tick} · {event.subsystem} · {event.kind}{event.pid === null ? "" : ` · PID ${event.pid}`}</span>
      {event.info && <span className="quiet">{event.info}</span>}
    </li>)}</ol> : <p className="quiet">Events appear after the first task is admitted.</p>}
  </section>;
}

export function Dashboard({ store, options, disabled, inspect, rewind, replay, openResources, openKernel }: {
  store: Store; options: Options | null; disabled: boolean; inspect: (pid: number) => void;
  rewind: (tick: number) => void; replay: () => void; openResources: () => void; openKernel: () => void;
}) {
  return <>
    <div className="stats"><TickStat store={store} /><FinishedStat store={store} /><CpuStat store={store} /><CrisisStat store={store} /></div>
    <div className="hero-grid">
      <Machine store={store} options={options} inspect={inspect} openResources={openResources} />
      <Trend store={store} disabled={disabled} rewind={rewind} replay={replay} />
    </div>
    <div className="bottom-grid"><GaugeCard store={store} /><TaskQueues store={store} inspect={inspect} /></div>
    <EventFeed store={store} openKernel={openKernel} />
  </>;
}

const actionNames: Record<string, string> = {
  new: "Created simulation", step: "Stepped simulation", checkpoint: "Saved checkpoint", rewind: "Rewound timeline",
  replay: "Applied policies", play: "Started playback", pause: "Paused playback", speed: "Changed playback speed",
  resize: "Resized machine", storm: "Triggered workload surge", inject: "Injected tasks", kill: "Terminated process",
  boost: "Changed task priority", finish: "Finished branch", run: "Advanced simulation",
};

export function ActionRail({ actions, loading, compare }: { actions: Action[]; loading: boolean; compare: () => void }) {
  return <aside className="activity-rail" aria-labelledby="actions-title" id="actions">
    <div className="panel action-panel">
      <header className="panel-head"><div className="heading-with-icon">
        <span className="panel-icon"><Zap size={17} /></span><div><h2 id="actions-title">What you did</h2><p>Session action log</p></div></div>
        <span className="pill action-count">{actions.length}</span>
      </header>
      {actions.length ? <ol className="action-list" tabIndex={0} aria-label="Recorded session actions">{actions.slice().reverse().map((entry, i) =>
        <li key={`${actions.length - i}-${entry.action}`}>
          <div className="action-mark"><span /></div>
          <div><span className="action-stamp">TICK {fmt(entry.tick)} {entry.branch !== "main" && `· ${entry.branch}`}</span>
            <b>{actionNames[entry.action] ?? entry.action}</b>
            {entry.effect && <p>{entry.effect}</p>}</div>
        </li>)}</ol> : <p className="quiet action-empty">{loading ? "Connecting to the session…" : "Run controls and machine changes will appear here."}</p>}
    </div>
    <div className="rail-note">
      <span className="rail-note-icon"><ArrowDownRight size={18} /></span>
      <div><b>Counterfactual replay</b><p>Return to a saved tick and compare how a different policy handles the same workload.</p>
        <button type="button" className="text-button" onClick={compare}>Open comparison <ArrowRight size={13} /></button></div>
    </div>
  </aside>;
}
