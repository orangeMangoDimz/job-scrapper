import type { Session } from '@/modules/auth/domain/entities/Session'

export interface SessionModel {
  auth_required: boolean
  signed_in: boolean
}

export function toSession(model: SessionModel): Session {
  return { isAuthRequired: model.auth_required, isSignedIn: model.signed_in }
}
