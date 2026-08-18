import { Check, Minus, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import type { TripInputField, TripInputRequest } from "../types";

type TripInputValues = Record<string, TripInputField["value"]>;

function initialValues(request: TripInputRequest): TripInputValues {
  return Object.fromEntries(request.fields.map((field) => [field.id, field.value]));
}

function selectedLabel(field: TripInputField, value: TripInputField["value"]): string {
  if (field.kind === "boolean") return value ? "Yes" : "No";
  if (field.kind === "number") return String(value);
  if (field.kind === "text" || field.kind === "date") {
    return String(value ?? "").trim() || "not specified";
  }
  const selected = Array.isArray(value) ? value : [value];
  return selected
    .map((item) => field.options?.find((option) => option.value === item)?.label ?? item)
    .join(", ");
}

export function formatTripInputResponse(
  request: TripInputRequest,
  values: TripInputValues,
): string {
  const choices = request.fields.map(
    (field) => `- ${field.label}: ${selectedLabel(field, values[field.id])}`,
  );
  return `Use these choices for this trip:\n${choices.join("\n")}`;
}

interface Props {
  request: TripInputRequest;
  disabled?: boolean;
  onSubmit: (values: TripInputValues) => void;
  onSkip: () => void;
}

export default function TripInputCard({ request, disabled = false, onSubmit, onSkip }: Props) {
  const [values, setValues] = useState<TripInputValues>(() => initialValues(request));
  const update = (field: TripInputField, value: TripInputField["value"]) => {
    setValues((current) => ({ ...current, [field.id]: value }));
  };

  return (
    <section className="max-w-[96%] rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-card" aria-label="Trip choices">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">{request.question}</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">Tap only what matters; the choices are already filled in.</p>
        </div>
        <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700 ring-1 ring-emerald-200">Quick step</span>
      </div>

      {request.known_context.length > 0 && (
        <div className="mt-2 text-[11px] leading-relaxed text-emerald-800">
          <span className="font-semibold">Already applied:</span> {request.known_context.join(" · ")}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        {request.fields.map((field) => {
          const value = values[field.id];
          if (field.kind === "single" || field.kind === "multi") {
            const selected = Array.isArray(value) ? value.map(String) : [String(value)];
            return (
              <fieldset key={field.id}>
                <legend className="text-xs font-semibold text-slate-700">{field.label}</legend>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {field.options?.map((option) => {
                    const active = selected.includes(option.value);
                    return (
                      <label key={option.value} className={`cursor-pointer rounded-full px-2.5 py-1.5 text-xs ring-1 ${active ? "bg-brand-50 text-brand ring-brand/30" : "text-slate-600 ring-slate-200 hover:ring-slate-300"}`}>
                        <input
                          className="sr-only"
                          type={field.kind === "single" ? "radio" : "checkbox"}
                          name={field.id}
                          checked={active}
                          onChange={() => {
                            if (field.kind === "single") update(field, option.value);
                            else update(field, active ? selected.filter((item) => item !== option.value) : [...selected, option.value]);
                          }}
                          disabled={disabled}
                        />
                        <span className="flex items-center gap-1.5 font-semibold">{active && <Check size={12} aria-hidden />}{option.label}</span>
                        {option.detail && <span className="mt-0.5 block text-[10px] font-normal text-slate-500">{option.detail}</span>}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            );
          }
          if (field.kind === "number") {
            const number = Number(value);
            const step = field.step ?? 1;
            return (
              <div key={field.id} className="flex h-9 items-center gap-2 rounded-full bg-slate-50 px-2.5 ring-1 ring-inset ring-slate-200">
                <span className="text-xs font-semibold text-slate-700">{field.label}</span>
                <div className="flex items-center gap-3">
                  <button type="button" onClick={() => update(field, Math.max(field.min ?? 1, number - step))} disabled={disabled || number <= (field.min ?? 1)} className="grid h-7 w-7 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 disabled:opacity-40" aria-label={`Decrease ${field.label}`}><Minus size={13} /></button>
                  <span className="w-6 text-center text-sm font-semibold">{number}</span>
                  <button type="button" onClick={() => update(field, Math.min(field.max ?? 12, number + step))} disabled={disabled || number >= (field.max ?? 12)} className="grid h-7 w-7 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 disabled:opacity-40" aria-label={`Increase ${field.label}`}><Plus size={13} /></button>
                </div>
              </div>
            );
          }
          if (field.kind === "text" || field.kind === "date") {
            return (
              <label key={field.id} className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-700">{field.label}</span>
                <input
                  type={field.kind === "date" ? "date" : "text"}
                  value={String(value ?? "")}
                  placeholder={field.placeholder}
                  onChange={(event) => update(field, event.target.value)}
                  disabled={disabled}
                  className="h-9 rounded-full bg-slate-50 px-3 text-sm text-ink ring-1 ring-inset ring-slate-200 focus:outline-none focus:ring-2 focus:ring-brand/30 disabled:opacity-50"
                />
              </label>
            );
          }
          return (
            <button key={field.id} type="button" aria-pressed={Boolean(value)} onClick={() => update(field, !value)} disabled={disabled} className="flex h-9 items-center gap-2 rounded-full bg-slate-50 px-3 text-left ring-1 ring-inset ring-slate-200 disabled:opacity-50">
              <span className="text-xs font-semibold text-slate-700">{field.label}</span>
              <span className={`relative h-6 w-10 rounded-full transition ${value ? "bg-accent" : "bg-slate-300"}`}><span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${value ? "left-5" : "left-1"}`} /></span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
        {request.allow_skip ? <button type="button" onClick={onSkip} disabled={disabled} className="text-xs font-semibold text-slate-500 hover:text-ink disabled:opacity-40">Use saved defaults</button> : <span />}
        <button type="button" onClick={() => onSubmit(values)} disabled={disabled} className="btn-primary"><Sparkles size={14} /> {request.submit_label}</button>
      </div>
    </section>
  );
}