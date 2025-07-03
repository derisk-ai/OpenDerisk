import uuid
import json
import requests 

from ..resource.evaluate_resource import get_eval_datasets

def call_chat_completions(query):
    url = "http://127.0.0.1:7777/api/v1/chat/completions"  
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer your_secret_key",  
    }
        
    # 构造请求体
    payload = {
        "chat_mode": "chat_agent",  # 替换为实际的 chat_mode
        "conv_uid": str(uuid.uuid4()),  # 会话唯一 ID
        "user_name": "test_user",  # 用户名
        "sys_code": "test_system",  # 系统代码
        "user_input": query,  # 用户输入
        "model_name": "deepseek-r1",  # 模型名称
        "app_code": "ai_sre",  # 应用代码
        "ext_info": {
            "trace_id": str(uuid.uuid4()),
            "rpc_id": "0.1",
            "incremental": False,
            "temperature": 0.5,
        },
        "temperature": 0.5,
        "max_new_tokens": 8192,
        "prompt_code": "default_prompt",
    }

    count = 0
    while count < 3:
        try:
            # 发送 POST 请求
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            # 检查响应状态码
            if response.status_code == 200:
                print("Response:", response.json())
                break
            else:
                print(f"Failed with status code {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Error occurred: {e}")
            count += 1

if __name__ == "__main__":
    
    input_path = "datasets/Telecom/query.csv"
    datasets = get_eval_datasets(input_path)

    for d in datasets:
        print(f"Query: {d['query']}, Answer: {d['answer']}, Task Index: {d['task_index']}")
        query = d["query"]
        call_chat_completions(query)