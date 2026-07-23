from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.demo_data import seed_demo_data
from app.models import Draft, SourceItem, Topic


def test_demo_seed_creates_expected_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_demo_data(session)
        seed_demo_data(session)

        assert session.scalar(select(func.count(SourceItem.id))) == 3
        assert session.scalar(select(func.count(Topic.id))) == 1
        assert session.scalar(select(func.count(Draft.id))) == 1

