import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Baseline Accessibility Audit', () => {
  test('audit empty state', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page }).analyze();
    console.log('BASELINE_AXE_VIOLATIONS_COUNT:', results.violations.length);
    console.log('BASELINE_AXE_VIOLATIONS:', JSON.stringify(results.violations.map(v => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      nodes: v.nodes.length,
      helpUrl: v.helpUrl
    })), null, 2));
    expect(results.violations.length).toBeGreaterThanOrEqual(0);
  });
});
