export const BANGLA_RE = /[\u0980-\u09FF]/;
export const LATIN_RE = /[A-Za-z]/;

export function detectQueryLanguage(text: string): "" | "bn" | "en" {
  const bangla = (text.match(BANGLA_RE) || []).length;
  const latin = (text.match(LATIN_RE) || []).length;
  if (bangla >= 2 && bangla >= latin) return "bn";
  if (latin >= 2 && latin > bangla) return "en";
  return "";
}
