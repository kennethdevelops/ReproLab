import { initialProfile } from './data.mjs'

const MAX_NAME = 60

export function createProfileStore() {
  let profile = initialProfile()

  return {
    get() {
      return { ...profile }
    },
    update(input) {
      const displayName = typeof input.displayName === 'string' ? input.displayName : ''
      if (displayName.length === 0) {
        return { ok: false, field: 'displayName', message: 'Display name is required.' }
      }
      if (displayName.length > MAX_NAME) {
        return { ok: false, field: 'displayName', message: `Display name must be ${MAX_NAME} characters or fewer.` }
      }
      profile = {
        ...profile,
        displayName: displayName.trim(),
        newsletter: Boolean(input.newsletter),
      }
      return { ok: true, profile: { ...profile } }
    },
  }
}
