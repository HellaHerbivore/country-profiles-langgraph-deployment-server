"""
Database models for user testing — query logs and feedback.
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=True)
    user_email = Column(String, nullable=True)
    topic = Column(String, nullable=False)
    max_analysts = Column(Integer, nullable=True)
    thread_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=True)
    user_email = Column(String, nullable=True)
    feedback_type = Column(String, default="general")
    message = Column(Text, nullable=False)
    page_context = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


_engines = {}
_session_factories = {}


def get_engine(db_path="sqlite:///testing_data.db"):
    if db_path not in _engines:
        _engines[db_path] = create_engine(
            db_path, connect_args={"check_same_thread": False}
        )
    return _engines[db_path]


def get_session_factory(db_path="sqlite:///testing_data.db"):
    if db_path not in _session_factories:
        engine = get_engine(db_path)
        _session_factories[db_path] = sessionmaker(bind=engine)
    return _session_factories[db_path]


def create_tables(db_path="sqlite:///testing_data.db"):
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
