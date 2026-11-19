"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, CornerDownLeft, Link2 } from "lucide-react";
import { useData, type Event, type Store } from "./data";
import { Dialog } from "./ui";

const subsystems = ["all", "sched", "nexus", "mm", "disk", "vram", "bus", "gpu", "lock", "kernel"];
const shellShortcuts = ["top", "free", "iostat", "gpustat", "dmesg nexus 10", "help"];

function related(events: Event[], selected: Event) {
  if (selected.pid === null) return [selected];
  const pid = events.filter(event => event.pid === selected.pid);
  const pairs = [["block", "wake"], ["vram_wait", "vram_grant"]];
  const pair = pairs.find(names => names.includes(selected.kind));
  if (pair) {
    const other = selected.kind === pair[0]
      ? pid.find(event => event.index > selected.index && pair.includes(event.kind))
      : pid.findLast(event => event.index < selected.index && pair.includes(event.kind));
    return other && other.kind !== selected.kind ? [selected, other].sort((a, b) => a.index - b.index) : [selected];
  }
  const placement = ["arrive", "place", "xfer", "gpu_queue", "gpu_run", "finish"];
  return placement.includes(selected.kind) ? pid.filter(event => placement.includes(event.kind)) : [selected];
}

function useTerminal({ tab, send, active }: {
  tab: "shell" | "kernel" | null; send: (line: string) => Promise<string[]>; active: boolean;
}) {
  const [line, setLine] = useState("");
  const [lines, setLines] = useState<string[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [at, setAt] = useState<number | null>(null);
  const [working, setWorking] = useState(false);
  const output = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (output.current) output.current.scrollTop = output.current.scrollHeight;
  }, [lines, tab]);
  async function submit(value: string) {
    const text = value.trim();
    if (!text || working) return;
    setLine("");
    setAt(null);
    setHistory(previous => [...previous, text]);
    if (text === "clear") { setLines([]); return; }
    setWorking(true);
    setLines(previous => [...previous, `orbit> ${text}`]);
    const result = await send(text);
    setLines(previous => [...previous, ...result, ""].slice(-3000));
    setWorking(false);
  }
  return {
    shell: <div className="terminal-body">
      <div className="terminal-shortcuts">{shellShortcuts.map(value =>
        <button className="button compact" key={value} type="button" disabled={!active || working} onClick={() => void submit(value)}>{value}</button>
      )}</div>
      <div className="terminal-output" ref={output} role="log" aria-label="Shell output" aria-live="polite" tabIndex={0}>
        {lines.length ? lines.map((value, index) => <div className={value.startsWith("orbit>") ? "prompt-line" : ""} key={index}>{value || "\u00a0"}</div>)
          : <div>{active ? "Type help for available simulator commands." : "Create or open a simulation to use the ORBIT shell."}</div>}
      </div>
      <form className="terminal-form" onSubmit={event => { event.preventDefault(); void submit(line); }}>
        <label htmlFor="command-line">orbit&gt;</label>
        <input id="command-line" aria-label="ORBIT command" placeholder="help" autoComplete="off" spellCheck={false} disabled={!active}
          value={line} onChange={event => setLine(event.target.value)} onKeyDown={event => {
            if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
            event.preventDefault();
            const next = Math.max(0, Math.min(history.length, (at ?? history.length) + (event.key === "ArrowUp" ? -1 : 1)));
            setAt(next); setLine(history[next] ?? "");
          }} />
        <button type="submit" className="icon-button" aria-label="Submit command" disabled={working || !active}><CornerDownLeft size={18} /></button>
      </form>
    </div>,
  };
}

export function TerminalDrawer({ tab, setTab, close, send, active, store, inspect }: {
  tab: "shell" | "kernel" | null; setTab: (tab: "shell" | "kernel") => void;
  close: () => void; send: (line: string) => Promise<string[]>; active: boolean; store: Store; inspect: (pid: number) => void;
}) {
  const terminal = useTerminal({ tab, send, active });
  return tab ? <Dialog title="ORBIT Shell" onClose={close} drawer>
    <div className="tab-strip terminal-tabs">
      <button type="button" aria-pressed={tab === "shell"} onClick={() => setTab("shell")}>Shell</button>
      <button type="button" aria-pressed={tab === "kernel"} onClick={() => setTab("kernel")}>Kernel log</button>
    </div>
    {tab === "shell" ? terminal.shell : <KernelLog store={store} inspect={pid => { close(); inspect(pid); }} />}
  </Dialog> : null;
}

function KernelLog({ store, inspect }: { store: Store; inspect: (pid: number) => void }) {
  const events = useData(store, s => s.events);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<Event | null>(null);
  const cause = selected && events.includes(selected) ? related(events, selected) : [];
  const ids = new Set(cause.map(event => event.index));
  const shown = events.filter(event => filter === "all" || filter === event.subsystem).slice(-100).reverse();
  return <div className="terminal-body kernel">
    <div className="terminal-shortcuts">
      {subsystems.map(name => <button type="button" className="button compact" key={name} aria-pressed={filter === name}
        onClick={() => setFilter(name)}>{name}</button>)}
    </div>
    {!!cause.length && <div className="cause"><h3><Link2 size={15} /> Related events {selected?.pid != null && `· PID ${selected.pid}`}</h3>
      <div>{cause.map(event => <span key={event.index}>t{event.tick} {event.kind} <ArrowRight size={12} /></span>)}</div>
    </div>}
    <ol className="kernel-list" aria-label="Kernel events">
      {shown.map(event => <li key={event.index} className={ids.has(event.index) ? "highlight-event" : ""}>
        <span className={`level ${event.level.toLowerCase()}`}>{event.level}</span>
        <div><span className="kernel-meta">t{event.tick} · {event.subsystem} · {event.kind}
          {event.pid != null && <> · <button className="text-button" type="button" onClick={() => inspect(event.pid!)}>PID {event.pid}</button></>}
        </span><p>{event.info || event.text}</p></div>
        <button className="button compact" type="button" aria-pressed={ids.has(event.index)} onClick={() => setSelected(event)}>Why?</button>
      </li>)}
    </ol>
    {!shown.length && <p className="quiet">No events match this filter yet.</p>}
  </div>;
}
