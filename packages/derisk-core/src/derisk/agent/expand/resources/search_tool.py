"""Search tools for the agent."""

import re

from typing_extensions import Annotated, Doc

from ...resource.tool.base import tool


@tool(
    description="Baidu search and return the results as a markdown string. Please set "
    "number of results not less than 8 for rich search results.",
)
def baidu_search(
    query: Annotated[str, Doc("The search query.")],
    num_results: Annotated[int, Doc("The number of search results to return.")] = 8,
) -> str:
    """Baidu search and return the results as a markdown string.

    Please set number of results not less than 8 for rich search results.
    """
    try:
        import requests
    except ImportError:
        raise ImportError(
            "`requests` is required for baidu_search tool, please run "
            "`pip install requests` to install it."
        )
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError(
            "`beautifulsoup4` is required for baidu_search tool, please run "
            "`pip install beautifulsoup4` to install it."
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:112.0) Gecko/20100101 Firefox/112.0",
        "Cookie": """PSTM=1677827588; BAIDUID=A410459655D83837CCD6277C8793D39F:FG=1; BIDUPSID=DA4523422A41D05919A1540DD835F576; BDUSS=Td6UGdPOWJFaWIwTnlqbzRyYndTMW54NVdkQ0IzcmxibVNCa3VJVHl0Nm0wc1ZrSUFBQUFBJCQAAAAAAAAAAAEAAAD-CBYLeWhqdW4xMDI2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKZFnmSmRZ5kL; BDUSS_BFESS=Td6UGdPOWJFaWIwTnlqbzRyYndTMW54NVdkQ0IzcmxibVNCa3VJVHl0Nm0wc1ZrSUFBQUFBJCQAAAAAAAAAAAEAAAD-CBYLeWhqdW4xMDI2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKZFnmSmRZ5kL; MCITY=-75%3A; H_WISE_SIDS=234020_216840_213348_214790_110085_244716_254833_261719_236312_256419_265881_266366_267298_265615_267074_259033_268569_266186_259642_269232_256151_269731_268237_269904_270083_267066_256739_270460_270451_270548_271034_271172_271175_271229_267659_271319_265032_271269_271482_266027_270102_271875_270157_269771_271812_269877_271957_271953_271944_271253_234296_234207_271187_272278_263618_267596_272364_272009_272464_253022_272654_272611_272472_272821_272839_272801_272958_260335_269296_269715_273093_273160_273119_273150_273029_273238_272795_273301_273399_273385_271158_273456_270055_273520_272642_272818_271562_271146_273671_264170_270186_272263_273807_273736_273165_274081_273932_273965_274139_274179_269610_273918_273348_274234_273788_273045_273595_263750_274290_256223_272806_203520_274356_272319_272561; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; H_WISE_SIDS_BFESS=234020_216840_213348_214790_110085_244716_254833_261719_236312_256419_265881_266366_267298_265615_267074_259033_268569_266186_259642_269232_256151_269731_268237_269904_270083_267066_256739_270460_270451_270548_271034_271172_271175_271229_267659_271319_265032_271269_271482_266027_270102_271875_270157_269771_271812_269877_271957_271953_271944_271253_234296_234207_271187_272278_263618_267596_272364_272009_272464_253022_272654_272611_272472_272821_272839_272801_272958_260335_269296_269715_273093_273160_273119_273150_273029_273238_272795_273301_273399_273385_271158_273456_270055_273520_272642_272818_271562_271146_273671_264170_270186_272263_273807_273736_273165_274081_273932_273965_274139_274179_269610_273918_273348_274234_273788_273045_273595_263750_274290_256223_272806_203520_274356_272319_272561; BA_HECTOR=218ga42521agala504000k0n1ifblgv1p; ZFY=RWcEWIlSWNOokGPSHuKGMqUv7mjMGIhDhNz5vTFDibc:C; BAIDUID_BFESS=A410459655D83837CCD6277C8793D39F:FG=1; BDRCVFR[feWj1Vr5u3D]=I67x6TjHwwYf0; delPer=0; BDRCVFR[S4-dAuiWMmn]=I67x6TjHwwYf0; PSINO=7; H_PS_PSSID=39227_39282_39222_39285_39097_39199_39261_39269_39233_26350_39239_39225; ab_sr=1.0.1_YzUzMzJjOGM3MTk0ZGQ5NTM2N2UyZTMyOGE5OTZkYmIzMzVmZDhiZDM0YjcyNjRkNjdiNzQ0MDk3MmUzMDBmNTE3NjdjZWJhZDYxMDFiZDIxZTVmM2FjMjRkODRkYjlkYTAwYWEwMTM2NGVkNmVjZDViMDQwMTM1ZThmMjViZDQ5OWY1MjJmYzBjMmYyNzlmYmU5NmQxNjFhZWUyODAwYQ==; RT="z=1&dm=baidu.com&si=7ba2d0b3-59a6-4cfa-89d7-2444febb8501&ss=lm60oklu&sl=8&tt=2ti&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=o8o&ul=qno&hd=r01"""
    }
    if num_results < 8:
        num_results = 8
    url = f"https://www.baidu.com/s?wd={query}&rn={num_results}"
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    search_results = []
    for result in soup.find_all("div", class_=re.compile("^result c-container ")):
        title = result.find("h3", class_="t").get_text()
        link = result.find("a", href=True)["href"]
        snippet = result.find("span", class_=re.compile("^content-right_"))
        if snippet:
            snippet = snippet.get_text()
        else:
            snippet = ""
        search_results.append({"title": title, "href": link, "snippet": snippet})

    return _search_to_view(search_results)


def _search_to_view(results) -> str:
    view_results = []
    for item in results:
        view_results.append(
            f"### [{item['title']}]({item['href']})\n{item['snippet']}\n"
        )
    return "\n".join(view_results)


