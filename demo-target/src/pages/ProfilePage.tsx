import { useEffect, useState, type FormEvent } from 'react'
import { api, type Profile } from '../lib/api'

export function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [newsletter, setNewsletter] = useState(false)
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    api
      .getProfile()
      .then((p) => {
        setProfile(p)
        setDisplayName(p.displayName)
        setNewsletter(p.newsletter)
      })
      .catch(() => setStatus({ ok: false, text: 'Could not load your profile.' }))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus(null)
    try {
      const result = await api.saveProfile({ displayName, newsletter })
      setStatus(
        result.ok
          ? { ok: true, text: 'Profile saved.' }
          : { ok: false, text: result.message ?? 'Could not save.' },
      )
      if (result.profile) setProfile(result.profile)
    } catch {
      setStatus({ ok: false, text: 'Could not save your profile. Please try again.' })
    }
  }

  return (
    <section>
      <h1>Profile settings</h1>
      {!profile && !status && <p role="status">Loading profile…</p>}
      {profile && (
        <form onSubmit={onSubmit} className="profile-form" noValidate>
          <label>
            Display name
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>
            Email
            <input value={profile.email} readOnly aria-readonly="true" />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={newsletter}
              onChange={(e) => setNewsletter(e.target.checked)}
            />
            Send me the monthly newsletter
          </label>
          <button type="submit">Save profile</button>
        </form>
      )}
      {status && (
        <p role={status.ok ? 'status' : 'alert'} className={status.ok ? 'success' : 'error'}>
          {status.text}
        </p>
      )}
    </section>
  )
}
