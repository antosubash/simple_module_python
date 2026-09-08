# Hi-Fi deck gap analysis — auth-screens-02-07

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

# Design-vs-implementation gap analysis: auth screens (02–07)

**Shared context.** All six `users` pages render inside `/home/anto/Repos/simple_module_python/packages/ui/src/layouts/AuthCardShell.tsx`: one centered glass card, `max-w-md` (448px), `rounded-3xl p-7 bg-white/85`, two emerald blur blobs, and a `BrandingMark` lockup (badge + `branding.appName`, default "SimpleModule", caption `python`) *inside* the card. No footer/copyright, and `bg-white/85` is hardcoded so the `.dark` variant (which the deck tokens define) is not honoured. Fonts already match the deck (`--font-display: Sora`, `--font-sans: DM Sans`, `--font-mono: JetBrains Mono` in `packages/ui/src/styles/globals.css`); primary is already emerald. Deck inputs are ~46px tall / radius 10px and buttons ~48px; the app's shadcn `Input` is `h-9 rounded-md` and `Button size="lg"` is `h-10`. The deck uses three distinct page shapes — a dark-brand split (Login), a light two-column "intro + card" (Register, Invite), and a single centered card (Forgot/Verify/Keycloak) — while the app has only the third. A shell variant (e.g. `AuthCardShell variant="split" aside={…}`) is the prerequisite for screens 02, 03 and 06. No `PasswordInput` (show/hide) or password-strength component exists anywhere in the repo (`ui/progress.tsx` and `ui/checkbox.tsx` do exist).

---

## 02 — Log in

**1. Route / files.** `GET /users/login` → `Users/Login` in `/home/anto/Repos/simple_module_python/modules/users/users/auth_local/views.py` (L33–69). Page: `/home/anto/Repos/simple_module_python/modules/users/users/pages/Login.tsx`. Props: `allow_signup`, `dev_accounts`, `login_redirect_url`, `oauth_providers[{name, display_name}]`. Submit: `POST /api/users/auth/login` (`auth_local/api.py` L81–118).

**2. Deck structure.** 1440×860 grid `1.05fr 1fr`.
- Left pane, `#0f172a` with teal blur blob: lockup "S" + "simple_module_py"; H2 "One admin surface for every module you install."; p "Users, permissions, settings, files, background tasks and audit history — all wired up on boot."; check rows "Sessions, invites and password reset built in", "Keycloak SSO when you need it"; footer "© 2026 simple_module_py".
- Right pane, 420px column: H1 "Sign in"; p "Use your workspace email and password."; label "Email" / placeholder "you@example.com"; label "Password" with right-aligned link "Forgot password?"; password input shown focused with trailing "Show" toggle; checked checkbox "Keep me signed in for 30 days"; primary "Sign in"; rule-divider "or"; outline "Continue with Keycloak SSO"; footer "No account? Register — or ask an admin to invite you."

**3. Already matches.** Field order, forgot link right-aligned on the password label baseline, full-width primary submit, gated sign-up line, outline buttons for OAuth providers, font/colour tokens.

**4. Deltas.**
1. Layout: single card vs dark brand column + form column. Add a split variant to `AuthCardShell.tsx` (aside slot, dark background, lockup, copyright) and use it in `Login.tsx`. Aside copy needs new keys (`packages/ui/locales/en.json`, e.g. `ui.auth_aside.*`).
2. Copy (`modules/users/users/locales/en.json` → `users.login.*`): heading "Welcome back" → "Sign in"; subtitle "Log in to your workspace." → "Use your workspace email and password."; `forgot_link` "Forgot?" → "Forgot password?"; `submit` "Log in" → "Sign in". Six e2e files pin `get_by_role("button", name="Log in")` (`tests/e2e/test_{audit_log_ui,document_titles,error_pages,i18n_rendering,settings_ui,shell_ui}.py`) — update alongside.
3. Show/hide password toggle missing. Create `packages/ui/src/components/PasswordInput.tsx` (Eye/EyeOff, translated `aria-label`) and use it here and in 03/04/06.
4. "Keep me signed in for 30 days" checkbox missing entirely (`Login.tsx`); requires backend (see §5).
5. Divider + SSO: app shows a `border-t` with mono caption "Or continue with" and buttons labelled `display_name`; deck shows a rule "or" and "Continue with Keycloak SSO". Add key `users.login.continue_with` = "Continue with {name}", restyle divider, and move the OAuth block *above* the "No account?" line (deck order).
6. Footer: "Don't have an account? Sign up" → "No account? Register — or ask an admin to invite you." (`no_account`, `sign_up`, plus a new suffix key).
7. Input/button sizing (h-9/h-10 vs ~46/48px, radius 10) — decide on a `size="lg"` for `Input` or auth-page overrides.
8. Deck has no dev quick-login, inline error, or needs-verification banner; app has all three — keep (05's "Waiting on you" covers the unverified case).

**5. Backend/props.** A `remember` field on `POST /api/users/auth/login` that varies the cookie max-age (`auth_local/api.py`; today fixed at `cookie_max_age_seconds` = 14 days in `settings.py`). The SSO button label is settings-driven (`oauth_oidc_display_name`, default "OIDC") — nothing to add, but "Keycloak SSO" only appears if an admin sets it.

**6. Ambiguities.** "30 days" vs the 14-day cookie / 30-day refresh-token settings — derive from a setting or fix copy. Whether "— or ask an admin to invite you." remains when `allow_signup` is false. "Continue with Keycloak SSO" must be the users-module OIDC provider (SM020 forbids the `keycloak` module coexisting with `users`), not a link to `/keycloak/login`. Narrow-viewport behaviour of the dark pane (deck is 1440 only). "Show" as text vs icon.

---

## 03 — Register

**1. Route / files.** `GET /users/register` (404 unless `allow_signup`) → `Users/Register`, no props (`auth_local/views.py` L85–89). Page: `/home/anto/Repos/simple_module_python/modules/users/users/pages/Register.tsx`. Submit: fastapi-users `POST /api/users/auth/register` with `full_name`.

**2. Deck structure.** 940px two-column grid, vertically centred.
- Left (no card): lockup "S" + "simple_module_py"; H1 "Create your account"; p "Open registration is on for this instance. The first account becomes the admin; later ones get the default role."; checks "Email verification is required before first sign-in", "Admins can close registration in `users.allow_signup`".
- Right card (radius 14, padding 32, shadow-lg): "Full name" placeholder "Optional"; "Email" value "rob@example.com"; "Password" + strength bar (78%) label "strong" + helper "At least 8 characters and not all numbers."; "Confirm password" in error state (red border) + "Passwords do not match"; primary "Create account"; "Already have an account? Sign in".

**3. Already matches.** H1 "Create your account", field order (name, email, password, confirm), have-account line linking to `LOGIN_PATH`, weak-password server errors surfaced.

**4. Deltas.**
1. Layout: single card vs intro column + form card (light variant of the split shell). `Register.tsx`.
2. Subtitle: app "Public signup — controlled by `SM_USERS_ALLOW_SIGNUP`." → deck paragraph + two check rows, referencing the settings key `users.allow_signup` (not the env var). Replace `users.register.subtitle_prefix` with `intro`, `bullet_verification`, `bullet_close_prefix`.
3. Full-name placeholder "Your name" → "Optional" (new register-specific key; `users.common.name_placeholder` is shared).
4. Strength meter missing. New `packages/ui/src/components/PasswordStrength.tsx` (wrap `ui/progress`), labels need keys ("strong", "ok", presumably "weak").
5. Helper text "At least 8 characters and not all numbers." missing (app has placeholder "8+ characters"). Note the server also rejects passwords containing the email (`manager.py` L45–53) — deck helper omits it.
6. Field-level error: deck shows red border on Confirm + inline "Passwords do not match"; app shows one `text-destructive` paragraph under the form with "Passwords do not match." and no `aria-invalid`. Change in `Register.tsx`.
7. Submit "Sign up" → "Create account" (`users.register.submit`).
8. "Already have an account? Log in" → "… Sign in" — app reuses `users.common.log_in`; add `users.common.sign_in` rather than repurposing.
9. Success state ("Check your inbox / We've sent a verification link to {email}.") exists in app, absent in deck — keep.

**5. Backend/props.** None required. If the "first account becomes the admin" line is kept, confirm it against `users/bootstrap.py` (the admin is seeded from `bootstrap_email`/`bootstrap_password` env, so the claim may be false for this codebase).

**6. Ambiguities.** Strength scoring and thresholds; truth of the "first account becomes the admin" claim; whether `require_verification=False` should suppress the "Email verification is required…" bullet; mobile stacking order.

---

## 04 — Forgot / reset password

**1. Route / files.** `GET /users/forgot-password` → `Users/ForgotPassword` (no props); `GET /users/reset-password?token=` → `Users/ResetPassword` `{token}` (`auth_local/views.py` L92–99). Pages: `/home/anto/Repos/simple_module_python/modules/users/users/pages/ForgotPassword.tsx`, `/home/anto/Repos/simple_module_python/modules/users/users/pages/ResetPassword.tsx`. APIs: `POST /api/users/auth/forgot-password` (202 always), `POST /api/users/auth/reset-password` (stock fastapi-users).

**2. Deck structure.** Four cards (28px padding), each with an uppercase eyebrow:
- "1 · Request": H2 "Forgot password"; p "We'll email a one-time link valid for 60 minutes."; "Email" / "you@example.com"; primary "Send reset link"; link "Back to sign in".
- "2 · Sent": ✉ tile (44px, soft emerald); H2 "Check your inbox"; p "If an account exists for **you@example.com**, a reset link is on its way. The same message shows either way."; amber callout "Console mailer: the link is in the server log."; link "Resend in 0:42".
- "3 · New password": H2 "Set a new password"; "New password"; "Confirm"; strength bar (60%) "ok"; primary "Save and sign in".
- "Edge case" (red border): ⧗ red tile; H2 "Link expired"; p "Reset links last 60 minutes and work once. Request a fresh one — the old link is now dead."; primary "Request a new link".

**3. Already matches.** "Forgot password" heading, "Send reset link" button, "Check your inbox" sent title, anti-enumeration behaviour, "New password" label, console-mailer mention (as a sentence).

**4. Deltas.**
1. Request subtitle "We'll email you a one-time reset link." → "We'll email a one-time link valid for {minutes} minutes." (`users.forgot_password.subtitle`; minutes from a prop, not hardcoded).
2. Back link "Remembered? Log in" → "Back to sign in" (collapse `remembered` + `common.log_in`; also align `common.back_to_login` "Back to log in" used on Register/Forgot-sent/Verify).
3. Sent state: app renders a small green inline banner with `CheckCircle2` and a combined sentence "If {email} has an account, a reset link is on its way. The console mailer logs it to stdout." Deck: page-level ✉ tile + H2 + paragraph with bold email + separate amber callout + countdown "Resend in 0:42" that becomes a resend action. Split `sent_body` / `console_mailer_note`; gate the callout on the mailer; add the resend timer + re-POST in `ForgotPassword.tsx`.
4. Reset form: H1 "Reset password" → "Set a new password"; drop subtitle "Choose a new password and you'll be redirected to log in."; label "Confirm password" → "Confirm"; submit "Reset password" → "Save and sign in"; add strength meter (`ResetPassword.tsx`, `users.reset_password.*`).
5. Expired-link state: app only shows inline "Reset failed. The link may have expired." after submit (and `no_token` when absent). Deck wants a distinct red-bordered "Link expired" card with ⧗ icon and "Request a new link" → `/users/forgot-password`. Add a state branch in `ResetPassword.tsx`.
6. Eyebrows "1 · Request" etc. are storyboard chrome — do not implement.

**5. Backend/props.** (a) `reset_link_lifetime_minutes` prop (`reset_password_token_lifetime_seconds` = 3600) on the forgot view; (b) `mailer_delivers` prop — `admin/views.py` L114–123 already computes this, reuse it on `forgot_password_page`; (c) optionally pre-decode the reset token on `GET /users/reset-password` (mirroring `invite_preview.py`) so "Link expired" renders on load, not after submit; (d) "Save and sign in" literally requires a reset+login wrapper (stock endpoint only resets; app then `router.visit(LOGIN_PATH)`) — pattern exists in `accept_invite` (`auth_local/api.py` L143–177); (e) resend is subject to the 10/5-min throughput limiter — countdown should be ≥ that cadence or expect 429s.

**6. Ambiguities.** Whether "Save and sign in" means auto-login; countdown length ("0:42" is illustrative); expired state on GET vs after POST; "work once" holds today (token carries a password fingerprint) — fine to keep.

---

## 05 — Email verification

**1. Route / files.** `GET /users/verify?token=` → `Users/VerifyEmail` `{token}` (`auth_local/views.py` L102–104). Page: `/home/anto/Repos/simple_module_python/modules/users/users/pages/VerifyEmail.tsx` — POSTs `/api/users/auth/verify` on mount; states `pending | success | already_verified | error`. The unverified-login case is handled inline on `Login.tsx` (L138–152) when the API returns `LOGIN_USER_NOT_VERIFIED`.

**2. Deck structure.** Three left-aligned cards (32px padding):
- ✓ soft-emerald tile (46px); H2 "Email verified"; p "Your address is confirmed. You can sign in now."; primary "Go to sign in".
- ⧗ amber tile, amber card border; H2 "Link expired"; p "Verification links last 24 hours. We can send a new one to the same address."; outline "Resend verification".
- ✉ grey tile; H2 "Waiting on you"; p "Shown when an unverified account tries to sign in. Nothing else is reachable until it's done."; mono chip "rob@example.com".

**3. Already matches.** Success state with icon + login button; error state with icon; single-card icon/title/description/action shape.

**4. Deltas.**
1. Success copy: "Email verified!" → "Email verified"; "Your account is now active." → "Your address is confirmed. You can sign in now."; button "Log in" → "Go to sign in" (`users.verify_email.success_*`, new key for the button).
2. Expired: "Verification failed" / "Verification link expired or invalid. Please request a new one." + "Back to log in" link → "Link expired" / "Verification links last {hours} hours. We can send a new one to the same address." + outline button "Resend verification" that POSTs `/api/users/auth/request-verify-token`. Card gets an amber border and amber tile (app uses red `XCircle`). `VerifyEmail.tsx`.
3. Lifetime copy: "24 hours" vs `verification_token_lifetime_seconds` = 7 days — pass as prop or change copy.
4. "Waiting on you" interstitial does not exist. Today it is an amber inline banner on Login ("Verify your email" + "Resend verification email"). Implement as a state branch in `Login.tsx` (email is already in component state), rendering the ✉ tile, heading, and a mono email chip; add `users.login.waiting_*` keys.
5. Icon tile: app 48px round `bg-secondary` with a coloured lucide icon, centred text; deck 46px rounded-13 tile tinted per state, left-aligned content.
6. `pending` and `already_verified` states exist in app, not in deck — keep.

**5. Backend/props.** For "Resend verification" on an expired token the page needs the address: decode the token with `verify_exp=False` server-side (new helper beside `invite_preview.py`) and pass `email`; plus `verification_lifetime_hours`. Otherwise fall back to an email input.

**6. Ambiguities.** The "Waiting on you" description reads as designer annotation, not user copy — needs real copy. Whether resend requires re-entering the email. Whether the pending spinner state should adopt the same tile style.

---

## 06 — Accept invite

**1. Route / files.** `GET /users/invite/accept?token=` → `Users/AcceptInvite` `{token, invite: {email, roles[], already_accepted} | null}` (`auth_local/views.py` L107–121; `auth_local/invite_preview.py`). Page: `/home/anto/Repos/simple_module_python/modules/users/users/pages/AcceptInvite.tsx`. Submit: `POST /api/users/auth/accept-invite` `{token, password}` (verify + set password + login) → `router.visit('/dashboard/')`.

**2. Deck structure.** 900px two-column, centred.
- Left: lockup "S" + "Acme Admin"; H1 "Dana invited you to Acme Admin"; p "Set a password to finish. Your email and role are fixed by the invite."; summary card rows: "Email" → mono `rob@example.com`; "Role" → pill "viewer"; "Expires" → "in 5 days".
- Right card (padding 34, shadow-lg): H2 "Accept invite"; "Full name" (value "Rob Meyer"); "Password" (focused); "Confirm password"; primary "Join workspace"; helper "Accepting verifies your email — no second step."

**3. Already matches.** Invitee email and role pills shown before the password ask; password + confirm; submit lands on the dashboard; already-used notice.

**4. Deltas.**
1. Layout: single card with a green banner vs intro + summary card left, form card right (light split shell). `AcceptInvite.tsx`.
2. Headline "You've been invited as {email}" + "Set your password" → "{inviter} invited you to {appName}" + card H2 "Accept invite". Inviter name is unavailable today (see §5); fallback "You've been invited to {appName}".
3. Subtitle "Pick a password and you'll be signed in." → "Set a password to finish. Your email and role are fixed by the invite."
4. Summary card: replace the banner's "Access:" pills with a key/value card — Email (mono), Role (pill), Expires (relative; `packages/ui/src/lib/relative-time.ts` exists).
5. "Full name" field missing from the form (and from the API body).
6. Submit "Set password & sign in" → "Join workspace" (`users.accept_invite.submit`).
7. Helper "Accepting verifies your email — no second step." missing (new key).
8. Mono `token=…` echo line (L143–148) is not in the deck — remove or keep for support.
9. `already_accepted` amber note exists in app, not in deck — keep.

**5. Backend/props.** (a) `inviter_name`: the invite JWT only carries `sub`/`email`/`aud` (`manager.py` L149–165) and `invited_by` is only recorded as `assigned_by` on the role row (`admin/service.py` L125–153) — add an `invited_by` claim when minting in `admin/bulk_invite.py`/`admin/api.py`, or store on the user, and surface it from `preview_invite`. (b) `expires_at` from the JWT `exp` in `preview_invite`. (c) Optional `full_name` on `AcceptInviteRequest` (`contracts/schemas.py`) applied in `accept_invite` (`auth_local/api.py` L148–177). Update `modules/users/tests/test_views.py::test_accept_invite_returns_200` and preview tests.

**6. Ambiguities.** Rendering for multiple roles (deck shows one pill); what to show when `invite` is `null` (expired/tampered) — deck has no state, reuse 04/05 "Link expired"; whether Full name is required or pre-filled from an admin-created account; inviter fallback when the admin account is gone.

---

## 07 — Keycloak SSO

**1. Route / files.** `GET /keycloak/login` → `Keycloak/Login` (`/home/anto/Repos/simple_module_python/modules/keycloak/keycloak/endpoints/views.py` L16–18); page `/home/anto/Repos/simple_module_python/modules/keycloak/keycloak/pages/Login.tsx` calls `router.get('/api/keycloak/auth/login')` on mount and renders a bare centred paragraph. `POST /keycloak/logout` clears the session and redirects to Keycloak end-session with `post_logout_redirect_uri=/keycloak/login` (L20–41). **`Keycloak/LoggedOut` (`pages/LoggedOut.tsx`) is never rendered by any view** — it appears only in the Vite manifest, so the signed-out interstitial is unreachable today.

**2. Deck structure.** Two centred cards (padding 40, centred text):
- ⇥ soft-emerald tile (52px); H2 "Redirecting to your identity provider"; p "Taking you to `sso.acme.co/realms/acme`. You'll come straight back once signed in."; 220px progress bar; link "Not redirected? Continue manually".
- ⏻ grey tile; H2 "You're signed out"; p "Your app session and the Keycloak session both ended. Close the browser to be certain on a shared machine."; primary "Sign in again" + outline "Back to site".

**3. Already matches.** Redirect-on-mount; "Sign in again" label (`keycloak.logout.sign_in_again`).

**4. Deltas.**
1. Login page has no shell: wrap in `AuthCardShell` (gains `BrandingHead`/`BrandingBanner`), add the icon tile, H2 "Redirecting to your identity provider" (current "Redirecting to identity provider…"), paragraph with the realm URL in `<code>`, an indeterminate `ui/progress`, and "Not redirected? Continue manually" as `<a href="/api/keycloak/auth/login">`. `pages/Login.tsx`, `locales/en.json`.
2. Interaction: `router.get()` issues an Inertia XHR against an endpoint that 302s to an external origin; a full-page `window.location.assign('/api/keycloak/auth/login')` is the safer redirect (verify in browser — not run here).
3. Signed-out page unreachable: add `GET /keycloak/logged-out` rendering `Keycloak/LoggedOut` in `endpoints/views.py`, point `post_logout_redirect_uri` at it (L38), and add the path to `get_public_paths()` in `keycloak/provider.py` L45–47 so `AuthMiddleware` doesn't bounce it.
4. Signed-out copy/shape: "Signed Out" → "You're signed out"; "You have been signed out successfully." → the deck sentence; underlined `Link` → primary `Button` "Sign in again" (`/keycloak/login`) plus outline "Back to site" (`/`); wrap in the shell with a `Power` icon tile. `pages/LoggedOut.tsx`, `keycloak.logout.*` keys.

**5. Backend/props.** `realm_url` prop (`f"{settings.server_url}/realms/{settings.realm}"` from `request.app.state.keycloak.settings`) on the login view; the new logged-out route + public-path registration; redirect target change. Check `modules/keycloak/tests` for assertions on the logout redirect.

**6. Ambiguities.** What the realm line shows when `server_url`/`realm` are blank in dev; progress bar as indeterminate vs a timed reveal of the manual link; whether the redirect card should also serve the users-module OAuth providers.

---

## Overall summary (largest gap first)

1. **Login** — new dark split layout, remember-me (needs a backend flag), show/hide toggle, SSO divider/label/order, four copy changes that also break six e2e selectors.
2. **Accept invite** — light split layout with a summary card, plus three backend additions (inviter name, expiry, full name on accept).
3. **Forgot / reset** — two missing states (sent-with-callout+resend, link-expired), strength meter, "Save and sign in" auto-login, mailer/lifetime props.
4. **Keycloak** — small code but a structural bug: the signed-out page is orphaned; both interstitials need a shell, realm prop, and a new public route.
5. **Register / Verify** — Register is layout + strength meter + field-level errors + copy; Verify is mostly copy plus a resend action (needs email prop) and a new "Waiting on you" state on Login.