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

/**
 * Attempts to parse the first valid JSON object from a string that may contain multiple objects or trailing garbage.
 * Useful when LLM outputs concatenated JSON blocks.
 * 关键修复：处理非法转义字符（如 \$）
 */
export function parseFirstJson(str: string): any {
  // 关键修复：预处理非法转义字符
  // JSON 标准不允许 \$ 转义，但某些后端可能错误地生成这种格式
  const sanitizedStr = str.replace(/\\\$/g, '$');
  
  try {
    return JSON.parse(sanitizedStr);
  } catch (e) {
    // If it's a "multiple JSON" error or "trailing garbage" error, 
    // JSON.parse usually throws SyntaxError.
    // We try to find the boundary of the first JSON object.
    
    const startIndex = sanitizedStr.indexOf('{');
    if (startIndex === -1) throw e;

    let braceCount = 0;
    let inString = false;
    let escape = false;

    for (let i = startIndex; i < sanitizedStr.length; i++) {
      const char = sanitizedStr[i];
      
      if (escape) {
        escape = false;
        continue;
      }

      if (char === '\\') {
        escape = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === '{') {
          braceCount++;
        } else if (char === '}') {
          braceCount--;
          if (braceCount === 0) {
            // Found the closing brace of the root object
            const potentialJson = sanitizedStr.substring(startIndex, i + 1);
            try {
              return JSON.parse(potentialJson);
            } catch (innerE) {
              // If extracting by brace counting fails (e.g. malformed internal structure), rethrow original error
              throw e;
            }
          }
        }
      }
    }
    // If we reach here, we didn't find a balanced closing brace
    throw e;
  }
}
