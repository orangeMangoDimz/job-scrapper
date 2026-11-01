export function parseKeywords(text: string): string[] {
  return text
    .split(',')
    .map((keyword) => keyword.trim())
    .filter((keyword) => keyword !== '')
}
