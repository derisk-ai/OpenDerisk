import logging

import requests

logger = logging.getLogger(__name__)


def get_oss_url(original_url):
    """
    Get the final URL after following redirects.
    Args:
        original_url:
    Returns:
        Final URL after redirects or "None" if the request fails.
    """
    response = ""
    logger.info(f"get original oss url {original_url}")

    try:
        response = requests.get(original_url, verify=False, allow_redirects=True)
        if response.status_code == 200:
            return response.url
        else:
            logger.error(f"{response.status_code}")
            return "None"
    except Exception as e:
        logger.error(f"get oss url{original_url} error {e}, {response}")
        return None