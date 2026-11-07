export const CITED_ATTRIBUTE = 'data-cited'

const CITED_MS = 1500

const clearTimers = new WeakMap<HTMLElement, ReturnType<typeof setTimeout>>()

export function findKeyedElement(keyAttribute: string, key: string): HTMLElement | null {
  const elements = Array.from(document.querySelectorAll<HTMLElement>(`[${keyAttribute}]`))
  return elements.find((element) => element.getAttribute(keyAttribute) === key) ?? null
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function markCited(element: HTMLElement): void {
  clearTimeout(clearTimers.get(element))
  element.removeAttribute(CITED_ATTRIBUTE)
  void element.offsetWidth
  element.setAttribute(CITED_ATTRIBUTE, '')
  clearTimers.set(
    element,
    setTimeout(() => element.removeAttribute(CITED_ATTRIBUTE), CITED_MS),
  )
}

export function revealKeyedElement(
  keyAttribute: string,
  key: string,
  block: ScrollLogicalPosition = 'center',
): boolean {
  const element = findKeyedElement(keyAttribute, key)
  if (element === null) {
    return false
  }
  element.scrollIntoView({ block, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  markCited(element)
  return true
}
