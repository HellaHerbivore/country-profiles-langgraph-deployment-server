import { Clerk } from '@clerk/clerk-js'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!publishableKey) {
  throw new Error('Add your VITE_CLERK_PUBLISHABLE_KEY to the .env file')
}

const clerkDomain = atob(publishableKey.split('_')[2]).slice(0, -1)

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

// Find the different parts of your web page
const userBox = document.getElementById('user-button')
const signInBox = document.getElementById('sign-in')
const formSection = document.getElementById('form-section')

// Check if the user is logged in
if (clerk.isSignedIn) {
  clerk.mountUserButton(userBox)
  formSection.style.display = 'block'
  signInBox.style.display = 'none'

  // Get the session token and pass it to CONFIG for API requests
  const token = await clerk.session.getToken()
  CONFIG.CLERK_TOKEN = token

  // Refresh the token every 50 seconds (Clerk tokens expire after 60s)
  setInterval(async () => {
    CONFIG.CLERK_TOKEN = await clerk.session.getToken()
  }, 50000)
} else {
  clerk.mountSignIn(signInBox)
  formSection.style.display = 'none'
}
