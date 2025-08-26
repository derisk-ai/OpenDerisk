"""Client: Simple App CRUD example.

This example demonstrates how to use the derisk client to get, list apps.
Example:
    .. code-block:: python

        DERISK_API_KEY = "derisk"
        client = Client(api_key=DERISK_API_KEY)
        # 1. List all apps
        res = await list_app(client)
        # 2. Get an app
        res = await get_app(client, app_id="ec4a57fc-fc27-11ef-999f-dff8a1307e66")

    uv run examples/client/app_crud_example.py
"""

import asyncio

from derisk_client import Client
from derisk_client.app import list_app


async def main():
    # initialize client
    DERISK_API_KEY = "derisk"
    client = Client(api_key=DERISK_API_KEY)
    res = await list_app(client)
    print(res)


if __name__ == "__main__":
    asyncio.run(main())
