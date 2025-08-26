/**
 * Utility function to safely parse JSON strings.
 * When parsing fails, it returns a default value or null.
 */
export function safeJsonParse<T>(jsonString: string, def: T): T {
  try {
    return JSON.parse(jsonString);
  } catch (error) {
    console.error('Failed to parse JSON:', error);
    return def;
  }
}
