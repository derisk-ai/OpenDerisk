# -*- coding: utf-8 -*-
"""
Project : derisk
File Name : index_construction.py
Create Time : 2025/4/21 11:49 AM
Author : yangrong.wj
Email: yangrong.wj@antgroup.com
"""

import json
import requests
import logging

logger = logging.getLogger("derisk_ext.storage.full_text.index_construction")

account = "xx_kb_8l"
secret = "Mfxx"

endpoint = "http://zsearch-et2.alipay.com:9999"
zsearch_config = {"account": account, "secret": secret, "endpoint": endpoint}


def search_collection(data):
    request = requests.session()
    request.auth = (zsearch_config["account"], zsearch_config["secret"])
    index_name = "goc_product_line"
    primary_key = 7
    url = f"http://zsearch-et2.alipay.com:9999/{index_name}/_doc/{primary_key}"
    print(url)
    headers = {"Content-Type": "application/json"}

    response = request.post(url, headers=headers, json=data)
    print(response)


if __name__ == "__main__":
    # todo: 单库单表python，是为了 查询ob数据，往索引里插入数据

    data = {
        "goc_product_line": "随便测试一下",
        "keywords": "测试，test,lalla，阿拉啦啦",
        "history_fault_info": "哈哈哈哈哈",
        "faq": "随便噶公告",
        "product_info": "哈哈哈吧",
    }
    search_collection(data)
