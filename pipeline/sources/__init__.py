"""Source modules: each exposes ``fetch() -> list[RawDocument]``.

Sources are the only components that touch the network. They must respect
robots.txt, send an honest User-Agent naming the project and repo URL,
rate-limit to <= 1 request / 2s per host, cache via ETag/Last-Modified, and back
off exponentially on 429/5xx. Official/structured sources take priority over
media; NO social-media scraping.
"""
