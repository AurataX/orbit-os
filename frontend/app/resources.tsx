"use client";

import { useState } from "react";
import { Activity, Cpu, HardDrive, Layers3, MemoryStick, SlidersHorizontal, Zap } from "lucide-react";
import { lanes, workload, useData, type Kind, type Store } from "./data";
import { Dialog, KindDot, Legend } from "./ui";

export type Mutate = (action: string, params?: Record<string, unknown>) => Promise<boolean>;

export function Resources({ store, inspect }: { store: Store; inspect: (pid: number) => void }) {
  const snapshot = useData(store, s => s.frame?.snapshot);
  const tasks = useData(store, s => s.frame?.tasks);
  const samples = useData(store, s => s.samples);
  const kinds = new Map(tasks?.map(task => [task.id, task.kind]));
  const span = samples.slice(-32);
  const ram = snapshot?.ram_frames;
  const vram = snapshot?.vram_held;
  const disk = snapshot?.disk;
  return <>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><Activity size={18} /></span><div>
        <h2>Shared resource lanes</h2><p>One cell per observed frame. Latest samples are on the right.</p>
      </div></div>
      <Legend />
      <div className="lane-view">
        {lanes.map(lane => {
          const tallies: Partial<Record<Kind, number>> = {};
          let observed = 0;
          for (const frame of span) {
            const slot = frame.occupancy[lane];
            if (slot !== undefined) observed++;
            if (slot) tallies[slot.kind] = (tallies[slot.kind] ?? 0) + 1;
          }
          return <div className="lane" key={lane}>
            <b>{lane}</b>
            <div className="lane-cells">
              {span.length ? span.map(sample => {
                const slot = sample.occupancy[lane];
                const label = `${lane}, tick ${sample.tick}, ${slot ? `PID ${slot.pid} · ${workload[slot.kind]}` : slot === null ? "idle" : "not sampled"}`;
                return slot ? <button key={sample.tick} type="button" className={`cell ${slot.kind}`} title={label}
                  aria-label={label} onClick={() => inspect(slot.pid)} />
                  : <span key={sample.tick} className={`cell ${slot === undefined ? "unobserved" : ""}`} title={label} />;
              }) : <span className="quiet">Waiting for frames</span>}
            </div>
            <div className="share-legend" aria-label={`${lane} sample shares`}>
              {Object.entries(tallies).map(([kind, count]) => <span key={kind}><KindDot kind={kind as Kind} />
                {workload[kind as Kind]} {Math.round(count / observed * 100)}%</span>)}
              {observed > 0 && <span>Idle {Math.round((observed - Object.values(tallies).reduce((a, b) => a + b, 0)) / observed * 100)}%</span>}
              {!observed && <span>Waiting for samples</span>}
            </div>
            <div className="share-bar" aria-hidden="true">
              {Object.entries(tallies).map(([kind, count]) => <i key={kind} className={kind} style={{ width: `${count / observed * 100}%` }} />)}
            </div>
          </div>;
        })}
      </div>
    </section>
    <div className="resource-grid">
      <section className="panel padded">
        <div className="section-heading"><span className="panel-icon"><MemoryStick size={18} /></span><div>
          <h2>RAM ownership</h2><p>{snapshot ? `${snapshot.ram_used} of ${snapshot.ram_total} frames · oldest first` : "Page resident order"}</p>
        </div></div>
        {ram ? <div className="frame-map">
          {Array.from({ length: snapshot!.ram_total }, (_, i) => {
            const frame = ram[i];
            if (!frame) return <i className="cell" key={i} title="Free RAM frame" />;
            const [pid, page] = frame;
            return <button key={`${pid}-${page}`} type="button" className={`cell ${kinds.get(pid) ?? ""}`} title={`PID ${pid} · page ${page}`}
              aria-label={`RAM frame: PID ${pid}, page ${page}`} onClick={() => inspect(pid)} />;
          })}
        </div> : <p className="quiet">Waiting for a detailed snapshot.</p>}
      </section>
      <section className="panel padded">
        <div className="section-heading"><span className="panel-icon"><Layers3 size={18} /></span><div>
          <h2>VRAM ownership</h2><p>{snapshot ? `${snapshot.vram_used} of ${snapshot.vram_total} frames held` : "GPU memory allocations"}</p>
        </div></div>
        {vram ? <div className="ownership">
          {Object.entries(vram).map(([pid, count]) => <button type="button" key={pid} className="task-chip" onClick={() => inspect(Number(pid))}>
            {kinds.has(Number(pid)) && <KindDot kind={kinds.get(Number(pid))!} />} PID {pid} <span>{count} frames</span>
          </button>)}
          {Object.keys(vram).length === 0 && <p className="quiet">No active allocations.</p>}
        </div> : <p className="quiet">Waiting for a detailed snapshot.</p>}
      </section>
    </div>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><HardDrive size={18} /></span><div>
        <h2>Disk head &amp; queue</h2><p>{disk ? `Head at track ${disk.head}` : "Waiting for a detailed snapshot"}</p>
      </div></div>
      {disk && <>
        <div className="disk-track" aria-label={`Disk head at track ${disk.head} of 199`}>
          <i style={{ left: `${disk.head / 199 * 100}%` }} /><span>0</span><span>199</span>
        </div>
        <div className="ownership">
          {disk.current && <button type="button" className="task-chip" onClick={() => inspect(disk.current!.task)}>
            Serving PID {disk.current.task} <span>track {disk.current.track}</span>
          </button>}
          {disk.queue.map((request, i) => <button type="button" className="task-chip" key={`${request.task}-${i}`} onClick={() => inspect(request.task)}>
            PID {request.task} <span>track {request.track}</span>
          </button>)}
          {!disk.current && !disk.queue.length && <p className="quiet">The disk queue is empty.</p>}
        </div>
      </>}
    </section>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><Cpu size={18} /></span><div><h2>Process table</h2><p>Select a PID to inspect its state and events.</p></div></div>
      <div className="table-scroll process-scroll" tabIndex={0} aria-label="Process table">
        <table><thead><tr><th>PID</th><th>Class</th><th>State</th><th>Placement</th><th>Priority</th><th>Work left</th></tr></thead>
          <tbody>{tasks?.map(task => <tr key={task.id}>
            <th scope="row"><button className="text-button" type="button" onClick={() => inspect(task.id)}>PID {task.id}</button></th>
            <td><KindDot kind={task.kind} /> {workload[task.kind]}</td><td>{task.state}</td><td>{task.placement}</td>
            <td>{task.priority}</td><td>{task.left} / {task.burst}</td>
          </tr>)}</tbody></table>
      </div>
      {!tasks?.length && <p className="quiet">No processes to show.</p>}
    </section>
  </>;
}

export function Scenarios({ store, mutate, disabled }: { store: Store; mutate: Mutate; disabled: boolean }) {
  const currentRam = useData(store, s => s.frame?.snapshot.ram_total ?? 60);
  const currentVram = useData(store, s => s.frame?.snapshot.vram_total ?? 16);
  const [ram, setRam] = useState<number | null>(null);
  const [vram, setVram] = useState<number | null>(null);
  const [kind, setKind] = useState<Kind>("interactive");
  const [count, setCount] = useState(4);
  return <>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><Zap size={18} /></span><div>
        <h2>Stress the machine</h2><p>Inject a deterministic burst at the active tick.</p>
      </div></div>
      <div className="scenario-grid">
        {[
          ["ai-burst", "AI burst", "4 AI jobs compete for VRAM and transfer time."],
          ["compile-storm", "Compile storm", "8 build jobs compete for CPU and storage."],
          ["swap-storm", "Swap storm", "6 build jobs and 6 background jobs add RAM pressure."],
        ].map(([name, label, detail]) => <div key={name} className="scenario">
          <h3>{label}</h3><p>{detail}</p><button className="button compact" type="button" disabled={disabled}
            onClick={() => void mutate("storm", { name })}><Zap size={14} /> Trigger surge</button>
        </div>)}
      </div>
      <form className="inline-form" onSubmit={event => { event.preventDefault(); void mutate("inject", { kind, n: count }); }}>
        <label>Workload class<select value={kind} onChange={event => setKind(event.target.value as Kind)}>
          {Object.entries(workload).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>Tasks<input type="number" min={1} max={50} required value={count || ""} onChange={event => setCount(Number(event.target.value))} /></label>
        <button type="submit" className="button" disabled={disabled}>Inject tasks</button>
      </form>
    </section>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><SlidersHorizontal size={18} /></span><div>
        <h2>Resize the machine</h2><p>RAM shrink can evict pages immediately. Held VRAM is released as tasks finish.</p>
      </div></div>
      <form className="resize-form" onSubmit={async event => {
        event.preventDefault();
        if (await mutate("resize", { ...(ram === null ? {} : { ram }), ...(vram === null ? {} : { vram }) })) {
          setRam(null); setVram(null);
        }
      }}>
        <label><span>RAM frames <strong>{ram ?? currentRam}</strong></span>
          <input type="range" min={10} max={200} value={ram ?? currentRam} onChange={event => setRam(Number(event.target.value))} />
        </label>
        <label><span>VRAM frames <strong>{vram ?? currentVram}</strong></span>
          <input type="range" min={0} max={64} value={vram ?? currentVram} onChange={event => setVram(Number(event.target.value))} />
        </label>
        <button className="button primary" type="submit" disabled={disabled || (ram === null && vram === null)}>Apply machine size</button>
      </form>
    </section>
  </>;
}

export function Inspector({ pid, store, close, mutate, disabled }: {
  pid: number; store: Store; close: () => void; mutate: Mutate; disabled: boolean;
}) {
  const task = useData(store, s => s.frame?.tasks.find(entry => entry.id === pid));
  const allEvents = useData(store, s => s.events);
  const priorityPolicy = useData(store, s => s.frame?.status.policies.cpu === "Priority");
  const events = allEvents.filter(event => event.pid === pid);
  const reason = events.findLast(event => event.kind === "place");
  const [priority, setPriority] = useState<number | null>(null);
  const [confirmKill, setConfirmKill] = useState(false);
  const isLive = task && !["killed", "done"].includes(task.state);
  return <Dialog title={`Process inspector · PID ${pid}`} onClose={close}>
    <div className="dialog-body">
      {task ? <>
        <div className="inspector-type"><KindDot kind={task.kind} /><b>{workload[task.kind]}</b><span className="pill">{task.state}</span></div>
        <dl className="inspect-grid">
          <div><dt>Placement</dt><dd>{task.placement}</dd></div><div><dt>Priority</dt><dd>{task.priority}</dd></div>
          <div><dt>Original burst</dt><dd>{task.burst} ticks</dd></div><div><dt>Work left</dt><dd>{task.left}</dd></div>
        </dl>
        <h3>NEXUS placement reason</h3><p className="quiet">{reason?.info || "No placement event in the retained history."}</p>
        <h3>Recent process events</h3>
        <ul className="inspect-events">{events.slice(-8).reverse().map(event =>
          <li key={event.index}><span>t{event.tick}</span><b>{event.kind}</b>{event.info}</li>)}</ul>
        {!events.length && <p className="quiet">No retained events for this process yet.</p>}
        {isLive && <>
          <form className="inline-form" onSubmit={event => { event.preventDefault(); void mutate("boost", { pid, priority: priority ?? task.priority }); }}>
            <label>Priority<input type="number" required value={priority ?? task.priority}
              onChange={event => setPriority(Number(event.target.value))} /></label>
            <button className="button" type="submit" disabled={disabled}>Update priority</button>
          </form>
          <p className="quiet">{priorityPolicy ? "Lower numbers run first under Priority scheduling." : "Only the Priority scheduler uses this number."}</p>
          <button className="button danger" type="button" disabled={disabled} onClick={() => {
            if (confirmKill) void mutate("kill", { pid });
            else setConfirmKill(true);
          }}>{confirmKill ? `Confirm termination of PID ${pid}` : "Terminate task"}</button>
        </> }
      </> : <p className="quiet">This PID is absent from the active branch.</p>}
    </div>
  </Dialog>;
}
