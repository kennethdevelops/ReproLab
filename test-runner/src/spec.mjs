// Restricted regression-test specification (spec §10.1). Anything outside this allowlist is
// rejected before code generation. The spec is data: no field is ever evaluated as code.

// wait_for_text is a setup checkpoint: it waits for state the app must reach before continuing.
export const ACTIONS = new Set(['goto', 'click', 'fill', 'press', 'select_option', 'reload', 'go_back', 'wait_for_text'])
export const LOCATOR_KINDS = new Set(['role', 'label', 'text', 'test_id', 'placeholder'])
export const ASSERTIONS = new Set(['text_visible', 'text_absent', 'url_contains'])
export const KEYS = new Set([
  'Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft',
  'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown', 'Space',
])
const ROLES = new Set([
  'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox', 'listbox', 'option', 'heading',
  'region', 'complementary', 'main', 'navigation', 'list', 'listitem', 'row', 'cell', 'table',
  'tab', 'tabpanel', 'dialog', 'alert', 'status', 'searchbox', 'spinbutton', 'img', 'form',
  'article', 'menu', 'menuitem', 'group', 'banner', 'contentinfo',
])
const MAX = { title: 200, text: 500, steps: 40, assertions: 10 }
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/

function isStr(v, max, min = 1) {
  return typeof v === 'string' && v.length >= min && v.length <= max && !CONTROL.test(v)
}

function only(obj, keys, where, errors) {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    errors.push(`${where}: must be an object`)
    return false
  }
  for (const k of Object.keys(obj)) if (!keys.includes(k)) errors.push(`${where}: unknown field ${k}`)
  return true
}

function checkPath(p, where, errors) {
  if (!isStr(p, MAX.text) || !p.startsWith('/') || p.startsWith('//') || /[\\\s]/.test(p)) {
    errors.push(`${where}: must be a same-origin path starting with a single /`)
  }
}

function checkLocator(loc, where, errors) {
  if (!only(loc, ['kind', 'value', 'name', 'exact'], where, errors)) return
  if (!LOCATOR_KINDS.has(loc.kind)) errors.push(`${where}.kind: not allowed (${loc.kind})`)
  if (!isStr(loc.value, MAX.text)) errors.push(`${where}.value: required string`)
  if (loc.kind === 'role' && !ROLES.has(loc.value)) errors.push(`${where}.value: unknown role`)
  if (loc.name != null && !isStr(loc.name, MAX.text)) errors.push(`${where}.name: invalid`)
  if (loc.name != null && loc.kind !== 'role') errors.push(`${where}.name: only for kind=role`)
  if (loc.exact != null && typeof loc.exact !== 'boolean') errors.push(`${where}.exact: boolean`)
}

const NEEDS = {
  goto: ['path'],
  click: ['locator'],
  fill: ['locator', 'value'],
  press: ['locator', 'key'],
  select_option: ['locator', 'value'],
  reload: [],
  go_back: [],
  wait_for_text: ['value'],
}

/** Returns a list of errors; empty means the spec is accepted. */
export function validateSpec(spec) {
  const errors = []
  if (!only(spec, ['version', 'title', 'start_path', 'steps', 'assertions'], 'spec', errors)) return errors
  if (spec.version !== 1) errors.push('version: must be 1')
  if (!isStr(spec.title, MAX.title)) errors.push('title: required string')
  checkPath(spec.start_path, 'start_path', errors)
  const steps = Array.isArray(spec.steps) ? spec.steps : []
  const assertions = Array.isArray(spec.assertions) ? spec.assertions : []
  if (!Array.isArray(spec.steps) || steps.length > MAX.steps) errors.push(`steps: array of at most ${MAX.steps}`)
  if (!Array.isArray(spec.assertions) || assertions.length < 1 || assertions.length > MAX.assertions) {
    errors.push(`assertions: array of 1-${MAX.assertions}`)
  }
  for (const [i, s] of steps.entries()) {
    const w = `steps[${i}]`
    if (!only(s, ['action', 'path', 'locator', 'value', 'key'], w, errors)) continue
    if (!ACTIONS.has(s.action)) {
      errors.push(`${w}.action: not allowed (${s.action})`)
      continue
    }
    const needs = NEEDS[s.action]
    for (const k of ['path', 'locator', 'value', 'key']) {
      if (needs.includes(k) && s[k] === undefined) errors.push(`${w}.${k}: required for ${s.action}`)
      const optional = s.action === 'wait_for_text' && k === 'locator'
      if (!needs.includes(k) && !optional && s[k] !== undefined) errors.push(`${w}.${k}: not allowed for ${s.action}`)
    }
    if (s.path !== undefined) checkPath(s.path, `${w}.path`, errors)
    if (s.locator != null) checkLocator(s.locator, `${w}.locator`, errors)
    if (s.value !== undefined && !isStr(s.value, MAX.text, 0)) errors.push(`${w}.value: string`)
    if (s.key !== undefined && !KEYS.has(s.key)) errors.push(`${w}.key: not allowed`)
  }
  for (const [i, a] of assertions.entries()) {
    const w = `assertions[${i}]`
    if (!only(a, ['type', 'locator', 'value'], w, errors)) continue
    if (!ASSERTIONS.has(a.type)) errors.push(`${w}.type: not allowed (${a.type})`)
    if (!isStr(a.value, MAX.text)) errors.push(`${w}.value: required string`)
    if (a.type === 'url_contains' && a.locator != null) errors.push(`${w}.locator: not allowed for url_contains`)
    if (a.locator != null) checkLocator(a.locator, `${w}.locator`, errors)
  }
  return errors
}
