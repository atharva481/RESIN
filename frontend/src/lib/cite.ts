/** Citation export utilities — BibTeX, APA, MLA. */
import type { Paper } from "@/lib/types";

const slug = (p: Paper) => {
  const first = (p.authors[0] || "anon").split(/\s+/).pop() || "anon";
  return `${first.toLowerCase().replace(/[^a-z]/g, "")}${p.year ?? ""}`;
};

export function toBibTeX(papers: Paper[]): string {
  return papers
    .map((p) => {
      const k = slug(p);
      return `@article{${k},
  title   = {${p.title}},
  author  = {${p.authors.join(" and ")}},
  year    = {${p.year ?? ""}},
  doi     = {${p.doi ?? ""}},
  url     = {${p.open_access_url ?? ""}}
}`;
    })
    .join("\n\n");
}

export function toAPA(papers: Paper[]): string {
  return papers
    .map((p) => {
      const authors = p.authors
        .map((a) => {
          const parts = a.split(/\s+/);
          const last = parts.pop();
          const initials = parts.map((s) => s[0]?.toUpperCase() + ".").join(" ");
          return last ? `${last}, ${initials}` : a;
        })
        .join(", ");
      return `${authors} (${p.year ?? "n.d."}). ${p.title}. ${p.doi ? "https://doi.org/" + p.doi : p.open_access_url ?? ""}`.trim();
    })
    .join("\n\n");
}

export function toMLA(papers: Paper[]): string {
  return papers
    .map((p) => {
      const authors = p.authors.length ? p.authors.join(", ") : "Anonymous";
      return `${authors}. "${p.title}." ${p.year ?? "n.d."}, ${p.doi ? "doi:" + p.doi : p.open_access_url ?? ""}.`;
    })
    .join("\n\n");
}

export function downloadText(filename: string, content: string, mime = "text/plain") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
