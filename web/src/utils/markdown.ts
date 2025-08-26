/**
 * Processes a string to ensure that HTML tags in Markdown are properly formatted.
 */
export function formatMarkdownVal(val: string) {
  return val?.replace(/<table(\w*=[^>]+)>/gi, '<table $1>').replace(/<tr(\w*=[^>]+)>/gi, '<tr $1>');
}
