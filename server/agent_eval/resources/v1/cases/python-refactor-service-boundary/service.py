class UserService:
    def save(self, name: str) -> None:
        normalized = name.strip().lower()
        self.storage.save(normalized)
