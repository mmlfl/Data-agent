/** Heuristic shared with the backend; never presented as an exact tokenizer. */
export function estimateTextTokens(text: string): number {
  let ascii = 0;
  let other = 0;
  for (const char of text) {
    const code = char.codePointAt(0)!;
    if ((code >= 0x4e00 && code <= 0x9fff) ||
        (code >= 0x3400 && code <= 0x4dbf) ||
        (code >= 0xf900 && code <= 0xfaff) ||
        (code >= 0x3000 && code <= 0x303f) ||
        (code >= 0xff00 && code <= 0xffef)) other += 1;
    else if (code > 127) other += code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    else ascii += 1;
  }
  return other + Math.ceil(ascii / 4);
}
