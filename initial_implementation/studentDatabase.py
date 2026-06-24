from tinydb import TinyDB, Query
class StudentDatabase:
    def __init__(self, path="student_data.json"):
        self.db = TinyDB(path)
        self.user = Query()

    def add_record(self, name: str, subject: str, scores: list[int]):
        self.db.insert({
            "name": name.strip().title(),
            "subject": subject,
            "scores": scores,
        })

    def get_names(self) -> list[str]:
        return sorted({item["name"] for item in self.db.all()})

    def get_records_for(self, name: str) -> list[dict]:
        return self.db.search(self.user.name == name)

    def has_data(self) -> bool:
        return bool(self.db.all())