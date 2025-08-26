import { EditorView } from 'codemirror';

/**
 * 获取光标坐标
 */
export const getCursorPosition = (view: EditorView) => {
  const cursor = view?.state?.selection?.main;
  const coords = view?.coordsAtPos(cursor?.head);
  return coords;
};
/**
 * 获取光标选区
 * @param view
 */
export const getCursorSelection = (view: EditorView) => {
  const selection = view.state.selection.main;
  // 选区之后也需要更新光标位置
  return { from: selection.from, to: selection.to };
};
