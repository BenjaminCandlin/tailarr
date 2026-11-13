import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Eye, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import {
  ActionKindPicker,
  ActionOptions,
  START,
  actionOf,
  choicesFromAction,
  missingChoice,
  type Choices,
} from "@/components/ActionChoices";
import { EmptyState } from "@/components/EmptyState";
import { LanguagePicker, SELECT_CLASS } from "@/components/LanguagePicker";
import { RulePreviewList } from "@/components/RulePreviewList";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, type Condition, type ConditionType, type Rule, type RuleInput } from "@/lib/api";
import { EXAMPLES } from "@/pages/RulesPage";

const CONDITIONS: { type: ConditionType; label: string; languages?: boolean }[] = [
  { type: "has_dolby_vision", label: "it has Dolby Vision" },
  { type: "has_hdr10plus", label: "it has HDR10+" },
  { type: "is_4k", label: "it's 4K" },
  { type: "has_subtitles_not_in", label: "it has subtitles that aren't in…", languages: true },
  { type: "has_audio_not_in", label: "it has audio that isn't in…", languages: true },
];

function BackLink() {
  return (
    <Button asChild variant="ghost" className="-ml-3 mb-3">
      <Link to="/rules">
        <ArrowLeft aria-hidden />
        Rules
      </Link>
    </Button>
  );
}

function Option({
  id,
  checked,
  onChange,
  title,
  text,
  danger = false,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  text: string;
  danger?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        aria-describedby={`${id}-help`}
      />
      <div className="pt-1.5 md:pt-1">
        <label
          htmlFor={id}
          className={`cursor-pointer text-sm font-medium ${danger ? "text-destructive" : ""}`}
        >
          {title}
        </label>
        <p id={`${id}-help`} className="text-xs text-muted-foreground">
          {text}
        </p>
      </div>
    </div>
  );
}

function ConditionsEditor({
  conditions,
  onChange,
}: {
  conditions: Condition[];
  onChange: (conditions: Condition[]) => void;
}) {
  const used = conditions.map((c) => c.type);
  const unused = CONDITIONS.filter((c) => !used.includes(c.type));
  return (
    <div className="flex flex-col gap-3">
      {conditions.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No conditions: the rule applies to every new file (files where there's nothing to do are
          skipped anyway).
        </p>
      )}
      <ul className="flex flex-col gap-3" aria-label="Conditions">
        {conditions.map((condition, index) => {
          const meta = CONDITIONS.find((c) => c.type === condition.type)!;
          return (
            <li key={condition.type} className="flex flex-col gap-2 rounded-lg border p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {index === 0 ? "If" : "and"} {meta.label}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  onClick={() => onChange(conditions.filter((_, i) => i !== index))}
                  aria-label={`Remove the condition “${meta.label}”`}
                >
                  <Trash2 aria-hidden />
                </Button>
              </div>
              {meta.languages && (
                <LanguagePicker
                  id={`condition-${condition.type}`}
                  label="Add a language that's fine"
                  value={condition.languages}
                  onChange={(languages) =>
                    onChange(conditions.map((c, i) => (i === index ? { ...c, languages } : c)))
                  }
                />
              )}
            </li>
          );
        })}
      </ul>
      {unused.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="add-condition" className="text-sm font-medium">
            Add a condition
          </label>
          <select
            id="add-condition"
            value=""
            className={SELECT_CLASS}
            onChange={(e) => {
              const type = e.target.value as ConditionType;
              if (type)
                onChange([
                  ...conditions,
                  { type, languages: type.endsWith("_not_in") ? ["eng"] : [] },
                ]);
            }}
          >
            <option value="">Choose…</option>
            {unused.map((c) => (
              <option key={c.type} value={c.type}>
                {c.label.replace("…", " (languages)")}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

function RuleForm({ initial, ruleId }: { initial: RuleInput; ruleId: number | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState(initial.name);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [scope, setScope] = useState(initial.scope);
  const [conditions, setConditions] = useState<Condition[]>(initial.conditions);
  const [choices, setChoices] = useState<Choices>(() => choicesFromAction(initial.action));
  const [allowOriginals, setAllowOriginals] = useState(initial.allow_originals);
  const [allowHardlinked, setAllowHardlinked] = useState(initial.allow_hardlinked);

  const body = (): RuleInput => ({
    name,
    enabled,
    scope,
    conditions,
    action: actionOf(choices),
    allow_originals: allowOriginals,
    allow_hardlinked: allowOriginals && allowHardlinked,
  });
  const preview = useMutation({ mutationFn: () => api.previewRule(body()) });
  const save = useMutation({
    mutationFn: () => (ruleId === null ? api.createRule(body()) : api.saveRule(ruleId, body())),
    onSuccess: (rule: Rule) => {
      void queryClient.invalidateQueries({ queryKey: ["rules"] });
      navigate("/rules", { state: { saved: rule.id } });
    },
  });
  const set = (change: Partial<Choices>) => {
    setChoices((c) => ({ ...c, ...change }));
    preview.reset();
  };
  const missing =
    missingChoice(choices) ??
    (conditions.some((c) => c.type.endsWith("_not_in") && c.languages.length === 0)
      ? "Choose at least one language for each language condition."
      : null) ??
    (choices.kind === "default_tracks" && !allowOriginals
      ? "Choosing default tracks changes the original files, so switch on “Allowed to change original files”."
      : null) ??
    (name.trim() ? null : "Give the rule a name.");

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!missing) save.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle>Name</CardTitle>
        </CardHeader>
        <CardContent>
          <label htmlFor="rule-name" className="sr-only">
            Rule name
          </label>
          <Input
            id="rule-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="For example: HDR10 copies of Dolby Vision films"
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>When</CardTitle>
          <CardDescription>Which new files the rule looks at.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="rule-scope" className="text-sm font-medium">
              When a new … is added
            </label>
            <select
              id="rule-scope"
              value={scope}
              onChange={(e) => {
                setScope(e.target.value as RuleInput["scope"]);
                preview.reset();
              }}
              className={SELECT_CLASS}
            >
              <option value="films">film</option>
              <option value="tv">episode</option>
              <option value="both">film or episode</option>
            </select>
          </div>
          <ConditionsEditor
            conditions={conditions}
            onChange={(c) => {
              setConditions(c);
              preview.reset();
            }}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Then</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          <ActionKindPicker
            value={choices.kind}
            onChange={(kind) => set({ kind })}
            name="rule-kind"
            wording="files"
          />
          <div className="rounded-xl border p-3">
            <ActionOptions choices={choices} set={set} />
          </div>
          <p className="text-xs text-muted-foreground">
            Rules never replace an original file with a copy: you do that yourself on the film or
            episode page.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Switches</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Option
            id="rule-enabled"
            checked={enabled}
            onChange={setEnabled}
            title="Rule is on"
            text="Off: the rule does nothing by itself, but you can still preview it and run it by hand."
          />
          <Option
            id="rule-originals"
            checked={allowOriginals}
            onChange={(v) => {
              setAllowOriginals(v);
              preview.reset();
            }}
            title="Allowed to change original files"
            text="Needed for “Choose the default audio and subtitles”, which edits the files themselves. Copies never need it. Off by default."
            danger
          />
          {allowOriginals && (
            <Option
              id="rule-hardlinked"
              checked={allowHardlinked}
              onChange={(v) => {
                setAllowHardlinked(v);
                preview.reset();
              }}
              title="Also change files that are still seeding"
              text="Seeding files are the same file as the one in your downloads, so changing them also changes the seeding copy and can break the torrent. Off: they're skipped."
              danger
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>
            What this rule would do if you ran it on your whole library now (with “Preview and run
            now” on the Rules page). Nothing is changed. When the rule is switched on, it only looks
            at new and upgraded files as they arrive: it never goes back through the films already
            there by itself.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => preview.mutate()}
              disabled={Boolean(missingChoice(choices)) || preview.isPending}
            >
              <Eye aria-hidden />
              {preview.isPending ? "Checking your library…" : "Preview this rule"}
            </Button>
          </div>
          {preview.isError && (
            <p role="alert" className="text-sm text-destructive">
              {preview.error.message}
            </p>
          )}
          {preview.data && (
            <>
              <p className="text-sm">{preview.data.sentence}</p>
              <RulePreviewList preview={preview.data} />
            </>
          )}
        </CardContent>
      </Card>

      {(save.isError || missing) && (
        <p
          role={save.isError ? "alert" : undefined}
          className={
            save.isError
              ? "rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
              : "text-sm text-muted-foreground"
          }
        >
          {save.isError ? save.error.message : missing}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={Boolean(missing) || save.isPending}>
          <Plus aria-hidden />
          {save.isPending ? "Saving…" : ruleId === null ? "Save the rule" : "Save changes"}
        </Button>
        <Button asChild variant="ghost">
          <Link to="/rules">Cancel</Link>
        </Button>
      </div>
    </form>
  );
}

const BLANK: RuleInput = {
  name: "",
  enabled: false,
  scope: "films",
  conditions: [],
  action: actionOf(START),
  allow_originals: false,
  allow_hardlinked: false,
};

export function RuleEditorPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const isNew = id === undefined;
  const rule = useQuery({
    queryKey: ["rules", id],
    queryFn: () => api.rule(id!),
    enabled: !isNew,
    retry: false,
  });
  const example = EXAMPLES[Number(params.get("example"))]?.rule;
  return (
    <>
      <BackLink />
      <h1 className="mb-6 text-2xl font-semibold tracking-tight md:text-3xl">
        {isNew ? "New rule" : "Edit rule"}
      </h1>
      {isNew ? (
        <RuleForm initial={example ?? BLANK} ruleId={null} />
      ) : rule.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : rule.isError ? (
        <EmptyState icon={AlertTriangle} title="Rule not found">
          <p>{rule.error.message}</p>
        </EmptyState>
      ) : (
        <RuleForm initial={rule.data} ruleId={rule.data.id} />
      )}
    </>
  );
}
