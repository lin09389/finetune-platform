def read_text(path: str) -> str:
    handle = open(path)
    return handle.read()
