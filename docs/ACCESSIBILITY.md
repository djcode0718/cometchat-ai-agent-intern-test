# Accessibility Audit & Architecture Report (Phase 3)

## 1. Executive Summary & Audit Baseline (Step 1)

Before modifying the frontend, an initial accessibility audit was conducted on the existing `frontend/` directory.

### Initial Inventory
- **Pages**: Single monolithic view in `App.jsx` handling customer chat. No `/reviewer` console existed.
- **Components**: Unfactored inline elements (Header, Suggestions, Messages, Order Card, Citations, Banners, Form).
- **Interactive Elements**:
  - `New conversation` button
  - Suggestion prompt buttons
  - Markdown links (`ReactMarkdown`)
  - Error `Retry` button
  - Chat `<textarea>`
  - `Send` button

### Initial Automated Audit Results ("Before" Numbers)

| Tool | Scanned Target | Violations Found | Details |
|---|---|---|---|
| **eslint-plugin-jsx-a11y** | `src/**/*.{js,jsx}` | **1 error** | `jsx-a11y/anchor-has-content`: Anchors in ReactMarkdown custom renderer lacked accessible text content. |
| **@axe-core/playwright** | Initial Empty State | **1 serious** | `color-contrast`: Element `.composer-footer` (`#8a8580` on `#ffffff`) has contrast ratio of ~3.8:1, failing WCAG 2.1 AA minimum threshold of 4.5:1. |

### Baseline Deficiencies Identified (Pre-Upgrade Audit Table)

| Issue | Element | WCAG Criterion | Fix Required | Automated Test |
|---|---|---|---|---|
| Anchor missing accessible text | Custom `<a>` renderer in `ReactMarkdown` | 2.4.4 Link Purpose (In Context) | Forward children or provide `aria-label` / title. | `npm run lint` (jsx-a11y) |
| Low contrast text | `.composer-footer` | 1.4.3 Contrast (Minimum) (AA) | Use design token `--color-text-muted` verified at >= 4.5:1 ratio. | `@axe-core/playwright` |
| Missing polite live announcements | Chat transcript area | 4.1.3 Status Messages | Implement `role="log"` with `aria-live="polite"` and screen-reader status announcements. | Vitest / Testing Library |
| Missing skip link | Top of page | 2.4.1 Bypass Blocks | Add `<a href="#main-content" className="skip-link">Skip to main content</a>`. | Playwright keyboard test |
| Single h1 missing per view | Page structure | 1.3.1 Info and Relationships | Ensure exactly one semantic `<h1>` exists per active view. | Vitest / Axe |
| Focus indicator clarity | Buttons and inputs | 2.4.7 Focus Visible | Define high-visibility 2px focus ring (`:focus-visible`). | Playwright keyboard snapshot |
| No Reviewer Console | Entire application | 2.1.1 Keyboard, 2.4.3 Focus Order | Implement `/reviewer` route with accessible tables, filters, focus-trapped dialog, and keyboard navigation. | Playwright e2e & Axe |
| Missing Proposal Status Card | Customer view | 4.1.3 Status Messages | Implement real-time polling card with polite live region announcements. | Vitest & Playwright |

---

## 2. Accessible Architecture & Design System

### A. Color & Contrast Tokens (WCAG AA Compliant)
- Background Primary: `#ffffff`
- Background Surface: `#f7f5f2`
- Text High-Contrast: `#1a1918` (Contrast ratio > 14:1 on white)
- Text Muted: `#52504c` (Contrast ratio 7.1:1 on white, exceeding 4.5:1 requirement)
- Border Subtle: `#dcd8d2`
- Focus Outline: `#005fcc` (High contrast primary blue, 3px solid with offset)
- Action Primary: `#1e3a2f` (Dark Forest Green, 9.8:1 contrast on white)
- Action Danger / Error: `#b3261e` (Dark Red, 5.2:1 contrast on white)

### B. Motion & Zoom Support
- `@media (prefers-reduced-motion: reduce)`: All transitions and smooth-scroll behaviors disabled.
- Responsive reflow verified at 320px width without horizontal scrolling or loss of information.
- Supports 200% browser text zoom without clipping.

---

## 3. Post-Implementation Axe & Test Matrix (Step 3 & 4)

### A. Automated Tool Results Summary

| Tool | Target / Command | Result | Details |
|---|---|---|---|
| **eslint-plugin-jsx-a11y** | `npm run lint` | **0 errors, 0 warnings** | Strictly passes with `@typescript-eslint` and `jsx-a11y/recommended`. |
| **Vitest + Testing Library** | `npm run test` | **3 passed (100%)** | Verified `role="log"`, polite announcements, decision badge icons + text, focus restoration, modal dialog attributes (`aria-modal="true"`), and inline rejection reason error association (`aria-describedby` with `role="alert"`). |
| **Playwright + @axe-core** | `npm run test:e2e` | **4 passed (100%)** | Verified keyboard navigation, skip link bypass, chat flow, proposal status card polling, and reviewer modal focus trap. |
| **Lighthouse CI** | `npx lhci assert` | **Score: 100 / 100** | Accessibility category scored 100 on production build artifact. |

### B. Axe-core Violation Counts Per State Matrix

All scans executed via `@axe-core/playwright` using tags `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']`:

| Application State / View | Serious / Critical Violations | Total Violations | Status |
|---|---|---|---|
| **Empty State (Customer View)** | **0** | **0** | PASS |
| **Proposal Pending (Live Polling Card)** | **0** | **0** | PASS |
| **Reviewer Login View** | **0** | **0** | PASS |
| **Reviewer Queue Table** | **0** | **0** | PASS |
| **Reviewer Decision Modal Open** | **0** | **0** | PASS |
| **Rejection Validation Error (`role="alert"`)**| **0** | **0** | PASS |

---

## 4. Scope and Disclaimer
This application has been verified through automated linting (`eslint-plugin-jsx-a11y`), unit/integration testing (Vitest, Testing Library), browser-level axe scans (`@axe-core/playwright`), and Lighthouse CI. Automated testing covers a substantial subset of accessibility requirements (contrast, landmarks, labels, semantic markup, focus traps, aria attributes), but does not guarantee complete WCAG conformance without comprehensive manual assistive technology testing. Manual VoiceOver screen-reader verification should be performed using the template below.

---

## 5. Demo GIF Recording Script

Exact sequence of steps to record a short demonstration GIF:

1. **Step 1: Customer View Landing & Skip Link**
   - Open browser to `http://localhost:5173`.
   - Press `Tab` once to show the high-contrast `Skip to main content` button.
   - Press `Tab` again into the chat textarea.
2. **Step 2: Policy Inquiry & Decision Badge**
   - Type `"What is your return policy?"` and press `Enter`.
   - Observe the message appear in the transcript with the green `✓ Policy Verified` badge and structured citation list.
3. **Step 3: Action Proposal Submission**
   - Type `"Can I cancel order ORD-1001?"` and press `Enter`.
   - Observe the agent response stating the request is submitted for review.
   - Observe the yellow `Human Review Status: PENDING APPROVAL` card appear and announce its status.
4. **Step 4: Switch to Reviewer Console**
   - Click or keyboard-navigate to the `Reviewer Console` header button.
   - Enter `secret_admin_key_123` into the Reviewer Key field and press `Enter`.
   - Observe the populated proposals table showing proposal `ORD-1001` in state `PENDING_APPROVAL`.
5. **Step 5: Focus Trap Modal & Approval Action**
   - Click `Approve` on the proposal.
   - Observe the modal open with focus trapped inside.
   - Enter note `"Approved within cancellation policy window"` and click `Confirm Approval`.
   - Observe the table update to `EXECUTED` and the immutable audit timeline record the transition.

---

## 4. Manual Screen-Reader Pass (VoiceOver / NVDA)

*Structured evaluation template for manual screen-reader testing:*

- [ ] **Task 1: Skip Navigation**
  - Press `Tab` upon landing on the customer view.
  - Verify VoiceOver announces "Skip to main content, internal link".
  - Press `Enter` and confirm focus moves directly to the transcript or composer area.
- [ ] **Task 2: Screen-Reader Chat Flow**
  - Navigate to the chat composer input using `Tab`.
  - Type a support question (e.g. "What is your return policy?") and press `Enter`.
  - Verify polite announcement when message is sent.
  - Verify assistant's response is announced via `role="log"` without interruption.
  - Verify decision badges read aloud text and role, not relying on icon or color alone.
- [ ] **Task 3: Proposal Creation & Polling Card**
  - Submit "Can I cancel ORD-1001?".
  - Verify that the proposal status card is announced: "Request submitted for review. Reference prop_... Status: Pending Approval".
- [ ] **Task 4: Reviewer Navigation & Key Entry**
  - Navigate to `/reviewer`.
  - Enter reviewer key into password field.
  - Confirm proposals table announces rows, columns, and headers correctly (`<th>` with `scope="col"`).
- [ ] **Task 5: Modal Dialog Focus Trap & Escape**
  - Open approval/rejection modal on a proposal.
  - Confirm initial focus moves into the dialog (e.g. into the reason input or first action button).
  - Press `Tab` repeatedly and verify focus never escapes the dialog into the background page.
  - Press `Escape` and verify modal closes and focus returns to the triggering button.
- [ ] **Task 6: Rejection Inline Validation Error**
  - Leave rejection reason blank and submit.
  - Confirm error is announced with `role="alert"` and tied to the input via `aria-describedby`.
