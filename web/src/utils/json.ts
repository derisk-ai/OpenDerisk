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
 * 关键修复：处理非法转义字符（如 \$ \= \@ 等）
 */
export function parseFirstJson(str: string): any {
  // 关键修复：预处理非法转义字符
  // JSON 标准只允许: \" \\ \/ \b \f \n \r \t \uXXXX
  // 其他以反斜杠开头的转义都是非法的，需要移除反斜杠
  // 这个正则会匹配 \" \\ \/ \b \f \n \r \t \u 后面跟随的内容，保留这些合法转义
  // 对于其他非法转义，移除反斜杠
  let sanitizedStr = str;
  
  // 临时替换合法转义序列，避免被后续处理破坏
  const validEscapes: { [key: string]: string } = {};
  let placeholderIndex = 0;
  
  // 先保护合法的 Unicode 转义 \uXXXX
  sanitizedStr = sanitizedStr.replace(/\\u[0-9a-fA-F]{4}/g, (match) => {
    const placeholder = `__UNICODE_PLACEHOLDER_${placeholderIndex++}__`;
    validEscapes[placeholder] = match;
    return placeholder;
  });
  
  // 保护其他合法转义: \" \\ \/ \b \f \n \r \t
  const validEscapeChars = ['"', '\\', '/', 'b', 'f', 'n', 'r', 't'];
  validEscapeChars.forEach(char => {
    // 需要为正则表达式正确转义特殊字符
    let escapedChar = char;
    if (char === '"' || char === '\\' || char === '/') {
      escapedChar = '\\' + char;
    }
    const regex = new RegExp(`\\\\${escapedChar}`, 'g');
    sanitizedStr = sanitizedStr.replace(regex, (match) => {
      const placeholder = `__ESCAPE_PLACEHOLDER_${placeholderIndex++}__`;
      validEscapes[placeholder] = match;
      return placeholder;
    });
  });
  
  // 现在处理非法转义：移除反斜杠
  // 匹配反斜杠后跟任何字符（除了已被保护的情况）
  sanitizedStr = sanitizedStr.replace(/\\(.)/g, '$1');
  
  // 恢复合法转义
  Object.keys(validEscapes).forEach(placeholder => {
    sanitizedStr = sanitizedStr.replace(new RegExp(placeholder, 'g'), validEscapes[placeholder]);
  });
  
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
    // If we reach here, we didn't find a balanced closing brace.
    // This likely means the JSON was truncated. Return an empty object
    // instead of throwing, so the component can render gracefully.
    console.warn('[parseFirstJson] JSON appears truncated (unbalanced braces), returning empty object');
    return {};
  }
}
