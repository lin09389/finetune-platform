class Cache:
    def __init__(self) -> None:
        self.values = {}
    def put(self, key: str, value: str) -> None:
        self.values[key] = value
