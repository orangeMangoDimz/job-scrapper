import { describe, expect, it } from 'vitest'
import { prettyJson, tokenizeJson } from '@/modules/runs/presentation/components/jsonTokens'

function kinds(value: unknown): [string, string][] {
  return tokenizeJson(prettyJson(value))
    .filter((token) => token.kind !== 'plain')
    .map((token) => [token.kind, token.text])
}

describe('prettyJson', () => {
  it('indents with two spaces', () => {
    expect(prettyJson({ a: [1] })).toBe('{\n  "a": [\n    1\n  ]\n}')
  })
})

describe('tokenizeJson', () => {
  it('marks keys, strings, numbers and literals apart', () => {
    expect(kinds({ name: 'x', n: -1.5e21, ok: true, no: false, none: null })).toEqual([
      ['punct', '{'],
      ['key', '"name"'],
      ['punct', ':'],
      ['string', '"x"'],
      ['punct', ','],
      ['key', '"n"'],
      ['punct', ':'],
      ['number', '-1.5e+21'],
      ['punct', ','],
      ['key', '"ok"'],
      ['punct', ':'],
      ['literal', 'true'],
      ['punct', ','],
      ['key', '"no"'],
      ['punct', ':'],
      ['literal', 'false'],
      ['punct', ','],
      ['key', '"none"'],
      ['punct', ':'],
      ['literal', 'null'],
      ['punct', '}'],
    ])
  })

  it('treats a string that looks like a number or literal as a string', () => {
    expect(kinds(['42', 'true', 'null'])).toEqual([
      ['punct', '['],
      ['string', '"42"'],
      ['punct', ','],
      ['string', '"true"'],
      ['punct', ','],
      ['string', '"null"'],
      ['punct', ']'],
    ])
  })

  it('keeps escaped quotes and colons inside one string token', () => {
    const tokens = kinds({ 'a"b': 'say "hi": now' })

    expect(tokens).toContainEqual(['key', '"a\\"b"'])
    expect(tokens).toContainEqual(['string', '"say \\"hi\\": now"'])
  })

  it('does not treat a string value followed by text as a key', () => {
    expect(kinds(['a:b'])).toContainEqual(['string', '"a:b"'])
  })

  it('gives back exactly the original text when tokens are joined', () => {
    const text = prettyJson({ a: [1, 'two', { three: null }], b: '<script>' })

    expect(
      tokenizeJson(text)
        .map((token) => token.text)
        .join(''),
    ).toBe(text)
  })

  it('returns no tokens for empty text', () => {
    expect(tokenizeJson('')).toEqual([])
  })
})
