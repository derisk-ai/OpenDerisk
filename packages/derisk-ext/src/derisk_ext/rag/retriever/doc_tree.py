"""Tree-based document retriever."""

import logging
import re
import uuid
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Optional, List, Tuple

from rapidfuzz import fuzz

from derisk.core import Chunk, Document
from derisk.rag.retriever import BaseRetriever, QueryRewrite, Ranker, DefaultRanker
from derisk.rag.transformer.base import ExtractorBase
from derisk.storage.vector_store.filters import MetadataFilters

logger = logging.getLogger(__name__)

RETRIEVER_NAME = "doc_tree_retriever"
TITLE = "title"
HEADER1 = "Header1"
HEADER2 = "Header2"
HEADER3 = "Header3"
HEADER4 = "Header4"
HEADER5 = "Header5"
HEADER6 = "Header6"
class TreeNode:
    """TreeNode class to represent a node in the document tree."""

    def __init__(self,
                 node_id: str,
                 title: str,
                 level: int,
                 body_content: str = "",
                 content: str = ""
                 ):
        """
        Initialize a TreeNode.

        Args:
            node_id (str): A unique identifier for the node.
            title (str): The text content of the header itself (e.g., "Chapter One").
            level (int): The header level (1 for H1, 2 for H2, etc.).
            body_content (str): The text content belonging to this header,
                                 up until the next header of the same or higher level.
        """
        self.node_id = node_id
        self.title = title
        self.level = level
        self.body_content = body_content
        self.content = content
        self.children = []
        self.retriever = RETRIEVER_NAME

    def add_child(self, child_node):
        """Add a child node to the current node."""
        self.children.append(child_node)

    def to_dict(self):
        """
        Converts the TreeNode and its children into a dictionary representation.
        Useful for serialization or debugging.
        """
        return {
            "node_id": self.node_id,
            "title": self.title,
            "level": self.level,
            "body_content": self.body_content,
            "retriever": self.retriever,
            "children": [child.to_dict() for child in self.children]
        }

    def __repr__(self):
        """String representation for debugging."""
        # Truncate body_content for cleaner repr
        body_snippet = self.body_content[:50].replace('\n', ' ') + '...' if len(self.body_content) > 50 else self.body_content.replace('\n', ' ')
        return f"TreeNode(id={self.node_id}, level={self.level}, title='{self.title}', body_snippet='{body_snippet}')"


# class TreeNode:
#     """TreeNode class to represent a node in the document tree."""
#
#     def __init__(self, node_id: str, content: str, level: int):
#         """Initialize a TreeNode."""
#         self.node_id = node_id
#         self.content = content
#         self.level = level  # 0: title, 1: header1, 2: header2, 3: header3
#         self.children = []
#         self.retriever = RETRIEVER_NAME
#
#     def add_child(self, child_node):
#         """Add a child node to the current node."""
#         self.children.append(child_node)


class DocTreeIndex:
    def __init__(self):
        """Initialize the document tree index."""
        self.root = TreeNode("root_id", "Root", -1)

    def add_nodes(
        self,
        node_id: str,
        title: str,
        header1: Optional[str] = None,
        header2: Optional[str] = None,
        header3: Optional[str] = None,
        header4: Optional[str] = None,
        header5: Optional[str] = None,
        header6: Optional[str] = None,
    ):
        """Add nodes to the document tree.

        Args:
            node_id (str): The ID of the node.
            title (str): The title of the document.
            header1 (Optional[str]): The first header.
            header2 (Optional[str]): The second header.
            header3 (Optional[str]): The third header.
            header4 (Optional[str]): The fourth header.
            header5 (Optional[str]): The fifth header.
            header6 (Optional[str]): The sixth header.
        """
        # Assuming titles is a dictionary containing title and headers
        title_node = None
        if title:
            title_nodes = self.get_node_by_level(0)
            if not title_nodes:
                # If title already exists, do not add it again
                title_node = TreeNode(node_id, title, 0)
                self.root.add_child(title_node)
            else:
                title_node = title_nodes[0]
        current_node = title_node
        headers = [header1, header2, header3, header4, header5, header6]
        for level, header in enumerate(headers, start=1):
            if header:
                new_header_node = TreeNode(node_id, header, level)
                current_node.add_child(new_header_node)
                current_node = new_header_node

    def get_node_by_level(self, level):
        """Get nodes by level."""
        # Traverse the tree to find nodes at the specified level
        result = []
        self._traverse(self.root, level, result)
        return result

    def get_all_children(self, node):
        """get all children of the node."""
        # Get all children of the current node
        result = []
        self._traverse(node, node.level, result)
        return result

    def display_tree(self, node: TreeNode, prefix: Optional[str] = ""):
        """Recursive function to display the directory structure with visual cues."""
        # Print the current node title with prefix
        if node.content:
            print(
                f"{prefix}├── {node.content} (node_id: {node.node_id}) "
                f"(content: {node.content})"
            )
            logger.info(
                f"{prefix}├── {node.content} (node_id: {node.node_id}) "
                f"(content: {node.content})"
            )
        else:
            print(f"{prefix}├── {node.content} (node_id: {node.node_id})")
            logger.info(f"{prefix}├── {node.content} (node_id: {node.node_id})")

        # Update prefix for children
        new_prefix = prefix + "│   "  # Extend the prefix for child nodes
        for i, child in enumerate(node.children):
            if i == len(node.children) - 1:  # If it's the last child
                new_prefix_child = prefix + "└── "
            else:
                new_prefix_child = new_prefix

            # Recursive call for the next child node
            self.display_tree(child, new_prefix_child)

    def _traverse(self, node, level, result):
        """Traverse the tree to find nodes at the specified level."""
        # If the current node's level matches the specified level, add it to the result
        if node.level == level:
            result.append(node)
        for child in node.children:
            self._traverse(child, level, result)

    def search_keywords(self, node, keyword) -> Optional[TreeNode]:
        # Check if the keyword matches the current node title
        if keyword.lower() == node.content.lower():
            logger.info(f"DocTreeIndex Match found in: {node.content}")
            return node
        # Recursively search in child nodes
        for child in node.children:
            result = self.search_keywords(child, keyword)
            if result:
                logger.info(
                    f"DocTreeIndex Match found when searching "
                    f"for {keyword} in {node.content} "
                )
                return result
        # Check if the keyword matches any of the child nodes
        # If no match, continue to search in all children
        return None


class DocTreeRetriever(BaseRetriever):
    """Doc Tree retriever."""

    def __init__(
        self,
        docs: List[Document] = None,
        top_k: Optional[int] = 10,
        query_rewrite: Optional[QueryRewrite] = None,
        rerank: Optional[Ranker] = None,
        keywords_extractor: Optional[ExtractorBase] = None,
        show_tree: Optional[bool] = True,
        executor: Optional[Executor] = None,
    ):
        """Create DocTreeRetriever.

        Args:
            docs (List[Document]): List of documents to initialize the tree with.
            top_k (int): top k
            query_rewrite (Optional[QueryRewrite]): query rewrite
            rerank (Ranker): rerank
            keywords_extractor (Optional[ExtractorBase]): keywords extractor
            executor (Optional[Executor]): executor

        Returns:
            DocTreeRetriever: DocTree retriever
        """
        super().__init__()
        self._top_k = top_k
        self._query_rewrite = query_rewrite
        self._show_tree = show_tree
        self._rerank = rerank or DefaultRanker(self._top_k)
        self._keywords_extractor = keywords_extractor

        self._tree_indexes = self._initialize_doc_tree(docs)
        self._executor = executor or ThreadPoolExecutor()

    def _retrieve(
        self, query: str, filters: Optional[MetadataFilters] = None
    ) -> List[TreeNode]:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text
            filters: metadata filters.
        Return:
            List[Chunk]: list of chunks
        """
        raise NotImplementedError("DocTreeRetriever does not support retrieval.")

    def _retrieve_with_score(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
    ) -> List[TreeNode]:
        """Retrieve knowledge chunks with score.

        Args:
            query (str): query text
            score_threshold (float): score threshold
            filters: metadata filters.
        Return:
            List[Chunk]: list of chunks with score
        """
        raise NotImplementedError("DocTreeRetriever does not support score retrieval.")

    async def _aretrieve(
        self, query: str, filters: Optional[MetadataFilters] = None
    ) -> List[TreeNode]:
        """Retrieve knowledge chunks.

        Args:
            query (str): query text.
            filters: metadata filters.
        Return:
            List[Chunk]: list of chunks
        """
        keywords = [query]
        if self._keywords_extractor:
            keywords = await self._keywords_extractor.extract(query)
        logger.info(f"DocTreeRetriever aretrieve, query:{query} keywords: {keywords}")
        all_nodes = []
        for keyword in keywords:
            for tree_index in self._tree_indexes:
                retrieve_node = tree_index.search_keywords(tree_index.root, keyword)
                if retrieve_node:
                    # If a match is found, return the corresponding chunks
                    if self._show_tree:
                        tree_index.display_tree(tree_index.root)
                    all_nodes.append(retrieve_node)
        logger.info(f"DocTreeRetriever retrieve:{len(all_nodes)} nodes.")
        self._tree_indexes.clear()
        return all_nodes

    async def _aretrieve_with_score(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilters] = None,
    ) -> List[TreeNode]:
        """Retrieve knowledge chunks with score.

        Args:
            query (str): query text
            score_threshold (float): score threshold
            filters: metadata filters.
        Return:
            List[Chunk]: list of chunks with score
        """
        return await self._aretrieve(query, filters)

    def _initialize_doc_tree(self, docs: List[Document]):
        """Initialize the document tree with docs.

        Args:
            docs (List[Document]): List of docs to initialize the tree with.
        """
        tree_indexes = []
        for doc in docs:
            tree_index = DocTreeIndex()
            for chunk in doc.chunks:
                if not chunk.metadata.get(TITLE):
                    continue
                tree_index.add_nodes(
                    node_id=chunk.chunk_id,
                    title=chunk.metadata[TITLE],
                    header1=chunk.metadata.get(HEADER1),
                    header2=chunk.metadata.get(HEADER2),
                    header3=chunk.metadata.get(HEADER3),
                    header4=chunk.metadata.get(HEADER4),
                    header5=chunk.metadata.get(HEADER5),
                    header6=chunk.metadata.get(HEADER6),
                )
            tree_indexes.append(tree_index)
        return tree_indexes


class DocumentOutlineParser:
    """
    Parses a Markdown-like body string to extract document outlines
    as a tree of TreeNode objects, including the section content.
    """

    def __init__(self, retriever_name: str = "document_outline_retriever"):
        """
        Initializes the parser.

        Args:
            retriever_name (str): The name of the retriever to associate with TreeNodes.
        """
        global RETRIEVER_NAME # Update the global constant if needed
        RETRIEVER_NAME = retriever_name
        # Using uuid for more robust unique IDs across runs/multiple documents
        # self._node_id_counter = 0 # No longer needed if using uuid

    # def _get_next_node_id(self) -> str:
    #     """Generates a unique ID for a new TreeNode."""
    #     self._node_id_counter += 1
    #     return f"node_{self._node_id_counter}"

    def _clean_html_tags(self, text: str) -> str:
        """Removes HTML tags from a given string."""
        return re.sub(r'<.*?>', '', text)

    def find_similar_header_node(self, outlines: List[TreeNode], header: str,
                                 threshold: int = 40) -> Tuple[TreeNode | None, str]:
        """
        Finds the most similar TreeNode based on its header title within the given outlines.
        Returns the matched TreeNode and a concatenated string of its body_content
        along with all its descendant's body_content.

        Args:
            outlines (list[TreeNode]): The list of top-level TreeNode objects
                                       (e.g., as returned by get_outlines_from_body).
            header (str): The target header name to search for.
            threshold (int): The minimum similarity score (0-100) for a match to be considered valid.
                             Default is 70.

        Returns:
            tuple[TreeNode | None, str]: A tuple containing:
                - The most similar TreeNode (or None if no match above threshold).
                - A string containing the body_content of the matched node and all its
                  descendant nodes, separated by double newlines. Returns an empty string
                  if no node is found.
        """
        try:
            best_match_info = {
                'best_match_node': None,
                'highest_score': -1
            }

            # Create a dummy root to facilitate traversal if outlines can be empty or have multiple roots
            # Or, simply iterate through the top-level outlines
            for root_node in outlines:
                self._traverse_and_search_for_similar(root_node, header, threshold,
                                                      best_match_info)

            matched_node = best_match_info['best_match_node']

            if matched_node:
                # Collect content from the matched node and all its descendants
                combined_content = self._collect_descendant_body_content(matched_node)
                return matched_node, combined_content
            else:
                return None, ""
        except Exception as e:
            logger.error(f"find_similar_header_node error: {str(e)}")
            return None, ""

    def _collect_descendant_body_content(self, node: TreeNode) -> str:
        """
        Recursively collects the body_content from the given node and all its children.
        """
        all_content_parts = [node.body_content]  # Start with current node's content

        for child in node.children:
            all_content_parts.append(
                self._collect_descendant_body_content(child))  # Recursive call

        # Join content, filtering out empty strings and separating with double newlines
        return "\n\n".join(filter(None, all_content_parts)).strip()

    def _traverse_and_search_for_similar(self,
                                         current_node: TreeNode,
                                         target_header: str,
                                         threshold: int,
                                         best_match_info: dict):
        """
        Helper method to recursively traverse the tree and find the most similar header.
        best_match_info is a dictionary passed by reference to update results.
        """
        # Use token_sort_ratio for better fuzzy matching with titles (handles word order)
        # Convert both to lower case for case-insensitive matching
        score = fuzz.token_sort_ratio(target_header.lower(), current_node.title.lower())

        if score > best_match_info['highest_score'] and score >= threshold:
            best_match_info['highest_score'] = score
            best_match_info['best_match_node'] = current_node

        for child in current_node.children:
            self._traverse_and_search_for_similar(child, target_header, threshold,
                                                  best_match_info)

    def display(self, outlines: List[TreeNode]) -> str:
        """
        Generates a string representation of the TreeNode hierarchy,
        similar to a file tree.

        Args:
            outlines (List[TreeNode]): The list of top-level TreeNode objects
                                       (e.g., as returned by get_outlines_from_body).

        Returns:
            str: A formatted string representing the tree structure.
        """
        output_lines = []

        def _display_recursive(node: TreeNode, prefix: str = "",
                               is_last_child: bool = False):
            """
            Recursive helper to build the display string.

            Args:
                node (TreeNode): The current node to display.
                prefix (str): The prefix string for the current line,
                              carrying indentation and vertical lines from parents.
                is_last_child (bool): True if the current node is the last child of its parent.
            """
            # Determine the connector for the current node
            connector = "└── " if is_last_child else "├── "
            output_lines.append(
                f"{prefix}{connector}{node.title} (content: {node.body_content})")

            # If current node is the last child, its children won't have a vertical line extending from its parent's branch.
            # Otherwise, the vertical line continues down.
            child_prefix = prefix + ("    " if is_last_child else "│   ")

            # Recursively call for children
            for i, child in enumerate(node.children):
                _display_recursive(child, child_prefix, i == len(node.children) - 1)

        # Iterate through the top-level nodes
        for i, root_node in enumerate(outlines):
            is_last_root = (i == len(outlines) - 1)
            _display_recursive(root_node, "", is_last_root)

        return "\n".join(output_lines)

    def get_outlines_from_body(self, body: str) -> List[TreeNode]:
        """
        Parses the input body string and returns a list of top-level TreeNode objects
        representing the document's outline hierarchy, including section content.

        Args:
            body (str): The input text body, potentially containing Markdown headers.

        Returns:
            List[TreeNode]: A list of TreeNode objects, where each object
                            represents a top-level header (e.g., H1) and
                            contains its sub-headers as children.
        """
        try:
            code_block_regex = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
            code_block_spans = []
            for match in code_block_regex.finditer(body):
                code_block_spans.append(match.span())

            def is_inside_code_block(index):
                for cb_start, cb_end in code_block_spans:
                    if cb_start <= index < cb_end:
                        return True
                return False

            header_regex = re.compile(r"^(#+)\s+(.*)", re.MULTILINE)
            valid_header_matches = []
            for match_obj in header_regex.finditer(body):
                if not is_inside_code_block(match_obj.start()):
                    valid_header_matches.append(match_obj)

            dummy_root = TreeNode(node_id=str(uuid.uuid4()), title="Document Root",
                                  level=0)
            node_stack: List[Tuple[TreeNode, int]] = [(dummy_root, 0)]

            for i, match_obj in enumerate(valid_header_matches):
                level_symbols = match_obj.group(1)
                title_text = match_obj.group(2)
                current_level = len(level_symbols)

                content_start_index = match_obj.end()

                if i + 1 < len(valid_header_matches):
                    content_end_index = valid_header_matches[i + 1].start()
                else:
                    # 到原始文档的末尾
                    content_end_index = len(body)

                raw_section_content = body[
                                      content_start_index:content_end_index].strip()

                cleaned_section_content = self._clean_html_tags(raw_section_content)

                cleaned_title = self._clean_html_tags(title_text.strip())
                # 存储清理HTML标签后的内容，保留代码块
                new_node = TreeNode(
                    node_id=str(uuid.uuid4()),
                    title=cleaned_title,
                    level=current_level,
                    body_content=cleaned_section_content
                )

                while node_stack and node_stack[-1][1] >= current_level:
                    node_stack.pop()

                parent_node, _ = node_stack[-1]
                parent_node.add_child(new_node)

                node_stack.append((new_node, current_level))

            return dummy_root.children

        except Exception as e:
            logger.error(f"get_outlines_from_body error: {str(e)}")
            return []
        



