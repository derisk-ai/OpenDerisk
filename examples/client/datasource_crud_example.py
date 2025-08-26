"""Client: Simple Flow CRUD example

This example demonstrates how to use the derisk client to create, get, update, and
delete  datasource.

Example:
    .. code-block:: python

        DERISK_API_KEY = "derisk"
        client = Client(api_key=DERISK_API_KEY)
        # 1. Create a flow
        res = await create_datasource(
            client,
            DatasourceModel(
                db_name="derisk",
                desc="for client datasource",
                db_type="mysql",
                db_type="mysql",
                db_host="127.0.0.1",
                db_user="root",
                db_pwd="xxxx",
                db_port=3306,
            ),
        )
        # 2. Update a flow
        res = await update_datasource(
            client,
            DatasourceModel(
                db_name="derisk",
                desc="for client datasource",
                db_type="mysql",
                db_type="mysql",
                db_host="127.0.0.1",
                db_user="root",
                db_pwd="xxxx",
                db_port=3306,
            ),
        )
        # 3. Delete a flow
        res = await delete_datasource(client, datasource_id="10")
        # 4. Get a flow
        res = await get_datasource(client, datasource_id="10")
        # 5. List all datasource
        res = await list_datasource(client)

"""

import asyncio

from derisk_client import Client
from derisk_client.datasource import list_datasource


async def main():
    # initialize client
    DERISK_API_KEY = "derisk"
    client = Client(api_key=DERISK_API_KEY)
    res = await list_datasource(client)
    print(res)


if __name__ == "__main__":
    asyncio.run(main())
