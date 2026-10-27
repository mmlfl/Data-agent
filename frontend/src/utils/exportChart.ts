import { downloadBlob } from "./exportCsv";

export async function exportChart(container: HTMLElement, format: "svg" | "png", filename: string) {
  const svg = container.querySelector("svg.recharts-surface");
  if (!(svg instanceof SVGSVGElement)) throw new Error("图表尚未生成，请稍后重试。");
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const originals = [svg, ...svg.querySelectorAll("*")];
  const clones = [copy, ...copy.querySelectorAll("*")];
  originals.forEach((node, index) => {
    const style = getComputedStyle(node);
    for (const key of ["fill", "stroke", "font-family", "font-size", "font-weight", "opacity"]) {
      (clones[index] as SVGElement).style.setProperty(key, style.getPropertyValue(key));
    }
  });
  const { width, height } = svg.getBoundingClientRect();
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.setAttribute("width", String(width)); copy.setAttribute("height", String(height));
  const outer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  outer.setAttribute("width", String(width)); outer.setAttribute("height", String(height + 80));
  outer.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const background = document.createElementNS(outer.namespaceURI, "rect");
  const color = getComputedStyle(document.documentElement).getPropertyValue("--color-panel").trim() || "white";
  background.setAttribute("width", "100%"); background.setAttribute("height", "100%"); background.setAttribute("fill", color); outer.append(background);
  const text = (value: string, y: number) => {
    const label = document.createElementNS(outer.namespaceURI, "text");
    label.setAttribute("x", "12"); label.setAttribute("y", String(y)); label.setAttribute("font-size", "12");
    label.setAttribute("fill", getComputedStyle(container).color); label.textContent = value; outer.append(label);
  };
  text(container.getAttribute("aria-label") ?? "查询结果图表", 22);
  copy.setAttribute("y", "32"); outer.append(copy);
  text(container.dataset.exportNote ?? "基于已加载查询结果", height + 65);
  const blob = new Blob([new XMLSerializer().serializeToString(outer)], { type: "image/svg+xml;charset=utf-8" });
  if (format === "svg") { downloadBlob(blob, `${filename}.svg`); return; }
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image(); image.src = url; await image.decode();
    const canvas = document.createElement("canvas"); canvas.width = width * 2; canvas.height = (height + 80) * 2;
    const context = canvas.getContext("2d"); if (!context) throw new Error("当前浏览器无法导出图片。");
    context.scale(2, 2); context.drawImage(image, 0, 0, width, height + 80);
    const png = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error("图片导出失败")), "image/png"));
    downloadBlob(png, `${filename}.png`);
  } finally { URL.revokeObjectURL(url); }
}
