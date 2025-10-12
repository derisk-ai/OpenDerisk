import os

def preprocess_query(raw_query: str) -> str:
    """
        Preprocess the query
    Args:
        raw_query:
    Returns:

    """
    try:
        import jieba
    except ImportError:
        raise ImportError("jieba is not installed")
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    with open(f"{script_dir}/stopwords.txt", 'r', encoding='utf-8') as f:
        stopwords = set([line.strip() for line in f if line.strip()])
        words = jieba.lcut(raw_query, cut_all=False)

    filtered_words = [
        word for word in words
        if word not in stopwords and word.strip()
    ]
    core_query = "".join(filtered_words)
    return core_query if core_query else raw_query