export function tripErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.';
}