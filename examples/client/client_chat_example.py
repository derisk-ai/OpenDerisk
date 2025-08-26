"""Client: Simple Chat example.

This example demonstrates how to use the derisk client to chat with the chatgpt model.

Example:
    .. code-block:: python

        DERISK_API_KEY = "derisk"
        # chat with stream
        client = Client(api_key=DERISK_API_KEY)

        # 1. chat normal
        async for data in client.chat_stream(
            model="chatgpt_proxyllm",
            messages="hello",
        ):
            print(data.dict())

        # chat with no stream
        res = await client.chat(model="chatgpt_proxyllm", messages="Hello?")
        print(res.json())

        # 2. chat with app
        async for data in client.chat_stream(
            model="chatgpt_proxyllm",
            chat_mode="chat_app",
            chat_param="${app_code}",
            messages="hello",
        ):
            print(data.dict())

        # 3. chat with knowledge
        async for data in client.chat_stream(
            model="chatgpt_proxyllm",
            chat_mode="chat_knowledge",
            chat_param="${space_name}",
            messages="hello",
        ):
            print(data.dict())

        # 4. chat with flow
        async for data in client.chat_stream(
            model="chatgpt_proxyllm",
            chat_mode="chat_flow",
            chat_param="${flow_id}",
            messages="hello",
        ):
            print(data.dict())
"""

import asyncio

from derisk_client import Client


async def main():
    # initialize client
    DERISK_API_KEY = "derisk"
    client = Client(api_key=DERISK_API_KEY)
    data = await client.chat(model="volc-deepseek-v3", messages="hello")
    # async for data in client.chat_stream(
    #     model="chatgpt_proxyllm",
    #     messages="hello",
    # ):
    print(data)

    # res = await client.chat(model="chatgpt_proxyllm" ,messages="hello")
    # print(res)


if __name__ == "__main__":
    asyncio.run(main())
