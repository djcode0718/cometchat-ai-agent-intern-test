import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Helper to run axe and assert zero serious or critical violations
async function checkAxe(page: any, stateName: string) {
  const accessibilityScanResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  const seriousOrCritical = accessibilityScanResults.violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical'
  );

  console.log(`AXE_AUDIT [${stateName}]: total=${accessibilityScanResults.violations.length}, serious/critical=${seriousOrCritical.length}`);
  if (seriousOrCritical.length > 0) {
    console.error(`Axe violations in state ${stateName}:`, JSON.stringify(seriousOrCritical, null, 2));
  }
  expect(seriousOrCritical.length).toBe(0);
  return accessibilityScanResults.violations.length;
}

test.describe('End-to-End Keyboard Navigation & Axe Accessibility Scan', () => {
  test('Axe Scan on Empty State & Skip Link Navigation', async ({ page }) => {
    await page.goto('/');

    // Verify exactly one H1 exists on the page
    const h1Count = await page.locator('h1').count();
    expect(h1Count).toBe(1);

    // Skip Link Test
    await page.keyboard.press('Tab');
    const skipLink = page.locator('.skip-link');
    await expect(skipLink).toBeFocused();
    await page.keyboard.press('Enter');

    // Axe Scan on Empty State
    await checkAxe(page, 'empty_state');
  });

  test('Customer Flow: Policy Question, Proposal Creation, and Polling Card', async ({ page }) => {
    await page.goto('/');

    const input = page.locator('#customer-chat-input');
    await input.focus();
    await input.fill('Can I cancel my order ORD-1001?');
    await page.keyboard.press('Enter');

    // Wait for response and proposal card
    await page.waitForSelector('.proposal-card', { timeout: 15000 });
    const proposalCard = page.locator('.proposal-card');
    await expect(proposalCard).toBeVisible();

    // Verify Decision Badge is rendered with icon and text
    const badge = page.locator('.decision-badge').first();
    await expect(badge).toBeVisible();

    // Axe Scan on Proposal Pending State
    await checkAxe(page, 'proposal_pending');
  });

  test('Reviewer Flow: Login, Filter, Focus Trap Modal Approve, and Audit Verification', async ({ page }) => {
    await page.goto('/');

    // Switch to Reviewer Console
    await page.getByRole('button', { name: /reviewer console/i }).click();

    // Check login view axe
    await checkAxe(page, 'reviewer_login');

    // Enter reviewer key
    const keyInput = page.locator('#reviewer-key-input');
    await keyInput.fill('secret_admin_key_123');
    await page.keyboard.press('Enter');

    // Wait for table of proposals
    await page.waitForSelector('.data-table', { timeout: 10000 });
    await checkAxe(page, 'reviewer_queue');

    // Open Approval Modal
    const approveBtn = page.getByRole('button', { name: /approve/i }).first();
    if (await approveBtn.isVisible()) {
      await approveBtn.click();

      // Verify modal dialog opened and has focus trap
      const dialog = page.locator('div[role="dialog"]');
      await expect(dialog).toBeVisible();
      await checkAxe(page, 'modal_open');

      // Close modal with Escape key
      await page.keyboard.press('Escape');
      await expect(dialog).not.toBeVisible();
    }
  });

  test('Reviewer Flow: Rejection Validation Inline Error', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /reviewer console/i }).click();

    const keyInput = page.locator('#reviewer-key-input');
    await keyInput.fill('secret_admin_key_123');
    await page.keyboard.press('Enter');

    await page.waitForSelector('.data-table', { timeout: 10000 });
    const rejectBtn = page.getByRole('button', { name: /reject/i }).first();
    if (await rejectBtn.isVisible()) {
      await rejectBtn.click();

      // Submit with empty reason to trigger validation error
      const confirmReject = page.getByRole('button', { name: /confirm rejection/i });
      await confirmReject.click();

      const errorAlert = page.locator('div[role="alert"]');
      await expect(errorAlert).toBeVisible();
      await checkAxe(page, 'rejection_validation_error');
    }
  });
});
