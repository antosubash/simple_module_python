import { describe, expect, test } from 'vitest';
import { detail } from '../tenants/components/apiDetail';

describe('detail', () => {
  test('returns a string detail', async () => {
    const response = new Response(JSON.stringify({ detail: 'nope' }), { status: 422 });
    expect(await detail(response)).toBe('nope');
  });

  test('is null for a non-string detail or a non-JSON body', async () => {
    expect(await detail(new Response(JSON.stringify({ detail: [1] })))).toBeNull();
    expect(await detail(new Response('<html>'))).toBeNull();
  });
});
