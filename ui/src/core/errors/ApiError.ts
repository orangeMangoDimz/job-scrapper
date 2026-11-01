export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: Record<string, string[]>
  readonly data: unknown

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string[]> = {},
    data: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
    this.data = data
  }
}
