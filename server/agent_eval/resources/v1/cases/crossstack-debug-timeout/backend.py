async def fetch(client, url):
    return await client.get(url, timeout=None)
