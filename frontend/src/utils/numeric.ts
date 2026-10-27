/** Compare decimal text without converting precise values to IEEE-754 numbers. */
export function compareNumericText(left: unknown, right: unknown): number {
  const parse = (value: unknown) => {
    const match = String(value ?? "").match(/^([+-]?)(\d+)(?:\.(\d*))?$/);
    return match ? { sign: match[1] === "-" ? -1 : 1, whole: match[2].replace(/^0+(?=\d)/, ""), fraction: (match[3] ?? "").replace(/0+$/, "") } : null;
  };
  const a = parse(left), b = parse(right);
  if (!a || !b) return String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true });
  if (a.whole === "0" && !a.fraction) a.sign = 1;
  if (b.whole === "0" && !b.fraction) b.sign = 1;
  if (a.sign !== b.sign) return a.sign - b.sign;
  const digits = Math.max(a.fraction.length, b.fraction.length);
  return a.sign * (a.whole.length - b.whole.length || a.whole.localeCompare(b.whole) || a.fraction.padEnd(digits, "0").localeCompare(b.fraction.padEnd(digits, "0")));
}
