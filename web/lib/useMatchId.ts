"use client";

import { useSearchParams } from "next/navigation";

/** The match id from ?id=..., for static-export pages without dynamic routes. */
export function useMatchId(): string | null {
  const params = useSearchParams();
  const id = params.get("id");
  return id && /^[a-z0-9-]{3,80}$/.test(id) ? id : null;
}
