import type { ReactNode } from "react";

/** No dead ends: wherever a list is empty, say why and offer the way to fill it. */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty" aria-label={title}>
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {action}
    </section>
  );
}
