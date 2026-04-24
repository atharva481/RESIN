interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="mb-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 animate-fade-up">
      <div className="space-y-2">
        {eyebrow && (
          <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground font-medium">
            {eyebrow}
          </div>
        )}
        <h1 className="font-serif-display text-4xl sm:text-5xl font-semibold tracking-tight text-balance">
          {title}
        </h1>
        {description && (
          <p className="text-muted-foreground max-w-2xl text-balance">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
