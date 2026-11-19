"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Activity, ArrowRight, Bookmark, ChevronRight, CircleHelp, CircleStop, Command, Download,
  GitBranch, LayoutDashboard, Menu, Moon, Orbit, Pause, Play, Plus, Radio, RotateCcw, Scale,
  Settings2, SkipForward, Sun, TerminalSquare, TriangleAlert, X, Zap,
} from "lucide-react";
import {
  api, base, baseline, createStore, dimensions, errorText, saveFile, useData,
  type Action, type Branch, type Config, type Frame, type Options, type Policies, type Store,
} from "./data";
import { ActionRail, Dashboard } from "./dashboard";
import { Comparison, Runs } from "./compare";
import { Inspector, Resources, Scenarios, type Mutate } from "./resources";
import { TerminalDrawer } from "./terminal";
import { Dialog, PolicyFields } from "./ui";

const pages = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, description: "Monitor resource contention and replay the same workload with different policies." },
  { id: "resources", label: "Resources", icon: Activity, description: "Inspect who owns memory and which workloads use each device." },
  { id: "compare", label: "Compare", icon: Scale, description: "Measure how scheduling choices affect the same seeded workload." },
  { id: "runs", label: "Runs", icon: GitBranch, description: "Review the original simulation and its counterfactual branches." },
  { id: "scenarios", label: "Scenarios", icon: Zap, description: "Change the workload or machine capacity while the simulation runs." },
  { id: "help", label: "Lab guide", icon: CircleHelp, description: "A walkthrough of the simulation and its operating systems model." },
] as const;
type Page = typeof pages[number]["id"];
type Panel = "new" | "replay" | "settings" | null;
type SocketCommand = { type: "play" | "pause" | "subscribe"; speed?: number; detail?: boolean; token?: string; request?: number };
type Response = Frame | { frame?: Frame; config?: Config };

function extractFrame(result: Response) {
  return "snapshot" in result ? result : result.frame;
}

export default function Home() {
  const [store] = useState(createStore);
  const [options, setOptions] = useState<Options | null>(null);
  const config = useData(store, s => s.frame?.config) ?? baseline;
  const [id, setId] = useState("");
  const [page, setPage] = useState<Page>("dashboard");
  const [panel, setPanel] = useState<Panel>(null);
  const [terminal, setTerminal] = useState<"shell" | "kernel" | null>(null);
  const [inspector, setInspector] = useState<number | null>(null);
  const [token, setToken] = useState("");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [menu, setMenu] = useState(false);
  const [speed, setSpeed] = useState(20);
  const [error, setError] = useState("");
  const [booting, setBooting] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [socketState, setSocketState] = useState<"off" | "connecting" | "open">("off");
  const [pendingPlay, setPendingPlay] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const queued = useRef<SocketCommand | null>(null);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRequest = useRef(0);
  const details = useRef(false);
  const operation = useRef(false);
  const currentId = useRef("");
  const applyId = (value: string) => {
    currentId.current = value;
    setId(value);
    if (value) sessionStorage.setItem("orbit-session", value);
  };

  useEffect(() => {
    const value = sessionStorage.getItem("orbit-token");
    if (value) setToken(value);
    setTheme(localStorage.getItem("orbit-theme") === "light" ? "light" : "dark");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const savedToken = sessionStorage.getItem("orbit-token") ?? "";
    const link = new URLSearchParams(location.search).get("session");
    const remembered = link ?? sessionStorage.getItem("orbit-session");
    async function start() {
      setBooting(true); setError("");
      try {
        const settings = await api<Options>("/api/options", undefined, "", controller.signal);
        if (controller.signal.aborted) return;
        setOptions(settings);
        if (remembered) {
          try {
            const frame = await api<Frame>(`/api/sessions/${encodeURIComponent(remembered)}/frame?since=0`, undefined, "", controller.signal);
            if (controller.signal.aborted) return;
            store.ingest(frame);
            applyId(remembered);
            return;
          } catch (err) {
            if (controller.signal.aborted) return;
            sessionStorage.removeItem("orbit-session");
            if (link) throw err;
          }
        }
        if (settings.token_required && !savedToken) return;
        const created = await api<{ id: string; frame: Frame; config: Config }>("/api/sessions", baseline, savedToken, controller.signal);
        if (controller.signal.aborted) return;
        store.reset();
        store.ingest(created.frame);
        applyId(created.id);
      } catch (err) {
        if (!controller.signal.aborted) setError(errorText(err));
      } finally {
        if (!controller.signal.aborted) setBooting(false);
      }
    }
    void start();
    return () => controller.abort();
  }, [attempt, store]);

  function clearPending() {
    if (pendingTimer.current) clearTimeout(pendingTimer.current);
    pendingTimer.current = null;
    setPendingPlay(false);
  }

  useEffect(() => {
    if (!id) return;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout>;
    function connect() {
      const url = new URL(`${base}/api/sessions/${encodeURIComponent(id)}/stream`, location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      setSocketState("connecting");
      const ws = new WebSocket(url);
      socket.current = ws;
      ws.onopen = () => {
        if (stopped) return;
        setSocketState("open");
        ws.send(JSON.stringify({ type: "subscribe", detail: details.current }));
        if (queued.current) {
          ws.send(JSON.stringify(queued.current));
          queued.current = null;
        }
      };
      ws.onmessage = message => {
        if (stopped || currentId.current !== id) return;
        const data = JSON.parse(message.data) as Frame | { type: "error"; detail: string; request?: number };
        if ("type" in data) {
          if (data.request == null || data.request === latestRequest.current) {
            clearPending(); setError(data.detail);
          }
        } else {
          store.ingest(data);
          if (data.request === latestRequest.current) clearPending();
        }
      };
      ws.onclose = () => {
        if (stopped || currentId.current !== id) return;
        setSocketState("off");
        queued.current = null;
        clearPending();
        retry = setTimeout(connect, 1500);
      };
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      socket.current?.close();
      socket.current = null;
    };
  }, [id, store]);

  useEffect(() => {
    details.current = page === "resources";
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify({ type: "subscribe", detail: details.current }));
    }
    if (!details.current || !id) return;
    const controller = new AbortController();
    const cursor = store.get().frame?.cursor ?? 0;
    api<Frame>(`/api/sessions/${encodeURIComponent(id)}/frame?detail=1&since=${cursor}`, undefined, "", controller.signal)
      .then(frame => { if (!controller.signal.aborted && currentId.current === id) store.ingest(frame); })
      .catch(err => { if (!controller.signal.aborted) setError(errorText(err)); });
    return () => controller.abort();
  }, [id, page, store]);

  function navigate(value: Page) {
    setPage(value); setMenu(false);
    window.scrollTo(0, 0);
  }

  function sendPlayback(type: "play" | "pause", rate = speed) {
    if (speedTimer.current) clearTimeout(speedTimer.current);
    setError("");
    const request = ++latestRequest.current;
    const cmd: SocketCommand = { type, speed: rate, detail: details.current, token, request };
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(cmd));
    else queued.current = cmd;
    setPendingPlay(true);
    if (pendingTimer.current) clearTimeout(pendingTimer.current);
    pendingTimer.current = setTimeout(() => {
      queued.current = null;
      clearPending();
      setError("Live stream is unavailable. Reconnect or use Step.");
    }, 4000);
  }

  async function newRun(values: Config, autoPlay = false) {
    if (operation.current) return;
    operation.current = true;
    if (speedTimer.current) clearTimeout(speedTimer.current);
    setBusy(true); setError("");
    try {
      const created = await api<{ id: string; frame: Frame; config: Config }>("/api/sessions", values, token);
      socket.current?.close();
      clearPending();
      queued.current = null;
      store.reset(); store.ingest(created.frame);
      applyId(created.id);
      if (autoPlay) {
        // The new session's socket will consume the command when it connects.
        socket.current = null;
        sendPlayback("play");
      }
      if (new URLSearchParams(location.search).has("session")) history.replaceState(null, "", location.pathname);
      setPanel(null); navigate("dashboard");
    } catch (err) { setError(errorText(err)); }
    finally { operation.current = false; setBusy(false); }
  }

  const mutate: Mutate = async (action, params = {}) => {
    if (!id || operation.current) return false;
    operation.current = true;
    if (speedTimer.current) clearTimeout(speedTimer.current);
    setBusy(true); setError("");
    try {
      const result = await api<Response>(`/api/sessions/${encodeURIComponent(id)}/${action}`, params, token);
      const frame = extractFrame(result);
      if (frame && id === currentId.current) store.ingest(frame);
      return true;
    } catch (err) { setError(errorText(err)); return false; }
    finally { operation.current = false; setBusy(false); }
  };

  async function shell(line: string) {
    if (!id) return ["Create or open a simulation first."];
    if (operation.current) return ["Waiting for another session action. Try again shortly."];
    operation.current = true;
    setBusy(true);
    try {
      const result = await api<{ output: string[]; frame?: Frame; config?: Config }>(
        `/api/sessions/${encodeURIComponent(id)}/shell`, { line }, token);
      if (id === currentId.current) {
        if (result.frame) store.ingest(result.frame);
      }
      return result.output;
    } catch (err) { return [errorText(err)]; }
    finally { operation.current = false; setBusy(false); }
  }

  async function exportRun() {
    if (!id) return;
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(id)}/export`);
      saveFile(`orbit-run-${config.seed}.json`, JSON.stringify(data, null, 2), "application/json");
    } catch (err) { setError(errorText(err)); }
  }

  const navigation = pages.find(item => item.id === page)!;
  const readOnly = !!options?.token_required && !token;
  const unavailable = busy || !id || readOnly;
  const serviceLabel = socketState === "open" ? "Connected" : booting || socketState === "connecting" ? "Connecting" :
    id ? "Disconnected" : options ? "API ready" : "Offline";

  return <div className="app" data-theme={theme}>
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    {menu && <button className="nav-scrim" type="button" tabIndex={-1} aria-label="Close navigation" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? "menu-open" : ""}`}>
      <button type="button" className="brand" onClick={() => navigate("dashboard")}><span className="brand-mark"><Orbit size={25} /></span>
        <span><b>ORBIT<span>-OS</span></b><small>Simulation Console</small></span></button>
      <nav aria-label="Workspace">
        <span className="nav-label">Workspace</span>
        {pages.slice(0, 4).map(item => <NavItem key={item.id} item={item} page={page} navigate={navigate} />)}
        <span className="nav-label nav-label-secondary">Lab tools</span>
        {pages.slice(4).map(item => <NavItem key={item.id} item={item} page={page} navigate={navigate} />)}
        <button className="nav-item" type="button" onClick={() => { setTerminal("shell"); setMenu(false); }}><TerminalSquare size={18} /><span>ORBIT Shell</span></button>
      </nav>
      <div className="sidebar-bottom">
        <button className="nav-item" type="button" onClick={() => { setPanel("settings"); setMenu(false); }}>
          <Settings2 size={18} /><span>Settings</span></button>
        <button className="nav-item theme-toggle" type="button" aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => { const next = theme === "dark" ? "light" : "dark"; setTheme(next); localStorage.setItem("orbit-theme", next); }}>
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}<span>{theme === "dark" ? "Light theme" : "Dark theme"}</span>
        </button>
        <div className="sidebar-status"><span className="status-dot" /><span>Simulated machine</span></div>
      </div>
    </aside>
    <main className="shell-main" id="workspace">
      <header className="topbar">
        <div className="crumb"><button type="button" className="icon-button mobile-menu" aria-label={menu ? "Close navigation" : "Open navigation"}
          aria-expanded={menu} onClick={() => setMenu(!menu)}>{menu ? <X size={20} /> : <Menu size={20} />}</button>
          <span className="crumb-root">Workspace</span><ChevronRight size={13} className="crumb-chevron" /><b>{navigation.label}</b></div>
        <div className="top-tools">
          <span className={`connection ${socketState === "open" ? "connected" : ""}`}><span className="status-dot" />{serviceLabel}</span>
          <button type="button" className="icon-button top-shell" aria-label="Open ORBIT Shell" title="Open ORBIT Shell" onClick={() => setTerminal("shell")}><TerminalSquare size={18} /></button>
          <button type="button" className="icon-button" aria-label="Export run JSON" title="Export run JSON" disabled={!id} onClick={() => void exportRun()}><Download size={18} /></button>
          <button type="button" className="icon-button mobile-settings" aria-label="Settings" title="Settings" onClick={() => setPanel("settings")}><Settings2 size={18} /></button>
        </div>
      </header>

      <div className="workspace-body">
        <div className="page-heading">
          <div><h1>{page === "dashboard" ? "Simulation overview" : navigation.label}</h1><p>{navigation.description}</p></div>
          <button className="button new-button" type="button" disabled={!options || busy} onClick={() => setPanel("new")}><Plus size={17} /> New simulation</button>
        </div>
        {error && <div className="error-banner" role="alert"><TriangleAlert size={17} /><span>{error}</span>
          {!options && <button className="button compact" type="button" onClick={() => setAttempt(attempt + 1)}>Retry</button>}
          <button className="icon-button" type="button" aria-label="Dismiss message" onClick={() => setError("")}><X size={15} /></button></div>}
        {readOnly && <div className="access-banner"><span>{id ? "Spectator view" : "Demo access is protected"}</span>
          <button className="text-button" type="button" onClick={() => setPanel("settings")}>Enter demo token <ArrowRight size={14} /></button></div>}
        <Transport store={store} config={config} speed={speed} disabled={busy || readOnly || booting || !options} pending={pendingPlay}
          active={!!id} onPlay={playing => id ? sendPlayback(playing ? "pause" : "play") : void newRun(config, true)}
          onSpeed={value => {
            setSpeed(value);
            if (speedTimer.current) clearTimeout(speedTimer.current);
            if (store.get().frame?.status.playing) {
              speedTimer.current = setTimeout(() => {
                if (store.get().frame?.status.playing) sendPlayback("play", value);
              }, 140);
            }
          }}
          step={() => void mutate("step", { n: 1 })} checkpoint={() => void mutate("checkpoint")}
          policies={() => setPanel(id ? "replay" : "new")} compare={() => navigate("compare")} />
        <div className="workspace-grid">
          <div className="surface-stack">
            {page === "dashboard" && <Dashboard store={store} options={options} disabled={unavailable} inspect={setInspector}
              rewind={tick => void mutate("rewind", { tick })} replay={() => setPanel("replay")} openResources={() => navigate("resources")} openKernel={() => setTerminal("kernel")} />}
            {page === "resources" && <Resources store={store} inspect={setInspector} />}
            {page === "scenarios" && <Scenarios store={store} mutate={mutate} disabled={unavailable} />}
            {(page === "compare" || page === "runs") && <BranchView key={`${id}-${config.seed}-${config.n_tasks}-${config.ram}-${config.vram}`} id={id}
              store={store} config={config} options={options} mutate={mutate} busy={unavailable} page={page} />}
            {page === "help" && <Guide compare={() => navigate("compare")} />}
          </div>
          <RecordedActions id={id} store={store} loading={booting} compare={() => navigate("compare")} />
        </div>
      </div>
    </main>
    {panel === "new" && options && <NewDialog options={options} config={config} busy={busy || readOnly}
      close={() => setPanel(null)} submit={newRun} error={error} />}
    {panel === "replay" && options && <PolicyDialog options={options} current={store.get().frame?.status.policies ?? options.defaults}
      busy={unavailable} close={() => setPanel(null)} error={error} submit={async values => {
        if (await mutate("replay", values)) setPanel(null);
      }} />}
    {panel === "settings" && <Settings token={token} id={id} save={value => {
      sessionStorage.setItem("orbit-token", value);
      setToken(value); setPanel(null); setError("");
    }} close={() => setPanel(null)} />}
    {inspector !== null && <Inspector key={inspector} pid={inspector} store={store} close={() => setInspector(null)} mutate={mutate} disabled={unavailable} />}
    <TerminalDrawer tab={terminal} setTab={setTerminal} close={() => setTerminal(null)} send={shell} active={!!id} store={store} inspect={setInspector} />
  </div>;
}

function NavItem({ item, page, navigate }: { item: typeof pages[number]; page: Page; navigate: (page: Page) => void }) {
  const Icon = item.icon;
  return <button className="nav-item" type="button" aria-current={page === item.id ? "page" : undefined} onClick={() => navigate(item.id)}>
    <Icon size={18} /><span>{item.label}</span>{page === item.id && <ChevronRight size={14} className="nav-arrow" />}
  </button>;
}

function Transport({ store, config, speed, disabled, pending, active, onPlay, onSpeed, step, checkpoint, policies, compare }: {
  store: Store; config: Config; speed: number; disabled: boolean; pending: boolean; active: boolean; onPlay: (playing: boolean) => void;
  onSpeed: (value: number) => void; step: () => void; checkpoint: () => void; policies: () => void; compare: () => void;
}) {
  const playing = useData(store, s => s.frame?.status.playing ?? false);
  const done = useData(store, s => s.frame?.status.done ?? false);
  const timedOut = useData(store, s => s.frame?.status.timed_out ?? false);
  const remaining = useData(store, s => s.frame?.summary?.unfinished);
  const stoppedAt = useData(store, s => s.frame?.summary?.makespan);
  const cpu = useData(store, s => s.frame?.status.policies.cpu) ?? config.cpu;
  const page = useData(store, s => s.frame?.status.policies.page) ?? config.page;
  const disk = useData(store, s => s.frame?.status.policies.disk) ?? config.disk;
  const place = useData(store, s => s.frame?.status.policies.place) ?? config.place;
  return <>
    <section className="panel transport" aria-label="Simulation controls">
      <button className="scenario-select" type="button" onClick={policies} disabled={disabled}>
        <span className="control-icon"><Command size={17} /></span><span><b>Seed {config.seed}</b><small>{cpu} / {page} / {disk} / {place}</small></span>
        <Settings2 size={14} className="scenario-chevron" />
      </button>
      <div className="transport-actions">
        <button className="button primary run-button" type="button" disabled={disabled || pending || done || timedOut} onClick={() => onPlay(playing)}>
          {playing ? <Pause size={16} fill="currentColor" /> : <Play size={15} fill="currentColor" />}{playing ? "Pause" : "Run"}
        </button>
        <button className="button" type="button" disabled={disabled || pending || !active || done || timedOut} onClick={step}><SkipForward size={16} /> Step</button>
        <button className="button control-checkpoint" type="button" disabled={disabled || !active} onClick={checkpoint}><Bookmark size={16} /> Checkpoint</button>
      </div>
      <label className="speed-control"><span>Speed <b>{speed} t/s</b></span><input type="range" aria-label="Playback speed" min={1} max={200}
        value={speed} onChange={event => onSpeed(Number(event.target.value))} /></label>
      <button className="icon-button compare-shortcut" type="button" aria-label="Open comparison" title="Open comparison" onClick={compare}><Scale size={18} /></button>
    </section>
    {timedOut && <div className="stop-banner" role="status"><TriangleAlert size={18} /><span><b>Thrashing · stopped at {stoppedAt} ticks.</b> {remaining} unfinished.</span></div>}
    {done && <div className="stop-banner complete" role="status"><CircleStop size={17} /> Branch complete · tick {stoppedAt}.</div>}
  </>;
}

function RecordedActions({ id, store, loading, compare }: { id: string; store: Store; loading: boolean; compare: () => void }) {
  const version = useData(store, s => s.frame?.action_version);
  const generation = useData(store, s => s.frame?.generation);
  const [record, setRecord] = useState<{ id: string; generation?: number; actions: Action[] } | null>(null);
  useEffect(() => {
    if (!id || version === undefined) return;
    const abort = new AbortController();
    api<Action[]>(`/api/sessions/${encodeURIComponent(id)}/actions`, undefined, "", abort.signal)
      .then(actions => { if (!abort.signal.aborted) setRecord({ id, generation, actions }); })
      .catch(() => {});
    return () => abort.abort();
  }, [id, version, generation]);
  const actions = record && record.id === id && record.generation === generation ? record.actions : [];
  return <ActionRail actions={actions} loading={loading} compare={compare} />;
}

function BranchView({ id, store, config, options, mutate, busy, page }: {
  id: string; store: Store; config: Config; options: Options | null; mutate: Mutate; busy: boolean; page: "compare" | "runs";
}) {
  const count = useData(store, s => s.frame?.action_count);
  const generation = useData(store, s => s.frame?.generation);
  const done = useData(store, s => s.frame?.status.done);
  const timedOut = useData(store, s => s.frame?.status.timed_out);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    api<Branch[]>(`/api/sessions/${encodeURIComponent(id)}/branches`, undefined, "", abort.signal)
      .then(value => { if (!abort.signal.aborted) { setBranches(value); setError(""); } })
      .catch(err => { if (!abort.signal.aborted) setError(errorText(err)); });
    return () => abort.abort();
  }, [id, count, generation, done, timedOut]);
  return <>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {page === "compare" ? <Comparison store={store} config={config} branches={branches} options={options} mutate={mutate} busy={busy} />
      : <Runs branches={branches} store={store} mutate={mutate} busy={busy} />}
  </>;
}

function NewDialog({ options, config, busy, close, submit, error }: {
  options: Options; config: Config; busy: boolean; close: () => void;
  submit: (config: Config, autoPlay?: boolean) => Promise<void>; error: string;
}) {
  const [draft, setDraft] = useState(config);
  function preset(value: "crisis" | "balanced" | "thrash") {
    setDraft(value === "crisis" ? baseline : value === "balanced" ? { ...baseline, ...options.defaults } :
      { ...baseline, ram: 30, place: "CPU" });
  }
  return <Dialog title="New simulation" onClose={close}>
    <form className="dialog-body" onSubmit={event => { event.preventDefault(); void submit(draft); }}>
      <div className="preset-row">
        <button className="button compact" type="button" onClick={() => preset("crisis")}>Crisis demo</button>
        <button className="button compact" type="button" onClick={() => preset("balanced")}>Balanced</button>
        <button className="button compact" type="button" onClick={() => preset("thrash")}>Thrashing demo</button>
      </div>
      <div className="policy-fields">
        {([["seed", "Seed"], ["n_tasks", "Tasks", 1, 200], ["ram", "RAM frames", 1, 200], ["vram", "VRAM frames", 0, 64]] as const).map(([key, label, min, max]) =>
          <label key={key}>{label}<input type="number" min={min} max={max} required value={Number.isNaN(draft[key]) ? "" : draft[key]} onChange={event =>
            setDraft({ ...draft, [key]: event.target.valueAsNumber })} /></label>)}
      </div>
      <PolicyFields options={options} value={draft} onChange={values => setDraft({ ...draft, ...values })} />
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="form-actions"><button type="button" className="button" onClick={close}>Cancel</button>
        <button type="submit" className="button primary" disabled={busy}>Create simulation</button></div>
    </form>
  </Dialog>;
}

function PolicyDialog({ options, current, busy, close, submit, error }: {
  options: Options; current: Policies; busy: boolean; close: () => void;
  submit: (values: Policies) => Promise<void>; error: string;
}) {
  const [draft, setDraft] = useState(current);
  const changed = dimensions.some(key => draft[key] !== current[key]);
  return <Dialog title="Replay with different policies" onClose={close}>
    <form className="dialog-body" onSubmit={event => {
      event.preventDefault();
      void submit(Object.fromEntries(dimensions.filter(key => draft[key] !== current[key]).map(key => [key, draft[key]])) as Policies);
    }}>
      <p className="quiet">Policies take effect at the active tick. Placement changes apply to future arrivals.</p>
      <PolicyFields options={options} value={draft} onChange={setDraft} />
      <button type="button" className="button compact" onClick={() => setDraft(options.defaults)}><RotateCcw size={13} /> Use engine defaults</button>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="form-actions"><button type="button" className="button" onClick={close}>Cancel</button>
        <button type="submit" className="button primary" disabled={busy || !changed}>Apply policies</button></div>
    </form>
  </Dialog>;
}

function Settings({ token, id, save, close }: { token: string; id: string; save: (token: string) => void; close: () => void }) {
  const [draft, setDraft] = useState(token);
  const [message, setMessage] = useState("");
  const submit = (event: FormEvent) => { event.preventDefault(); save(draft.trim()); };
  return <Dialog title="Simulation settings" onClose={close}>
    <form className="dialog-body" onSubmit={submit}>
      <label>Demo token<input type="password" autoComplete="off" value={draft} onChange={event => setDraft(event.target.value)} /></label>
      <p className="quiet">Enter the token configured on the server to control a protected demo. It is kept in this browser tab.</p>
      {id && <button className="button" type="button" onClick={async () => {
        try {
          const url = new URL(location.pathname, location.origin);
          url.searchParams.set("session", id);
          await navigator.clipboard.writeText(url.toString());
          setMessage("Session link copied.");
        } catch { setMessage("Clipboard unavailable."); }
      }}>Copy spectator link</button>}
      {message && <p className="quiet" role="status">{message}</p>}
      <div className="form-actions"><button type="submit" className="button primary">Save settings</button></div>
    </form>
  </Dialog>;
}

function Guide({ compare }: { compare: () => void }) {
  return <section className="panel padded guide">
    <div className="section-heading"><span className="panel-icon"><Radio size={18} /></span><div><h2>Run the crisis demo</h2><p>Seeded workload · simulated ticks</p></div></div>
    <ol><li>Choose <b>Crisis demo</b> in New simulation. Start at 20 ticks/s.</li>
      <li>When the disk queue reaches the crisis threshold, inspect blocked tasks and page faults. The shell commands <code>free</code> and <code>iostat</code> expose the same state.</li>
      <li>Pause and rewind to checkpoint 40. Apply MLFQ, LRU, and SCAN to the replay branch.</li>
      <li>Compare both branches after they finish. Look at makespan, wait time, and interactive turnaround together.</li></ol>
    <button className="button" type="button" onClick={compare}>Open comparison <ArrowRight size={15} /></button>
    <h3>Deadlock lab</h3><p>Banker’s algorithm and wait-for-graph cycle detection are implemented as standalone exercises. The live machine’s crisis marker measures disk queue pressure.</p>
    <h3>GPU model</h3><p>NEXUS estimates CPU, GPU, and hybrid placement using parallel fractions, transfer time, and available VRAM. Work and time are simulated.</p>
  </section>;
}
