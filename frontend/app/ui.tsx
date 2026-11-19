"use client";

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { Maximize2, Minimize2, X } from "lucide-react";
import { dimensions, labels, workload, type Kind, type Options, type Policies } from "./data";

export function Dialog({ title, children, onClose, drawer = false }: {
  title: string; children: ReactNode; onClose: () => void; drawer?: boolean;
}) {
  const element = useRef<HTMLDialogElement>(null);
  // A drawer is a floating window like a Mac app: not modal, so the dashboard behind stays usable.
  // Drag it by the title bar; double-click the title bar or use the button for full screen.
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [full, setFull] = useState(false);
  const grab = useRef<{ dx: number; dy: number } | null>(null);
  useEffect(() => {
    const dialog = element.current;
    if (drawer) dialog?.show(); else dialog?.showModal();
    return () => dialog?.close();
  }, [drawer]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (full) setFull(false); else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer, full, onClose]);

  const startDrag = (event: ReactPointerEvent<HTMLElement>) => {
    const box = element.current?.getBoundingClientRect();
    if (!drawer || full || !box || (event.target as HTMLElement).closest("button")) return;
    grab.current = { dx: event.clientX - box.left, dy: event.clientY - box.top };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const drag = (event: ReactPointerEvent<HTMLElement>) => {
    const box = element.current?.getBoundingClientRect();
    if (!grab.current || !box) return;
    const x = Math.min(Math.max(0, event.clientX - grab.current.dx), window.innerWidth - Math.min(box.width, 120));
    const y = Math.min(Math.max(0, event.clientY - grab.current.dy), window.innerHeight - 48);
    setPos({ x, y });
  };
  const drop = () => { grab.current = null; };

  const classes = ["dialog", drawer && "drawer", drawer && full && "full", drawer && pos && !full && "moved"].filter(Boolean).join(" ");
  return <dialog ref={element} className={classes} aria-label={title}
    style={drawer && pos && !full ? { left: pos.x, top: pos.y } : undefined}
    onCancel={event => { event.preventDefault(); if (!drawer) onClose(); }}
    onClick={event => {
      if (!drawer && event.target === event.currentTarget) {
        const b = event.currentTarget.getBoundingClientRect();
        if (event.clientX < b.left || event.clientX > b.right || event.clientY < b.top || event.clientY > b.bottom) onClose();
      }
    }}>
    <header className={drawer ? "dialog-head grabbable" : "dialog-head"} onPointerDown={startDrag} onPointerMove={drag}
      onPointerUp={drop} onPointerCancel={drop} onDoubleClick={() => drawer && setFull(value => !value)}>
      <h2>{title}</h2>
      <div className="dialog-actions">
        {drawer && <button type="button" className="icon-button" aria-label={full ? "Exit full screen" : "Full screen"}
          title={full ? "Exit full screen (Esc)" : "Full screen (double-click title)"} onClick={() => setFull(value => !value)}>
          {full ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>}
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
      </div>
    </header>
    {children}
  </dialog>;
}

export function PolicyFields({ options, value, onChange }: {
  options: Options; value: Policies; onChange: (value: Policies) => void;
}) {
  return <div className="policy-fields">{dimensions.map(key =>
    <label key={key}>{labels[key]}
      <select value={value[key]} onChange={event => onChange({ ...value, [key]: event.target.value })}>
        {options[key].map(name => <option key={name}>{name}</option>)}
      </select>
    </label>)}</div>;
}

export function KindDot({ kind }: { kind: Kind }) {
  return <span className={`kind-dot ${kind}`} title={workload[kind]} aria-hidden="true" />;
}

export function Legend() {
  return <div className="legend">{Object.entries(workload).map(([kind, label]) =>
    <span key={kind}><KindDot kind={kind as Kind} />{label}</span>
  )}</div>;
}
