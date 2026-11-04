import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ListInput } from "@/components/list-input";
import { parseCountries } from "@/lib/countries";

function Harness() {
  const [v, setV] = useState<string[]>([]);
  return (<><ListInput id="x" value={v} onChange={setV} /><output data-testid="out">{JSON.stringify(v)}</output></>);
}

describe("ListInput", () => {
  it("keeps spaces and commas while typing", async () => {
    render(<Harness />);
    const box = screen.getByRole("textbox") as HTMLInputElement;
    await userEvent.type(box, "Data Engineer, Azure ");
    expect(box.value).toBe("Data Engineer, Azure ");
    expect(screen.getByTestId("out").textContent).toBe('["Data Engineer","Azure"]');
  });
});

describe("parseCountries", () => {
  it("accepts names and codes, flags unknown", () => {
    expect(parseCountries("Japan, in, united states")).toEqual({ codes: ["JP", "IN", "US"], unknown: [] });
    expect(parseCountries("Atlantis").unknown).toEqual(["Atlantis"]);
  });
});
