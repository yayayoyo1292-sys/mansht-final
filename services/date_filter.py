from config.settings import (
    FACEBOOK_START_DATE,
    FACEBOOK_END_DATE
)


def is_within_range(article_date):

    return (
        FACEBOOK_START_DATE <= article_date <= FACEBOOK_END_DATE
    )