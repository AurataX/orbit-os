"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { dimensions, labels, workload, type Kind, type Options, type Policies } from "./data";

export function Dialog({ title, children, onClose, drawer = false }: {
  title: string; children: ReactNode; onClose: () => void; drawer?: boolean;
}) {
  const element = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = element.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={element} className={drawer ? "dialog drawer" : "dialog"} aria-label={title}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => {
      if (event.target === event.currentTarget) {
        const b = event.currentTarget.getBoundingClientRect();
        if (event.clientX < b.left || event.clientX > b.right || event.clientY < b.top || event.clientY > b.bottom) onClose();
      }
    }}>
    <header className="dialog-head"><h2>{title}</h2><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></header>
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
