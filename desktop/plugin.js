// Lethe: a top-bar button that takes the open chat off the record, a status-bar pill, and a
// "Where it went" panel showing every write that sank into the river instead of reaching memory.
// Plain ESM, loaded uncompiled by Hermes Desktop (no JSX, no build step).
import { host, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PANE_ID = 'lethe:panel'
const POLL_MS = 2500
const TEAL = 'var(--lethe-teal, #2fb5a6)'

const C = {
  text: 'var(--ui-text-primary)',
  soft: 'var(--ui-text-secondary)',
  muted: 'var(--ui-text-tertiary)',
  stroke: 'var(--ui-stroke-tertiary)',
  tile: 'var(--ui-bg-tertiary)',
  yellow: 'var(--ui-yellow)'
}

const log = (...args) => console.warn('[lethe]', ...args)
let diagCtx = null
const diag = (event, detail) => {
  log(event, detail || '')
  if (diagCtx) diagCtx.rest('/diag', { method: 'POST', body: { event, detail: detail || null } }).catch(() => {})
}

// ---- shared per-session state, polled once for every component that shows it ------------------

const watchers = new Map() // sid -> { data, subs:Set, timer }

function fetchFlow(ctx, sid) {
  return ctx.rest(`/flow?session_id=${encodeURIComponent(sid)}`).then(res => {
    const w = watchers.get(sid)
    if (!w) return res
    if (res && res.ok) w.data = res
    w.subs.forEach(fn => fn(w.data))
    return res
  }).catch(err => diag('flow failed', String(err)))
}

function publish(sid, data) {
  const w = watchers.get(sid)
  if (!w || !data || !data.ok) return
  w.data = data
  w.subs.forEach(fn => fn(data))
}

function useFlow(ctx, sid) {
  const [data, setData] = useState(() => (sid && watchers.get(sid) ? watchers.get(sid).data : null))
  useEffect(() => {
    if (!sid) { setData(null); return undefined }
    let w = watchers.get(sid)
    if (!w) {
      w = { data: null, subs: new Set(), timer: null }
      watchers.set(sid, w)
    }
    w.subs.add(setData)
    setData(w.data)
    if (!w.timer) {
      fetchFlow(ctx, sid)
      w.timer = setInterval(() => fetchFlow(ctx, sid), POLL_MS)
    }
    return () => {
      w.subs.delete(setData)
      if (!w.subs.size) { clearInterval(w.timer); watchers.delete(sid) }
    }
  }, [sid])
  return data
}

function toggle(ctx, sid, on) {
  return ctx.rest('/toggle', { method: 'POST', body: { session_id: sid, on } }).then(res => {
    if (!res || !res.ok) throw new Error((res && res.error) || 'Lethe could not change this chat.')
    publish(sid, res)
    return res
  })
}

// ---- small pieces -------------------------------------------------------------------------------

// Lethe's mark: a closed eye above the river. Same stroke weight as the other top-bar icons.
function LetheIcon({ size = 17 }) {
  return jsxs('svg', {
    viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', strokeWidth: 1.65,
    strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
    children: [
      jsx('path', { d: 'M4 6.5c2.4 2.8 5 4 8 4s5.6-1.2 8-4' }),
      jsx('path', { d: 'M8 9.6l-.9 1.6M12 10.5v1.8M16 9.6l.9 1.6' }),
      jsx('path', { d: 'M3 16c1.5-1.2 3-1.2 4.5 0s3 1.2 4.5 0 3-1.2 4.5 0 3 1.2 4.5 0' }),
      jsx('path', { d: 'M3 19.6c1.5-1.2 3-1.2 4.5 0s3 1.2 4.5 0 3-1.2 4.5 0 3 1.2 4.5 0' })
    ]
  })
}

const small = (text, color = C.muted, extra = {}) =>
  jsx('div', { style: { fontSize: '0.75rem', color, lineHeight: 1.5, ...extra }, children: text })

const TEAL_SOFT = 'color-mix(in srgb, #2fb5a6 12%, transparent)'
const TEAL_LINE = 'color-mix(in srgb, #2fb5a6 45%, transparent)'

function Header({ on, badge }) {
  return jsxs('div', {
    style: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 },
    children: [
      jsx('span', {
        style: {
          width: 30, height: 30, borderRadius: 9, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: on ? TEAL_SOFT : C.tile, color: on ? TEAL : C.muted, flex: 'none'
        },
        children: jsx(LetheIcon, { size: 18 })
      }),
      jsxs('div', {
        style: { flex: 1, minWidth: 0 },
        children: [
          jsx('div', { style: { fontWeight: 650, fontSize: '0.9375rem', color: C.text, letterSpacing: '-0.01em' }, children: 'Where it went' }),
          jsx('div', { style: { fontSize: '0.6875rem', color: C.muted }, children: 'Lethe \u00b7 off-the-record chats' })
        ]
      }),
      jsxs('span', {
        style: {
          display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '0.6875rem', fontWeight: 600, padding: '3px 9px', borderRadius: 99,
          background: on ? TEAL_SOFT : C.tile, color: on ? TEAL : C.muted, border: `1px solid ${on ? TEAL_LINE : 'transparent'}`, whiteSpace: 'nowrap'
        },
        children: [jsx('span', { style: { width: 6, height: 6, borderRadius: 3, background: on ? TEAL : C.muted } }), badge]
      })
    ]
  })
}

function Card({ children, style }) {
  return jsx('div', {
    style: { background: 'color-mix(in srgb, #2fb5a6 6%, var(--ui-bg-elevated, #fff))', border: `1px solid ${C.stroke}`, borderRadius: 14, padding: 12, ...(style || {}) },
    children
  })
}

function Button({ onClick, children, primary, danger, title, disabled, wide }) {
  return jsx('button', {
    type: 'button', onClick, title, disabled,
    style: {
      padding: '8px 12px', borderRadius: 10, cursor: disabled ? 'default' : 'pointer', fontSize: '0.8125rem', fontWeight: 550,
      border: `1px solid ${primary ? 'transparent' : C.stroke}`,
      background: primary ? TEAL : 'transparent',
      boxShadow: primary ? '0 1px 2px rgba(0,0,0,.12), 0 4px 14px rgba(47,181,166,.28)' : 'none',
      color: primary ? '#fff' : danger ? 'var(--ui-red, #e5484d)' : C.text,
      opacity: disabled ? 0.5 : 1, flex: wide ? '1 1 100%' : '0 0 auto', transition: 'transform .12s ease, opacity .12s ease'
    },
    children
  })
}

const STYLE = `
:root { --lethe-teal: #2fb5a6; }
@keyframes lethe-wave { from { transform: translateX(0) } to { transform: translateX(-80px) } }
@keyframes lethe-drop {
  0%   { transform: translate(0px, 0px) scale(1); opacity: 0 }
  12%  { opacity: 1 }
  62%  { transform: translate(var(--dx), var(--dy)) scale(1); opacity: 1 }
  100% { transform: translate(var(--dx), calc(var(--dy) + 16px)) scale(0.35); opacity: 0 }
}
@keyframes lethe-ripple {
  0%   { transform: scale(0.2); opacity: 0 }
  10%  { opacity: 0.9 }
  100% { transform: scale(2.4); opacity: 0 }
}
@keyframes lethe-glow { 0%,100% { opacity: .55 } 50% { opacity: 1 } }
.lethe-wave { animation: lethe-wave 6s linear infinite }
.lethe-wave.slow { animation-duration: 10s }
.lethe-card { transform-box: view-box; animation: lethe-drop 1.8s cubic-bezier(.45,.05,.4,1) both }
.lethe-ripple { transform-box: fill-box; transform-origin: center; animation: lethe-ripple 1.4s ease-out both }
.lethe-glow { animation: lethe-glow 2.4s ease-in-out infinite }
@media (prefers-reduced-motion: reduce) {
  .lethe-wave, .lethe-glow { animation: none }
  .lethe-card, .lethe-ripple { animation: none; opacity: 0 }
}`

function StyleTag() {
  return jsx('style', { children: STYLE })
}

// ---- the river ----------------------------------------------------------------------------------

const W = 268
const LANE_X = [W * 0.125, W * 0.375, W * 0.625, W * 0.875]
const LANE_INDEX = { memory: 0, user: 1, skills: 2, provider: 3 }
const SHORT = { memory: 'Memory', user: 'Profile', skills: 'Skills', provider: 'Provider' }
const RIVER_Y = 132
const BUBBLE_Y = 34

function laneOf(destination) {
  const d = String(destination || '')
  if (d === 'USER.md') return 'user'
  if (d.startsWith('skills/')) return 'skills'
  if (d.startsWith('provider:')) return 'provider'
  return 'memory'
}

function wavePath(y, amp) {
  let d = `M -80 ${y}`
  for (let x = -80; x <= W + 160; x += 40) d += ` q 20 ${-amp} 40 0`
  return d + ` V ${y + 40} H -80 Z`
}

function River({ flow, drops }) {
  const on = flow && flow.on
  const lanes = (flow && flow.lanes) || []
  const count = key => (lanes.find(l => l.key === key) || {}).kept_out || 0
  const children = []

  // The chat
  children.push(jsxs('g', {
    key: 'bubble',
    children: [
      jsx('rect', { x: W / 2 - 50, y: BUBBLE_Y - 19, width: 100, height: 32, rx: 16, fill: 'var(--ui-bg-elevated, #fff)', stroke: on ? TEAL : C.stroke, strokeWidth: 1.2, filter: 'url(#lethe-shadow)' }),
      jsx('text', { x: W / 2, y: BUBBLE_Y + 1.5, textAnchor: 'middle', fontSize: 11.5, fontWeight: 600, fill: C.text, children: 'This chat' }),
      jsx('path', { d: `M ${W / 2 - 6} ${BUBBLE_Y + 13} l 6 7 l 6 -7`, fill: 'var(--ui-bg-elevated, #fff)', stroke: on ? TEAL : C.stroke, strokeWidth: 1.2 })
    ]
  }))

  // Faint paths from the chat to each store (where things *would* have gone)
  LANE_X.forEach((x, i) => children.push(jsx('path', {
    key: `path-${i}`,
    d: `M ${W / 2} ${BUBBLE_Y + 20} C ${W / 2} ${BUBBLE_Y + 60}, ${x} ${RIVER_Y - 50}, ${x} ${RIVER_Y + 70}`,
    fill: 'none', stroke: on ? TEAL : C.stroke, strokeOpacity: on ? 0.45 : 1, strokeDasharray: '2 5', strokeWidth: 1.2, strokeLinecap: 'round'
  })))

  // The river Lethe, between the chat and memory
  children.push(jsxs('g', {
    key: 'river',
    children: [
      jsxs('defs', { children: [
        jsx('clipPath', { id: 'lethe-clip', children: jsx('rect', { x: 0, y: RIVER_Y - 16, width: W, height: 44, rx: 12 }) }),
        jsxs('linearGradient', { id: 'lethe-water', x1: 0, y1: 0, x2: 0, y2: 1, children: [
          jsx('stop', { offset: '0%', stopColor: '#5fd4c6', stopOpacity: on ? 0.55 : 0.3 }),
          jsx('stop', { offset: '100%', stopColor: '#1f8f84', stopOpacity: on ? 0.85 : 0.42 })
        ] }),
        jsx('filter', { id: 'lethe-shadow', x: '-20%', y: '-40%', width: '140%', height: '180%', children: jsx('feDropShadow', { dx: 0, dy: 2, stdDeviation: 2.5, floodColor: '#0b2e2a', floodOpacity: 0.18 }) })
      ] }),
      jsxs('g', {
        clipPath: 'url(#lethe-clip)',
        children: [
          jsx('rect', { x: 0, y: RIVER_Y - 16, width: W, height: 44, fill: 'url(#lethe-water)' }),
          jsx('path', { className: 'lethe-wave slow', d: wavePath(RIVER_Y - 5, 5), fill: '#ffffff', opacity: on ? 0.22 : 0.18 }),
          jsx('path', { className: 'lethe-wave', d: wavePath(RIVER_Y + 4, 4), fill: '#ffffff', opacity: on ? 0.16 : 0.12 })
        ]
      }),
      jsx('text', {
        x: W - 10, y: RIVER_Y + 22, textAnchor: 'end', fontSize: 9, fontWeight: 700, letterSpacing: 3, fill: '#ffffff',
        opacity: on ? 0.95 : 0.6, className: on ? 'lethe-glow' : undefined, children: 'LETHE'
      })
    ]
  }))

  // The stores, below the river, untouched
  Object.keys(LANE_INDEX).forEach(key => {
    const x = LANE_X[LANE_INDEX[key]]
    const n = count(key)
    children.push(jsxs('g', {
      key: `lane-${key}`,
      children: [
        jsx('rect', {
          x: x - 31, y: RIVER_Y + 42, width: 62, height: 56, rx: 11,
          fill: n ? TEAL_SOFT : 'var(--ui-bg-elevated, #fff)', stroke: n ? TEAL : C.stroke, strokeWidth: n ? 1.4 : 1
        }),
        jsx('text', { x, y: RIVER_Y + 57, textAnchor: 'middle', fontSize: 9, fontWeight: 600, fill: C.soft, children: SHORT[key] }),
        jsx('text', { x, y: RIVER_Y + 77, textAnchor: 'middle', fontSize: 17, fontWeight: 700, fill: n ? TEAL : C.muted, children: n ? String(n) : '0' }),
        jsx('text', { x, y: RIVER_Y + 91, textAnchor: 'middle', fontSize: 7.5, fill: n ? TEAL : C.muted, children: n ? 'kept out' : 'written' })
      ]
    }))
  })

  // Each write, travelling from the chat and sinking into the river
  drops.forEach((d, i) => {
    const x = LANE_X[LANE_INDEX[laneOf(d.destination)]]
    const dx = x - W / 2
    const dy = RIVER_Y - BUBBLE_Y - 8
    const delay = `${d.delay || 0}ms`
    children.push(jsxs('g', {
      key: `drop-${d.key}`,
      children: [
        jsx('g', {
          className: 'lethe-card',
          style: { '--dx': `${dx}px`, '--dy': `${dy}px`, animationDelay: delay },
          children: [
            jsx('rect', { x: W / 2 - 25, y: BUBBLE_Y + 1, width: 50, height: 16, rx: 8, fill: TEAL, filter: 'url(#lethe-shadow)' }),
            jsx('text', { x: W / 2, y: BUBBLE_Y + 12, textAnchor: 'middle', fontSize: 8, fontWeight: 600, fill: '#ffffff', children: SHORT[laneOf(d.destination)].toLowerCase() })
          ]
        }),
        jsx('circle', {
          className: 'lethe-ripple', cx: x, cy: RIVER_Y + 4, r: 8, fill: 'none', stroke: TEAL, strokeWidth: 1.2,
          style: { animationDelay: `${(d.delay || 0) + 1100}ms` }
        })
      ]
    }))
  })

  return jsx('svg', {
    viewBox: `0 0 ${W} ${RIVER_Y + 102}`, width: '100%', role: 'img',
    'aria-label': on ? 'Writes from this chat sink into the river Lethe instead of reaching memory.' : 'Lethe is off for this chat.',
    style: { display: 'block', overflow: 'visible' },
    children
  })
}

// ---- the panel ----------------------------------------------------------------------------------

// A brand-new chat has no id yet, and Desktop can't run a command in it until it exists. So the
// panel arms Lethe instead: the backend's on_session_start hook turns the next Desktop chat off
// the record before its first message reaches the model.
function NewChat({ ctx }) {
  const [armed, setArmed] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    const load = () => ctx.rest('/armed').then(r => { if (live && r && r.ok) setArmed(r) }).catch(() => {})
    load()
    const t = setInterval(load, POLL_MS)
    return () => { live = false; clearInterval(t) }
  }, [])
  const set = on => {
    setBusy(true)
    ctx.rest('/arm', { method: 'POST', body: { on } })
      .then(r => {
        if (r && r.ok) setArmed(r)
        if (on) { try { host.composer.focus(null) } catch {} }
      })
      .catch(err => host.notify({ kind: 'error', message: String(err.message || err) }))
      .finally(() => setBusy(false))
  }
  const on = Boolean(armed && armed.armed)
  return jsxs('div', {
    style: { padding: 16 },
    children: [
      jsx(StyleTag, {}),
      jsx(Header, { on, badge: on ? 'Next chat' : 'New chat' }),
      on
        ? small('Your next message starts this chat off the record. Nothing from it reaches Hermes\u2019s memory, your profile or its skills, starting with that first message.', C.soft)
        : small('Start this chat off the record. Nothing from it, not even the first message, reaches Hermes\u2019s memory, your profile or its skills, and the transcript is deleted when it ends.', C.soft),
      jsx(Card, { style: { margin: '14px 0 12px' }, children: jsx(River, { flow: { on, lanes: [] }, drops: [] }) }),
      jsx('div', {
        style: { display: 'flex', gap: 8, flexWrap: 'wrap' },
        children: on
          ? jsx(Button, { wide: true, onClick: () => set(false), disabled: busy, children: 'Cancel' })
          : jsx(Button, { wide: true, primary: true, onClick: () => set(true), disabled: busy, children: 'Start off the record' })
      }),
      on ? small(`Applies to the next new Desktop chat within ${(armed && armed.minutes) || 5} minutes.`, C.muted, { marginTop: 8, textAlign: 'center' }) : null
    ]
  })
}

function timeOf(t) {
  if (!t) return ''
  const d = new Date(t * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function Panel({ ctx }) {
  const sid = useValue(host.state.focusedStoredSessionId)
  const flow = useFlow(ctx, sid)
  const seen = useRef({ sid: null, keys: new Set() })
  const [drops, setDrops] = useState([])
  const [busy, setBusy] = useState(false)
  const [armForget, setArmForget] = useState(false)
  const [note, setNote] = useState('')

  // Each chat has its own river: clear the previous chat's cards, note and armed button.
  useEffect(() => {
    seen.current = { sid, keys: new Set(), first: true }
    setDrops([])
    setNote('')
    setArmForget(false)
  }, [sid])

  // Animate writes we haven't shown yet. On first look at a chat, replay the latest few.
  useEffect(() => {
    if (!flow || !flow.events || flow.session_id !== sid) return
    if (seen.current.sid !== sid) seen.current = { sid, keys: new Set(), first: true }
    const fresh = flow.events.filter(e => !seen.current.keys.has(`${e.t}-${e.tool}`))
    fresh.forEach(e => seen.current.keys.add(`${e.t}-${e.tool}`))
    const show = seen.current.first ? fresh.slice(-6) : fresh
    seen.current.first = false
    if (!show.length) return
    const now = Date.now()
    setDrops(prev => [...prev.filter(d => now - d.born < 4000),
      ...show.map((e, i) => ({ key: `${e.t}-${e.tool}-${now}`, destination: e.destination, delay: i * 450, born: now }))])
  }, [flow, sid])

  const replay = () => {
    if (!flow || !flow.events) return
    const now = Date.now()
    setDrops(flow.events.slice(-8).map((e, i) => ({ key: `${e.t}-${e.tool}-r${now}`, destination: e.destination, delay: i * 450, born: now })))
  }

  if (!sid) return jsx(NewChat, { ctx })

  const on = Boolean(flow && flow.on)
  const doToggle = () => {
    setBusy(true); setNote('')
    toggle(ctx, sid, !on)
      .then(res => setNote(res.on ? 'Off the record. Nothing from this chat will reach memory.' : 'Back on the record from here on. The transcript will be kept.'))
      .catch(err => setNote(String(err.message || err)))
      .finally(() => setBusy(false))
  }
  const doForget = () => {
    if (!armForget) { setArmForget(true); ctx.setTimeout(() => setArmForget(false), 4000); return }
    setArmForget(false); setBusy(true)
    ctx.rest('/forget', { method: 'POST', body: { session_id: sid } })
      .then(res => { publish(sid, res); setNote((res && res.message) || '') })
      .catch(err => setNote(String(err)))
      .finally(() => setBusy(false))
  }

  const events = (flow && flow.events) || []
  const header = jsx(Header, { on, badge: on ? 'Off the record' : 'On the record' })

  const intro = on
    ? small(`Hermes can still use what it already knows. Anything it tries to save from this chat sinks here instead.`, C.soft)
    : small('Take this chat off the record and nothing from it reaches Hermes’s memory, your profile or its skills. The transcript is deleted when the chat ends.', C.soft)

  const actions = jsxs('div', {
    style: { display: 'flex', gap: 8, flexWrap: 'wrap' },
    children: [
      jsx(Button, { wide: true, primary: !on, onClick: doToggle, disabled: busy, children: on ? 'Go back on the record' : 'Take off the record' }),
      events.length ? jsx(Button, { onClick: replay, title: 'Play the animation again', children: 'Replay' }) : null,
      jsx(Button, {
        danger: true, onClick: doForget, disabled: busy,
        title: 'Delete this chat’s transcript from your session history now',
        children: armForget ? 'Click again to delete' : 'Delete transcript now'
      })
    ]
  })

  const list = events.length
    ? jsxs('div', {
      style: { marginTop: 16, display: 'flex', flexDirection: 'column', gap: 6 },
      children: [
        jsxs('div', { style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 2 }, children: [
          jsx('span', { style: { fontSize: '0.75rem', fontWeight: 650, color: C.text }, children: `${events.length} write${events.length === 1 ? '' : 's'} kept out` }),
          jsx('span', { style: { fontSize: '0.6875rem', color: TEAL, fontWeight: 600 }, children: 'nothing saved' })
        ] }),
        ...events.slice().reverse().map((e, i) => jsxs('div', {
          key: `${e.t}-${i}`,
          style: { display: 'flex', gap: 10, alignItems: 'center', padding: '8px 10px', borderRadius: 10, background: 'var(--ui-bg-elevated, #fff)', border: `1px solid ${C.stroke}` },
          children: [
            jsx('span', { style: { width: 8, height: 8, borderRadius: 4, background: TEAL, boxShadow: '0 0 0 3px ' + TEAL_SOFT, flex: 'none' } }),
            jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
              jsx('div', { style: { fontSize: '0.75rem', fontWeight: 600, color: C.text }, children: e.summary || e.tool }),
              jsx('div', { style: { fontSize: '0.6875rem', color: C.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: `${timeOf(e.t)} \u00b7 ${e.destination}` })
            ] }),
            jsx('span', { style: { fontSize: '0.6875rem', fontWeight: 600, color: TEAL, padding: '2px 8px', borderRadius: 99, background: TEAL_SOFT, whiteSpace: 'nowrap' }, children: 'Not saved' })
          ]
        }))
      ]
    })
    : on ? small('Nothing has tried to reach memory yet. When it does, you’ll see it sink here.', C.muted, { marginTop: 8 }) : null

  const transcript = flow
    ? small(flow.shredded ? '✕ Transcript deleted from your session history.' : on ? 'Transcript: deleted when this chat ends.' : '', C.soft, { marginTop: 8 })
    : null

  const gaps = flow && flow.gaps && flow.gaps.length
    ? jsx('div', { style: { marginTop: 10, display: 'flex', flexDirection: 'column', gap: 3 }, children: flow.gaps.map((g, i) => small(`⚠ ${g}`, C.yellow, { key: i })) })
    : null

  return jsxs('div', {
    style: { padding: 16, overflowY: 'auto', height: '100%', boxSizing: 'border-box' },
    children: [
      jsx(StyleTag, {}), header, intro,
      jsx(Card, { style: { margin: '14px 0 12px' }, children: jsx(River, { flow, drops }) }),
      actions, note ? small(note, C.soft, { marginTop: 8 }) : null, transcript, list, gaps
    ]
  })
}

// ---- top-bar button and status pill -------------------------------------------------------------

function TopButton({ ctx, openPanel }) {
  const sid = useValue(host.state.focusedStoredSessionId)
  const flow = useFlow(ctx, sid)
  const on = Boolean(flow && flow.on)
  const label = on ? `Lethe: this chat is off the record (${(flow && flow.total) || 0} kept out). Show where it went.`
    : 'Lethe: show or hide the off-the-record panel.'
  return jsxs('button', {
    type: 'button', title: label, 'aria-label': label,
    onPointerDown: e => e.stopPropagation(),
    onClick: () => openPanel(),
    style: {
      WebkitAppRegion: 'no-drag', appRegion: 'no-drag', pointerEvents: 'auto', position: 'relative', zIndex: 5,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 6,
      padding: 0, border: 0, background: 'none', cursor: 'pointer', color: on ? TEAL : C.muted
    },
    children: [
      jsx(LetheIcon, {}),
      on ? jsx('span', {
        'aria-hidden': true,
        style: { position: 'absolute', top: 4, right: 4, width: 6, height: 6, borderRadius: 3, background: TEAL, boxShadow: '0 0 6px #2fb5a6' }
      }) : null
    ]
  })
}

// Only shown while the open chat is off the record, so it's a quiet reminder rather than clutter.
function StatusPill({ ctx, openPanel }) {
  const sid = useValue(host.state.focusedStoredSessionId)
  const flow = useFlow(ctx, sid)
  if (!flow || !flow.on) return null
  return jsxs('button', {
    type: 'button', title: 'Lethe: where it went', onClick: () => openPanel(),
    style: {
      WebkitAppRegion: 'no-drag', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 6px', height: '100%',
      background: 'none', border: 'none', cursor: 'pointer', color: TEAL, fontSize: '0.6875rem'
    },
    children: [jsx(LetheIcon, { size: 12 }), `Off the record · ${flow.total || 0}`]
  })
}

// ---- registration -------------------------------------------------------------------------------

export default {
  id: 'lethe',
  name: 'Lethe',
  register(ctx) {
    diagCtx = ctx
    const PANE = {
      id: 'panel', area: 'panes', title: 'Lethe',
      data: { placement: 'right', dock: { pane: 'workspace', pos: 'right' }, width: '340px' },
      render: () => jsx(Panel, { ctx })
    }
    let disposePane = null
    const isVisible = () => {
      if (!disposePane) return false
      if (typeof host.paneVisibility !== 'function') return true
      try { return Boolean(host.paneVisibility(PANE_ID).get()) } catch { return true }
    }
    const reveal = () => {
      if (typeof host.undismissPane === 'function') host.undismissPane(PANE_ID)
      if (typeof host.revealPane === 'function') host.revealPane(PANE_ID)
    }
    const show = () => {
      if (!disposePane) disposePane = ctx.register(PANE)
      reveal()
      ctx.setTimeout(reveal, 60)
    }
    const hide = () => { if (disposePane) disposePane(); disposePane = null }
    const openPanel = (forceOpen = false) => {
      try { (forceOpen || !isVisible()) ? show() : hide() } catch (err) {
        diag('panel failed', String(err))
        host.notify({ kind: 'error', message: `Lethe couldn't open: ${String(err)}` })
      }
    }

    // Top-bar button, only on chat routes (plugin pages own the title bar otherwise).
    const isChatRoute = () => {
      const path = (window.location.hash || '#/').slice(1).split(/[?#]/)[0] || '/'
      if (path === '/') return true
      const seg = decodeURIComponent(path.slice(1))
      return !seg.includes('/') && seg.length >= 16 && /\d/.test(seg) && /^[\w.:-]+$/.test(seg)
    }
    let disposeTop = null
    const syncTop = () => {
      const want = isChatRoute()
      if (want && !disposeTop) {
        disposeTop = ctx.register({ id: 'top-button', area: 'titleBar.right', order: 4, render: () => jsx(TopButton, { ctx, openPanel }) })
      } else if (!want && disposeTop) {
        disposeTop(); disposeTop = null
      }
    }
    syncTop()
    ctx.addEventListener(window, 'hashchange', syncTop)
    ctx.setInterval(syncTop, 1000)

    ctx.register({ id: 'status', area: 'statusBar.right', order: 91, render: () => jsx(StatusPill, { ctx, openPanel }) })

    const current = () => {
      try { return host.state.focusedStoredSessionId.get() } catch { return null }
    }
    ctx.register({
      id: 'toggle-command', area: 'palette',
      data: {
        id: 'lethe.toggle', label: 'Lethe: Take this chat off the record (or back on)',
        keywords: ['lethe', 'incognito', 'private', 'off the record', 'memory'],
        run: () => {
          const sid = current()
          if (!sid) return host.notify({ kind: 'info', message: 'Open a chat first.' })
          ctx.rest(`/flow?session_id=${encodeURIComponent(sid)}`)
            .then(f => toggle(ctx, sid, !(f && f.on)))
            .then(res => {
          host.notify({ kind: res.on ? 'success' : 'info', title: res.on ? 'Off the record' : 'Back on the record',
            message: res.on ? 'Nothing from this chat will reach Hermes\u2019s memory.' : 'This chat is saved normally from here on.' })
          if (res.on) openPanel(true)
        })
            .catch(err => host.notify({ kind: 'error', message: String(err.message || err) }))
        }
      }
    })
    ctx.register({
      id: 'open-command', area: 'palette',
      data: { id: 'lethe.open', label: 'Lethe: Show where it went', keywords: ['lethe', 'memory', 'river'], run: () => openPanel() }
    })
    diag('registered')
  }
}
