import { expect, test } from '@playwright/test';

import { installMockApi } from './fixtures';

test('direct statutory lookup preserves answer and citation action', async ({ page }) => {
  await installMockApi(page, 'direct');
  await page.goto('/');

  await page.getByPlaceholder('Nhập câu hỏi về Bộ luật Lao động…').fill('Điều 35 quy định gì?');
  await page.getByRole('button', { name: 'Gửi' }).click();

  await expect(page.getByText('Tra cứu điều luật')).toBeVisible();
  await expect(page.getByText('Người lao động phải báo trước.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Xem căn cứ pháp lý' })).toBeVisible();
});

test('Case Analysis displays bounded clarification state', async ({ page }) => {
  await installMockApi(page, 'clarification');
  await page.goto('/');

  await page
    .getByPlaceholder('Nhập câu hỏi về Bộ luật Lao động…')
    .fill('Phân tích hợp đồng của tôi.');
  await page.getByRole('button', { name: 'Gửi' }).click();

  await expect(page.getByText('Phân tích tình huống', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Thông tin còn thiếu' })).toBeVisible();
  await expect(page.getByText('Loại hợp đồng')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Câu hỏi cần làm rõ' })).toBeVisible();
});

test('public error copy never exposes provider details', async ({ page }) => {
  await installMockApi(page, 'error');
  await page.goto('/');

  await page
    .getByPlaceholder('Nhập câu hỏi về Bộ luật Lao động…')
    .fill('Phân tích lỗi an toàn.');
  await page.getByRole('button', { name: 'Gửi' }).click();

  await expect(page.getByRole('alert')).toContainText('Không thể xử lý yêu cầu');
  await expect(page.locator('body')).not.toContainText('provider-secret');
});
