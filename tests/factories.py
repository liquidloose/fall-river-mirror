"""
Factory classes for generating test data using factory_boy.
"""

import factory
from datetime import datetime
from app.data.data_classes import Committee, AIAgent, ArticleType, Tone, Journalist


class TranscriptFactory(factory.Factory):
    """Factory for creating test transcript data."""

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n)
    committee = factory.Iterator([c.value for c in Committee])
    title = factory.Sequence(lambda n: f"Test Meeting {n}")
    content = factory.Faker("text", max_nb_chars=500)
    date = factory.LazyFunction(datetime.now)
    category = factory.Iterator([a.value for a in AIAgent])
    video_id = factory.Sequence(lambda n: f"TEST{n:06d}")


class ArticleRequestFactory(factory.Factory):
    """Factory for creating test article request data."""

    class Meta:
        model = dict

    context = factory.Faker("text", max_nb_chars=200)
    prompt = factory.Faker("sentence", nb_words=10)
    article_type = factory.Iterator([t.value for t in ArticleType])
    tone = factory.Iterator([t.value for t in Tone])
    committee = factory.Iterator([c.value for c in Committee])


class ArticleFactory(factory.Factory):
    """Factory for creating test article data."""

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n)
    title = factory.Faker("sentence", nb_words=6)
    content = factory.Faker("text", max_nb_chars=1000)
    author = factory.Iterator([j.value for j in Journalist])
    created_at = factory.LazyFunction(datetime.now)
    committee = factory.Iterator([c.value for c in Committee])
    article_type = factory.Iterator([t.value for t in ArticleType])
    tone = factory.Iterator([t.value for t in Tone])


class YouTubeVideoFactory(factory.Factory):
    """Factory for creating test YouTube video data."""

    class Meta:
        model = dict

    video_id = factory.Sequence(lambda n: f"dQw4w9WgXc{n}")
    title = factory.Faker("sentence", nb_words=8)
    description = factory.Faker("text", max_nb_chars=300)
    duration = factory.Faker("random_int", min=60, max=3600)
    upload_date = factory.Faker("date_this_year")
    view_count = factory.Faker("random_int", min=100, max=1000000)
