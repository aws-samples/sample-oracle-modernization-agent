import { test, expect } from '@playwright/test';

test.describe('Dashboard Pages', () => {

  test('Overview page loads', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h2')).toHaveText('Pipeline Overview');
    await expect(page.locator('text=Total SQL')).toBeVisible();
    await expect(page.locator('text=Pass Rate')).toBeVisible();
    await expect(page.locator('text=Failed')).toBeVisible();
    await expect(page.locator('text=Skipped')).toBeVisible();
  });

  test('Overview shows pipeline progress chart', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=Pipeline Progress')).toBeVisible();
    await expect(page.locator('text=Step Counts')).toBeVisible();
  });

  test('SQL Explorer page loads with table', async ({ page }) => {
    await page.goto('/sql');
    await expect(page.locator('h2')).toHaveText('SQL Explorer');
    await expect(page.locator('input[placeholder*="Search"]')).toBeVisible();
    await expect(page.locator('select')).toHaveCount(2);
  });

  test('SQL Explorer filter controls work', async ({ page }) => {
    await page.goto('/sql');
    const searchInput = page.locator('input[placeholder*="Search"]');
    await searchInput.fill('select');
    await expect(searchInput).toHaveValue('select');

    const stepSelect = page.locator('select').first();
    await stepSelect.selectOption('transform');
    await expect(stepSelect).toHaveValue('transform');
  });

  test('FAIL Analysis page loads', async ({ page }) => {
    await page.goto('/analysis');
    await expect(page.locator('h2')).toHaveText('FAIL Analysis');
  });

  test('Run History page loads', async ({ page }) => {
    await page.goto('/runs');
    await expect(page.locator('h2')).toHaveText('Run History');
    await expect(page.locator('text=Recent Runs')).toBeVisible();
  });

  test('Pipeline Control page loads with step buttons', async ({ page }) => {
    await page.goto('/control');
    await expect(page.locator('h2')).toHaveText('Pipeline Control');
    await expect(page.locator('text=Source Analysis')).toBeVisible();
    await expect(page.locator('text=SQL Transform')).toBeVisible();
    await expect(page.locator('text=Mapper Merge')).toBeVisible();
    await expect(page.locator('text=DB Execution Test')).toBeVisible();
    await expect(page.locator('text=Run Full Pipeline')).toBeVisible();
  });

  test('Settings page loads', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('h2')).toHaveText('Settings');
    await expect(page.locator('text=Configuration')).toBeVisible();
  });

  test('Navigation sidebar has all links', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toHaveText('OMA Dashboard');
    const nav = page.locator('nav');
    await expect(nav.locator('text=Overview')).toBeVisible();
    await expect(nav.locator('text=SQL Explorer')).toBeVisible();
    await expect(nav.locator('text=FAIL Analysis')).toBeVisible();
    await expect(nav.locator('text=Run History')).toBeVisible();
    await expect(nav.locator('text=Pipeline')).toBeVisible();
    await expect(nav.locator('text=Settings')).toBeVisible();
  });

  test('Navigation works between pages', async ({ page }) => {
    await page.goto('/');
    await page.locator('nav >> text=SQL Explorer').click();
    await expect(page).toHaveURL('/sql');
    await expect(page.locator('h2')).toHaveText('SQL Explorer');

    await page.locator('nav >> text=Pipeline').click();
    await expect(page).toHaveURL('/control');
    await expect(page.locator('h2')).toHaveText('Pipeline Control');
  });
});

test.describe('API Endpoints', () => {

  test('GET /api/pipeline/status returns valid JSON', async ({ request }) => {
    const res = await request.get('/api/pipeline/status');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('steps');
    expect(data).toHaveProperty('totals');
    expect(Array.isArray(data.steps)).toBeTruthy();
    expect(data.totals).toHaveProperty('total');
    expect(data.totals).toHaveProperty('passRate');
  });

  test('GET /api/sql returns valid JSON with pagination', async ({ request }) => {
    const res = await request.get('/api/sql');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('total');
    expect(data).toHaveProperty('limit');
    expect(data).toHaveProperty('offset');
    expect(data).toHaveProperty('data');
    expect(Array.isArray(data.data)).toBeTruthy();
  });

  test('GET /api/sql with filters returns valid JSON', async ({ request }) => {
    const res = await request.get('/api/sql?step=transform&status=PASS&search=select&limit=10');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('data');
    expect(Array.isArray(data.data)).toBeTruthy();
  });

  test('GET /api/pipeline/run returns running status', async ({ request }) => {
    const res = await request.get('/api/pipeline/run');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('running');
  });
});
