/** The `detail` string of a FastAPI error response, or `null` when it has none. */
export async function detail(response: Response): Promise<string | null> {
  const data = await response.json().catch(() => ({}) as Record<string, unknown>);
  return typeof data.detail === 'string' ? data.detail : null;
}
