import { expect, it } from "vitest";
import { buildCsv } from "./exportCsv";
it("keeps spreadsheet formulas inert and precise text unchanged apart from the protective prefix", () => {
  const value = buildCsv(["id", "value", "note"], [{ id: "1234567890123456789", value: "=HYPERLINK(1)", note: 'a,"b"\nline' }]);
  expect(value).toContain("'1234567890123456789");
  expect(value).toContain("'=HYPERLINK(1)");
  expect(value).toContain('"a,""b""\nline"');
});
