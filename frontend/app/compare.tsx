"use client";

import { useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, Download, GitBranch, Scale, Trophy } from "lucide-react";
import {
  api, dimensions, errorText, labels, saveFile, useData,
  type Branch, type Config, type Dimension, type Options, type Store, type Summary, type Tables,
} from "./data";
import type { Mutate } from "./resources";

const metrics: { key: keyof Summary; title: string; better?: "low" | "high" }[] = [
  { key: "inter_p95_turn", title: "Interactive p95 turnaround", better: "low" },
  { key: "inter_p95_resp", title: "Interactive p95 response", better: "low" },
  { key: "makespan", title: "Makespan", better: "low" },
  { key: "avg_wait", title: "Avg. wait", better: "low" },
  { key: "unfinished", title: "Unfinished", better: "low" },
  { key: "page_faults", title: "Page faults", better: "low" },
  { key: "cpu_util_%", title: "CPU utilization", better: "high" },
  { key: "disk_busy", title: "Disk busy" },
  { key: "head_moved", title: "Disk head travel", better: "low" },
  { key: "gpu_stall", title: "GPU stalls", better: "low" },
  { key: "gpu_busy", title: "GPU busy" },
  { key: "bus_busy", title: "Bus busy" },
  { key: "killed", title: "Terminated" },
  { key: "crisis_at", title: "Crisis tick" },
];
const display = (value: string | number, key?: keyof Summary) => typeof value === "number"
  ? `${value.toLocaleString("en-US")}${key === "cpu_util_%" ? "%" : ""}` : value === "-" ? "—" : value;
const diffMetrics = metrics.filter(metric => ["makespan", "inter_p95_turn", "avg_wait", "page_faults", "unfinished"].includes(metric.key));

function DeltaTable({ before, after }: { before: Summary; after: Summary }) {
  const makespanMax = Math.max(1, before.makespan, after.makespan);
  return <><div className="delta-chart" aria-label="Simulated makespan comparison">
    {([["Before", before.makespan], ["After", after.makespan]] as const).map(([label, ticks]) => <div key={label}>
      <span>{label}</span><div className="delta-track" aria-hidden="true"><i style={{ width: `${ticks / makespanMax * 100}%` }} /></div>
      <strong>{display(ticks)} ticks</strong>
    </div>)}
  </div><div className="table-scroll" tabIndex={0} aria-label="Before and after metrics"><table>
    <thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
    <tbody>{diffMetrics.map(({ key, title, better }) => {
      const delta = Number((Number(after[key]) - Number(before[key])).toFixed(1));
      return <tr key={key}><th scope="row">{title}</th><td>{display(before[key])}</td><td>{display(after[key])}</td>
        <td className={delta < 0 && better === "low" ? "improved" : ""}>{delta > 0 ? "+" : ""}{display(delta)}</td></tr>;
    })}</tbody>
  </table></div></>;
}

type WhatIf = { crisis_at: number; rewound_to: number; original: Summary; replayed: Summary; policy_log: string[] };

export function Comparison({ store, config, branches, options, mutate, busy }: {
  store: Store; config: Config; branches: Branch[]; options: Options | null; mutate: Mutate; busy: boolean;
}) {
  const activeId = useData(store, s => s.frame?.status.branch);
  const [tables, setTables] = useState<Tables | null>(null);
  const [whatif, setWhatif] = useState<WhatIf | null>(null);
  const [dimension, setDimension] = useState<Dimension>("cpu");
  const [sort, setSort] = useState<{ key: keyof Summary; asc: boolean }>({ key: "inter_p95_turn", asc: true });
  const [guess, setGuess] = useState("");
  const [result, setResult] = useState<{ correct: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState<"tables" | "whatif" | null>(null);
  const [error, setError] = useState("");
  const branch = branches.find(row => row.id === activeId);
  const parent = branches.find(row => row.id === branch?.parent);
  const rows = [...(tables?.[dimension] ?? [])].sort((a, b) => {
    const aVal = a[sort.key], bVal = b[sort.key];
    if (typeof aVal !== typeof bVal) return typeof aVal === "number" ? -1 : 1;
    return typeof aVal === "number" && typeof bVal === "number" ? (aVal - bVal) * (sort.asc ? 1 : -1) : 0;
  });
  const finishedFewest = rows.length ? Math.min(...rows.map(row => row.unfinished)) : 0;
  async function load(kind: "tables" | "whatif") {
    setLoading(kind); setError("");
    const query = new URLSearchParams({ seed: String(config.seed), tasks: String(config.n_tasks) });
    try {
      if (kind === "whatif") {
        query.set("ram", String(config.ram));
        query.set("vram", String(config.vram));
        setWhatif(await api<WhatIf>(`/api/whatif?${query}`));
      } else {
        const data = await api<Tables>(`/api/compare?${query}`);
        setTables(data);
        if (guess) {
          const eligible = data[dimension].filter(row => row.unfinished === Math.min(...data[dimension].map(r => r.unfinished)));
          const winners = eligible.filter(row => row.inter_p95_turn === eligible[0].inter_p95_turn);
          setResult({ correct: winners.some(row => row.policy === guess),
            text: `${winners.map(row => row.policy).join(" / ")} · p95 turnaround ${eligible[0].inter_p95_turn} ticks · ${eligible[0].unfinished} unfinished` });
        }
      }
    } catch (error) { setError(errorText(error)); }
    finally { setLoading(null); }
  }
  return <>
    <section className="panel padded">
      <div className="section-heading"><span className="panel-icon"><GitBranch size={18} /></span><div>
        <h2>Before vs. after</h2><p>Two branches from the same recorded checkpoint.</p>
      </div></div>
      {branch && parent ? <>
        <div className="branch-pair">
          <div><span>Before · {parent.label}</span><b>{Object.values(parent.policies).join(" / ")}</b><small>{parent.summary ? `Stopped at tick ${parent.tick}` : `Paused at tick ${parent.tick}`}</small></div>
          <ArrowRight size={18} />
          <div><span>After · {branch.label}</span><b>{Object.values(branch.policies).join(" / ")}</b><small>Forked at tick {branch.rewound_to}</small></div>
        </div>
        {parent.summary && branch.summary ? <DeltaTable before={parent.summary} after={branch.summary} />
          : <div className="form-actions">
            {!parent.summary && <button type="button" className="button" disabled={busy} onClick={() => void mutate(`finish?branch=${parent.id}`)}>Finish original branch</button>}
            {!branch.summary && <button type="button" className="button primary" disabled={busy} onClick={() => void mutate("finish")}>Finish replay branch</button>}
          </div>}
      </> : <p className="quiet">Rewind the live timeline, change the policies and finish both branches to see measured differences.</p>}
      <div className="whatif">
        <button className="button" type="button" disabled={!!loading} onClick={() => void load("whatif")}>
          <Scale size={16} /> {loading === "whatif" ? "Simulating…" : "Run seeded crisis experiment"}
        </button>
        <p className="quiet">Fresh run from tick 0 · seed {config.seed} · RAM {config.ram}, VRAM {config.vram} · FCFS / FIFO / FCFS → MLFQ / LRU / SCAN</p>
      </div>
      {whatif && <><p className="comparison-caption">Crisis at tick {whatif.crisis_at} · replay from tick {whatif.rewound_to}</p>
        <DeltaTable before={whatif.original} after={whatif.replayed} /></>}
    </section>
    <section className="panel padded sweep">
      <div className="section-heading"><span className="panel-icon"><Scale size={18} /></span><div>
        <h2>Policy sweep</h2><p>Seed {config.seed} · {config.n_tasks} tasks · default machine. One policy dimension varies per table.</p>
      </div></div>
      <div className="tab-strip">
        {dimensions.map(key => <button key={key} type="button" aria-pressed={dimension === key} disabled={!!loading}
          onClick={() => { setDimension(key); setGuess(""); setResult(null); }}>{labels[key]}</button>)}
      </div>
      <div className="inline-form">
        <label>Predict the winner<select value={guess} onChange={event => { setGuess(event.target.value); setResult(null); }}
          disabled={!options || !!loading}><option value="">Optional challenge</option>{options?.[dimension].map(name => <option key={name}>{name}</option>)}</select></label>
        <button type="button" className="button primary" disabled={!!loading} onClick={() => void load("tables")}>
          {loading === "tables" ? "Comparing…" : "Compare policies"}
        </button>
        {tables && <button type="button" className="button" onClick={() => {
          const csv = ["dimension,policy," + metrics.map(m => m.key).join(","),
            ...dimensions.flatMap(key => tables[key].map(row => [key, row.policy, ...metrics.map(m => row[m.key])].join(",")))];
          saveFile(`orbit-compare-${config.seed}.csv`, csv.join("\n"), "text/csv");
        }}><Download size={16} /> CSV</button>}
      </div>
      {result && <p className="challenge-result"><Trophy size={17} /><strong>{result.correct ? "Prediction matched" : "Prediction missed"}</strong> {result.text}</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {rows.length > 0 && <>
        <div className="table-scroll comparison-table" tabIndex={0} aria-label={`${labels[dimension]} comparison metrics`}><table>
          <thead><tr><th>Policy</th>{metrics.map(({ key, title, better }) => <th key={key}
            aria-sort={sort.key === key ? sort.asc ? "ascending" : "descending" : undefined}>
            <button type="button" onClick={() => setSort({ key, asc: sort.key === key ? !sort.asc : better !== "high" })}>
              {title}{sort.key === key && (sort.asc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
            </button></th>)}</tr></thead>
          <tbody>{rows.map(row => <tr key={row.policy}><th scope="row">{row.policy}</th>
            {metrics.map(({ key, better }) => {
              const eligible = key === "unfinished" ? rows : rows.filter(r => r.unfinished === finishedFewest);
              const values = eligible.map(r => Number(r[key]));
              const best = better && eligible.includes(row) && Number(row[key]) === (better === "low" ? Math.min(...values) : Math.max(...values));
              return <td key={key}><span className={best ? "best-value" : ""}>{display(row[key], key)}</span></td>;
            })}
          </tr>)}</tbody>
        </table></div>
        <p className="quiet comparison-caption">Highlighted values use the fewest unfinished tasks, then each metric’s preferred direction. Times are simulated ticks.</p>
      </>}
    </section>
  </>;
}

export function Runs({ branches, store, mutate, busy }: { branches: Branch[]; store: Store; mutate: Mutate; busy: boolean }) {
  const active = useData(store, s => s.frame?.status.branch);
  return <section className="panel padded">
    <div className="section-heading"><span className="panel-icon"><GitBranch size={18} /></span><div>
      <h2>Recorded branches</h2><p>Original and replay timelines in this session.</p>
    </div></div>
    {!branches.length && <p className="quiet">Create a simulation to record a branch.</p>}
    <div className="branch-list">{branches.map(branch => <div key={branch.id}>
      <div><h3>{branch.label} {active === branch.id && <span className="pill">Active</span>}</h3>
        <p>{Object.values(branch.policies).join(" / ")} · tick {branch.tick}{branch.rewound_to != null ? ` · forked at ${branch.rewound_to}` : ""}</p></div>
      {branch.summary ? <span>{branch.summary.unfinished ? `${branch.summary.unfinished} unfinished` : "Complete"}</span> :
        <button type="button" className="button compact" disabled={busy} onClick={() => void mutate(`finish?branch=${branch.id}`)}>Finish branch</button>}
    </div>)}</div>
  </section>;
}
