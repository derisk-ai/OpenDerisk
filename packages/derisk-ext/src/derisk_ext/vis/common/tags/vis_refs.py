import json

from derisk.vis.base import Vis


class VisRefs(Vis):
    """VisThinking."""

    def sync_display(self, **kwargs) -> str:
        """Display the content using the vis protocol."""
        refs = kwargs.get("content")
        ref_links = []
        url_to_index = {}
        try:
            if refs:
                for ref in refs:
                    for sub_query, candidates in ref.get("references").items():
                        text = ""
                        for i, chunk in enumerate(candidates):
                            yuque_url = (
                                chunk.get("metadata").get("yuque_url")
                                if chunk.get("metadata")
                                else ""
                            )
                            title = (
                                chunk.get("metadata").get("title")
                                if chunk.get("metadata")
                                else ""
                            )
                            if not yuque_url:
                                continue
                            if yuque_url in url_to_index:
                                index = url_to_index[yuque_url]
                            else:
                                index = len(url_to_index) + 1
                                url_to_index[yuque_url] = index
                            # duplicate check in ref_links
                            if not any(
                                link["ref_link"] == yuque_url for link in ref_links
                            ):
                                ref_links.append(
                                    {
                                        "ref_link": yuque_url,
                                        "ref_name": title,
                                        "ref_index": index,
                                    }
                                )
                return f"```{self.vis_tag()}\n{json.dumps(ref_links, ensure_ascii=False)}\n```"
            return str(refs)
        except Exception as e:
            return str(refs)

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "vis-refs"
