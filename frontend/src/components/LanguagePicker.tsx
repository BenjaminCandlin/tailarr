import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";

import { api, type Language } from "@/lib/api";
import { cn } from "@/lib/utils";

export const SELECT_CLASS =
  "h-11 w-full min-w-0 cursor-pointer rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm";

/** The languages Tailarr knows (common ones first). Loaded once. */
export function useLanguages(): Language[] {
  const query = useQuery({ queryKey: ["languages"], queryFn: api.languages, staleTime: Infinity });
  return query.data ?? [];
}

function Options({ languages, exclude = [] }: { languages: Language[]; exclude?: string[] }) {
  const common = languages.filter((l) => l.common && !exclude.includes(l.code));
  const others = languages.filter((l) => !l.common && !exclude.includes(l.code));
  return (
    <>
      <optgroup label="Common languages">
        {common.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </optgroup>
      <optgroup label="All languages">
        {others.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </optgroup>
    </>
  );
}

export function languageName(languages: Language[], code: string): string {
  return languages.find((l) => l.code === code)?.name ?? code;
}

/** Choose one or more languages: chosen ones show as removable chips. */
export function LanguagePicker({
  value,
  onChange,
  label,
  id,
}: {
  value: string[];
  onChange: (codes: string[]) => void;
  /** Read out for the "add a language" box, e.g. "Add a subtitle language to keep". */
  label: string;
  id: string;
}) {
  const languages = useLanguages();
  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Chosen languages">
          {value.map((code) => (
            <li key={code}>
              <button
                type="button"
                onClick={() => onChange(value.filter((c) => c !== code))}
                className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-full border border-primary/50 bg-accent px-3 text-sm font-medium text-accent-foreground hover:bg-accent/70"
                aria-label={`Remove ${languageName(languages, code)}`}
              >
                {languageName(languages, code)}
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <select
        id={id}
        value=""
        onChange={(e) => e.target.value && onChange([...value, e.target.value])}
        className={cn(SELECT_CLASS, "text-muted-foreground")}
      >
        <option value="">{value.length ? "Add another language…" : "Choose a language…"}</option>
        <Options languages={languages} exclude={value} />
      </select>
    </div>
  );
}

/** Choose a single language. */
export function LanguageSelect({
  value,
  onChange,
  id,
  noneLabel,
}: {
  value: string | null;
  onChange: (code: string | null) => void;
  id: string;
  noneLabel: string;
}) {
  const languages = useLanguages();
  return (
    <select
      id={id}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      className={SELECT_CLASS}
    >
      <option value="">{noneLabel}</option>
      <Options languages={languages} />
    </select>
  );
}
