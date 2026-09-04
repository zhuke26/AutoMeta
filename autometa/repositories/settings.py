from autometa.persistence.database import Database
from autometa.persistence.models import LocalSetting


class LocalSettingsRepository:
    def __init__(self, database: Database):
        self.database = database

    def get(self, key: str) -> dict | None:
        with self.database.session() as session:
            setting = session.get(LocalSetting, key)
            return dict(setting.value) if setting is not None else None

    def set(self, key: str, value: dict) -> dict:
        with self.database.session() as session:
            setting = session.get(LocalSetting, key)
            if setting is None:
                setting = LocalSetting(key=key, value=dict(value))
                session.add(setting)
            else:
                setting.value = dict(value)
            session.flush()
            return dict(setting.value)
