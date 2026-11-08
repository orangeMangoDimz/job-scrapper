export type JsonTokenKind = 'key' | 'string' | 'number' | 'literal' | 'punct' | 'plain'

export interface JsonToken {
  kind: JsonTokenKind
  text: string
}

const JSON_INDENT = 2
// Above this many characters the viewer skips coloring, one node per token freezes the tab
export const MAX_HIGHLIGHT_CHARS = 200_000
const TOKEN_PATTERN =
  /("(?:\\.|[^"\\])*")(\s*:)?|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\b(?:true|false|null)\b|[{}[\],:]/g

export function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, JSON_INDENT) ?? ''
}

function pushPlain(tokens: JsonToken[], text: string): void {
  if (text === '') {
    return
  }
  const last = tokens[tokens.length - 1]
  if (last?.kind === 'plain') {
    tokens[tokens.length - 1] = { kind: 'plain', text: last.text + text }
    return
  }
  tokens.push({ kind: 'plain', text })
}

function toToken(match: RegExpExecArray): JsonToken[] {
  const [text, quoted, colon] = match
  if (quoted !== undefined) {
    if (colon === undefined) {
      return [{ kind: 'string', text: quoted }]
    }
    return [
      { kind: 'key', text: quoted },
      { kind: 'plain', text: colon.slice(0, -1) },
      { kind: 'punct', text: ':' },
    ]
  }
  if (/^[{}[\],:]$/.test(text)) {
    return [{ kind: 'punct', text }]
  }
  if (/^(?:true|false|null)$/.test(text)) {
    return [{ kind: 'literal', text }]
  }
  return [{ kind: 'number', text }]
}

// Splits pretty printed JSON into typed pieces. The pieces always join back to
// the exact input, and the view renders each one as text, never as HTML.
export function tokenizeJson(text: string): JsonToken[] {
  const tokens: JsonToken[] = []
  let cursor = 0
  for (const match of text.matchAll(TOKEN_PATTERN)) {
    pushPlain(tokens, text.slice(cursor, match.index))
    for (const token of toToken(match)) {
      if (token.kind === 'plain') {
        pushPlain(tokens, token.text)
      } else {
        tokens.push(token)
      }
    }
    cursor = match.index + match[0].length
  }
  pushPlain(tokens, text.slice(cursor))
  return tokens
}
