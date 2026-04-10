import { Clerk } from '@clerk/clerk-js'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!publishableKey) {
  throw new Error('Add your VITE_CLERK_PUBLISHABLE_KEY to the .env file')
}

const clerkDomain = atob(publishableKey.split('_')[2]).slice(0, -1)

// DOM references
const signInBox = document.getElementById('sign-in')
const authLoading = document.getElementById('auth-loading')

function showAuthLoadError(message) {
  if (authLoading) {
    authLoading.innerHTML = `<p style="color: var(--on-primary, #fff); font-family: var(--font-body, sans-serif); text-align: center; padding: 1rem;">${message}</p>`
  }
}

try {
  // Load Clerk's visual pieces from the web
  await new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://${clerkDomain}/npm/@clerk/ui@1/dist/ui.browser.js`
    script.async = true
    script.crossOrigin = 'anonymous'
    script.onload = resolve
    script.onerror = () => reject(new Error('Failed to load @clerk/ui bundle'))
    document.head.appendChild(script)
  })

  const clerk = new Clerk(publishableKey)
  await clerk.load({
    ui: { ClerkUI: window.__internal_ClerkUICtor },
  })

  window.__clerk = clerk

  // Clerk has finished loading; lift the pending gate.
  document.body.classList.remove('auth-pending')

  const userBox = document.getElementById('user-button')

  function handleSessionExpired() {
    window.CONFIG.CLERK_TOKEN = null
    document.body.classList.add('signed-out')
    clerk.unmountUserButton(userBox)
    clerk.mountSignIn(signInBox)
  }

  if (clerk.isSignedIn) {
    clerk.mountUserButton(userBox)
    document.body.classList.remove('signed-out')

    // Get the session token and pass it to CONFIG for API requests
    const token = await clerk.session.getToken()
    window.CONFIG.CLERK_TOKEN = token

    const tokenRefreshInterval = setInterval(async () => {
      try {
        if (!clerk.session) {
          clearInterval(tokenRefreshInterval)
          handleSessionExpired()
          return
        }
        window.CONFIG.CLERK_TOKEN = await clerk.session.getToken()
      } catch (e) {
        clearInterval(tokenRefreshInterval)
        handleSessionExpired()
      }
    }, 50000)

    document.addEventListener('visibilitychange', async () => {
      if (document.visibilityState !== 'visible') return
      if (!clerk.session) {
        handleSessionExpired()
        return
      }
      try {
        window.CONFIG.CLERK_TOKEN = await clerk.session.getToken()
      } catch (e) {
        handleSessionExpired()
      }
    })

    clerk.addListener(({ session }) => {
      if (!session) {
        handleSessionExpired()
      }
    })

  } else {
    document.body.classList.add('signed-out')
    clerk.mountSignIn(signInBox)
  }
} catch (err) {
  console.error('Clerk failed to load:', err)
  showAuthLoadError("Sign-in is temporarily unavailable. Please refresh the page or try again later.")
}
