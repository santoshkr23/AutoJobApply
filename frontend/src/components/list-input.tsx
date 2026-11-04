"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/form";

export const splitList = (s: string) => s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);

/**
 * Text box for a list. Keeps exactly what the person types (spaces and trailing commas included)
 * and only turns it into a list for the parent; it re-syncs from the parent when the list changes elsewhere.
 */
export function ListInput({ id, value, onChange, parse = splitList, placeholder }: {
  id?: string; value: string[]; onChange: (v: string[]) => void; parse?: (s: string) => string[]; placeholder?: string;
}) {
  const [text, setText] = useState(value.join(", "));
  const last = useRef(value);
  useEffect(() => {
    if (JSON.stringify(value) !== JSON.stringify(last.current)) { last.current = value; setText(value.join(", ")); }
  }, [value]);
  return (
    <Input id={id} value={text} placeholder={placeholder}
      onChange={(e) => { setText(e.target.value); const v = parse(e.target.value); last.current = v; onChange(v); }}
      onBlur={() => setText(last.current.join(", "))} />
  );
}
