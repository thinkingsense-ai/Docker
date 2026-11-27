// "Download image": the chart's SVG(s) drawn onto a canvas and saved as a PNG. The SVG styles come from the page's CSS, which a standalone file would lose, so the computed values are copied onto a clone first.
const PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-size', 'font-weight', 'font-family', 'text-anchor']

function inlined(svg: SVGSVGElement): { node: SVGSVGElement; w: number; h: number } {
  const clone = svg.cloneNode(true) as SVGSVGElement
  const from = [svg, ...Array.from(svg.querySelectorAll('*'))], to = [clone, ...Array.from(clone.querySelectorAll('*'))]
  from.forEach((el, i) => { const cs = getComputedStyle(el); to[i].setAttribute('style', PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(';')) })
  const vb = svg.viewBox.baseVal, w = vb && vb.width ? vb.width : svg.clientWidth, h = vb && vb.height ? vb.height : svg.clientHeight
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); clone.setAttribute('width', String(w)); clone.setAttribute('height', String(h))
  return { node: clone, w, h }
}

function load(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => no(new Error('image')); im.src = src })
}

/** Saves every chart drawing inside `root` (one, or one per panel) as a single PNG stacked top to bottom. Returns false when there is nothing to save or the browser cannot draw it. */
export async function downloadImage(root: HTMLElement | null, name: string): Promise<boolean> {
  try {
    const svgs = Array.from(root?.querySelectorAll('svg') ?? []) as SVGSVGElement[]
    if (!svgs.length) return false
    const parts = svgs.map(inlined), scale = 2, width = Math.max(...parts.map((p) => p.w)), height = parts.reduce((s, p) => s + p.h, 0)
    const canvas = document.createElement('canvas'); canvas.width = width * scale; canvas.height = height * scale
    const ctx = canvas.getContext('2d'); if (!ctx) return false
    ctx.fillStyle = getComputedStyle(document.body).backgroundColor || '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    let y = 0
    for (const p of parts) {
      const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(p.node))
      ctx.drawImage(await load(url), 0, y * scale, p.w * scale, p.h * scale); y += p.h
    }
    const blob: Blob | null = await new Promise((ok) => canvas.toBlob(ok, 'image/png')); if (!blob) return false
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${name}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000)
    return true
  } catch { return false }
}
