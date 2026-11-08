import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT_FONT_PX = 16
const MIN_TEXT_PX = 16
const MIN_LINE_HEIGHT_PX = 24
const SRC_DIR = resolve(process.cwd(), 'src')
const STYLES_DIR = join(SRC_DIR, 'shared/styles')
const SOURCE_EXTENSIONS = ['.vue', '.css', '.ts']

function listSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      return name === '__tests__' ? [] : listSourceFiles(path)
    }
    return SOURCE_EXTENSIONS.some((ext) => name.endsWith(ext)) ? [path] : []
  })
}

function toPx(value: number, unit: string): number {
  return unit === 'px' ? value : value * ROOT_FONT_PX
}

function readStyleTokens(): string {
  return readdirSync(STYLES_DIR)
    .filter((name) => name.endsWith('.css'))
    .map((name) => readFileSync(join(STYLES_DIR, name), 'utf8'))
    .join('\n')
}

describe('minimum readable text size', () => {
  it('keeps every --text-* font-size token at 16px or larger', () => {
    const tokens = [...readStyleTokens().matchAll(/--text-([a-z-]+):\s*(\d+(?:\.\d+)?)(px|rem)\s*;/g)]
      .filter(([, name]) => !name!.includes('--'))
      .map(([, name, value, unit]) => ({ name: name!, px: toPx(Number(value), unit!) }))

    expect(tokens.map((t) => t.name)).toEqual(
      expect.arrayContaining(['display', 'title', 'heading', 'subheading', 'body', 'body-sm', 'caption', 'code']),
    )
    expect(tokens.filter((t) => t.px < MIN_TEXT_PX)).toEqual([])
  })

  it('gives every 16px token a line height of at least 24px', () => {
    const css = readStyleTokens()
    const sixteens = [...css.matchAll(/--text-([a-z-]+):\s*16px\s*;/g)]
      .map(([, name]) => name!)
      .filter((name) => !name.includes('--'))
    const tooTight = sixteens.filter((name) => {
      const match = css.match(new RegExp(`--text-${name}--line-height:\\s*(\\d+)px`))
      return !match || Number(match[1]) < MIN_LINE_HEIGHT_PX
    })

    expect(sixteens.length).toBeGreaterThan(0)
    expect(tooTight).toEqual([])
  })

  it('has no hardcoded font size below 16px anywhere in src', () => {
    const offenders = listSourceFiles(SRC_DIR).flatMap((file) => {
      const text = readFileSync(file, 'utf8')
      const hardcoded = [...text.matchAll(/font-size:\s*(\d*\.?\d+)(px|rem|em)/g)]
        .filter(([, value, unit]) => toPx(Number(value), unit!) < MIN_TEXT_PX)
      const arbitrary = [...text.matchAll(/\btext-\[(\d*\.?\d+)(px|rem|em)\]/g)]
        .filter(([, value, unit]) => toPx(Number(value), unit!) < MIN_TEXT_PX)
      const keywords = [...text.matchAll(/font-size:\s*(x{1,2}-small|small|smaller)\b/g)]
      const defaults = [...text.matchAll(/(?<![\w-])text-(xs|sm)\b/g)]
      return [...hardcoded, ...arbitrary, ...keywords, ...defaults].map(
        (m) => `${relative(SRC_DIR, file)}: ${m[0]}`,
      )
    })

    expect(offenders).toEqual([])
  })
})
