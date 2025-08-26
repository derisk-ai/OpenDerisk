/**
 * Find the closest parent element with a specific class name.
 */
export function findParentElementByClassName(element: Element | null, className: string): Element | null {
  if (!element) return null;

  let currentElement: Element | null = element;
  while (currentElement) {
    if (currentElement.classList.contains(className)) {
      return currentElement;
    }
    currentElement = currentElement.parentElement;
  }
  return null;
}
