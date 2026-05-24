export interface KVRow {
  k: string;
  v: string;
}

export interface KVProps {
  rows: ReadonlyArray<KVRow>;
}

/**
 * Description-list component matching the landing page's `.kv` block:
 *   <dl class="kv">
 *     <div><dt>label</dt><dd>value</dd></div>
 *     ...
 *   </dl>
 */
export function KV({ rows }: KVProps): JSX.Element {
  return (
    <dl className="kv">
      {rows.map((row) => (
        <div key={row.k}>
          <dt>{row.k}</dt>
          <dd className="mono">{row.v}</dd>
        </div>
      ))}
    </dl>
  );
}
