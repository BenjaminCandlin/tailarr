/** The tools' own words, tucked away behind "Show technical details". */
export function TechnicalDetails({ details }: { details: string | null | undefined }) {
  if (!details) return null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
        Show technical details
      </summary>
      <pre className="mt-2 max-h-60 overflow-auto rounded bg-background p-3 text-xs whitespace-pre-wrap [overflow-wrap:anywhere]">
        {details}
      </pre>
    </details>
  );
}
