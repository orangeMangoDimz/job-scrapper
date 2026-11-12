import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const INDEX_HTML = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')

describe('index.html', () => {
  it('starts with the Loading title and no brand', () => {
    expect(INDEX_HTML).toContain('<title>Loading</title>')
    expect(INDEX_HTML).not.toContain('NoNo Scraper')
  })

  it('links the ico and svg favicons that ship in public', () => {
    expect(INDEX_HTML).toContain('<link rel="icon" href="/favicon.ico" sizes="48x48" />')
    expect(INDEX_HTML).toContain('<link rel="icon" href="/favicon.svg" type="image/svg+xml" />')
    expect(existsSync(resolve(process.cwd(), 'public/favicon.ico'))).toBe(true)
    expect(existsSync(resolve(process.cwd(), 'public/favicon.svg'))).toBe(true)
  })
})
