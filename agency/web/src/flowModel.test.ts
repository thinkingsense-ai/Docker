import { describe, expect, it } from 'vitest'
import { ROUTES, NODES, STEP_FOCUS, advance, centre, clampSpeed, newSim, node, pointAt, routeLength, routePoints, SPEEDS, NODE_W, NODE_H, W, H } from './flowModel'
import { STEPS } from './tourScript'

describe('the data-flow picture', () => {
  it('has unique nodes inside the drawing, and routes that only use known nodes', () => {
    expect(new Set(NODES.map((x) => x.id)).size).toBe(NODES.length)
    for (const x of NODES) { expect(x.x).toBeGreaterThanOrEqual(0); expect(x.x + NODE_W).toBeLessThanOrEqual(W); expect(x.y + NODE_H).toBeLessThanOrEqual(H) }
    for (const r of ROUTES) { expect(r.ids.length).toBeGreaterThan(2); for (const i of r.ids) expect(node(i)).toBeTruthy() }
  })
  it('never routes data through a planned (not built) source', () => {
    for (const r of ROUTES) for (const i of r.ids) expect(node(i).planned).not.toBe(true)
  })
  it('every route starts at a source and passes the access layer before any rule', () => {
    for (const r of ROUTES) { expect(node(r.ids[0]).group).toBe('source'); expect(r.ids.indexOf('access')).toBe(1); expect(r.ids.indexOf('access')).toBeLessThan(r.ids.indexOf('rules')) }
  })
  it('lights up something for every tour step, and only known nodes', () => {
    for (const s of STEPS) expect(STEP_FOCUS[s.id]?.length).toBeGreaterThan(0)
    for (const ids of Object.values(STEP_FOCUS)) for (const i of ids) expect(node(i)).toBeTruthy()
  })
  it('places a ball at the ends and the middle of a route', () => {
    const pts = routePoints(ROUTES[0]); expect(pointAt(pts, 0)).toEqual(centre(ROUTES[0].ids[0])); expect(pointAt(pts, 1)).toEqual(centre(ROUTES[0].ids.at(-1)!))
    const [x, y] = pointAt([[0, 0], [10, 0]], 0.5); expect([x, y]).toEqual([5, 0])
  })
  it('gives every route its own icon', () => {
    expect(new Set(ROUTES.map((r) => r.icon)).size).toBe(ROUTES.length)
  })
  it('clamps the speed to the slider range', () => {
    expect(clampSpeed(0)).toBe(SPEEDS.min); expect(clampSpeed(99)).toBe(SPEEDS.max); expect(clampSpeed(NaN)).toBe(SPEEDS.start); expect(clampSpeed(2)).toBe(2)
  })
  it('moves balls faster at a higher speed, not at all when paused, and retires them at the end', () => {
    const run = (speed: number, paused = false) => { let s = newSim(); for (let i = 0; i < 100; i++) s = advance(s, 16, speed, [], paused); return s }
    const slow = run(0.5), fast = run(2)
    expect(run(1, true).balls.length).toBe(0); expect(fast.clock).toBeGreaterThan(slow.clock * 3)
    let s = newSim(); for (let i = 0; i < 4000; i++) s = advance(s, 16, 4)
    expect(s.balls.every((b) => b.u >= 0 && b.u < 1)).toBe(true); expect(s.balls.length).toBeLessThan(60)
  })
  it('sends balls more often through a focused node', () => {
    const count = (focus: string[]) => { let s = newSim(), n = 0; const seen = new Set<number>(); for (let i = 0; i < 1500; i++) { s = advance(s, 16, 1, focus); for (const b of s.balls) if (b.route === 'incident' && !seen.has(b.id)) { seen.add(b.id); n++ } } return n }
    expect(count(['clocks'])).toBeGreaterThan(count([]) * 2)
  })
  it('ignores a huge frame gap (a hidden tab) instead of jumping', () => {
    const s = advance(newSim(), 60000, 1); expect(s.clock).toBeLessThanOrEqual(100 * 1)
    expect(routeLength(routePoints(ROUTES[0]))).toBeGreaterThan(0)
  })
})
