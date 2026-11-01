import { describe, expect, it } from 'vitest'
import { parseKeywords } from '@/shared/utils/parseKeywords'

describe('parseKeywords', () => {
  it('splits on commas and trims', () => {
    expect(parseKeywords(' django, flask ')).toEqual(['django', 'flask'])
  })

  it('drops empty entries', () => {
    expect(parseKeywords('django,, ,')).toEqual(['django'])
  })
})
