import datetime
from datetime import timedelta


def get_ndays_before(day, ndays=29):
    d_today = datetime.datetime.strptime(day, "%Y-%m-%d")
    date_before = (d_today - timedelta(days=ndays)).strftime("%Y-%m-%d")

    return date_before


def get_ndays_after(day, ndays=1):
    d_today = datetime.datetime.strptime(day, "%Y-%m-%d")
    date_after = (d_today + timedelta(days=ndays)).strftime("%Y-%m-%d")

    return date_after


def get_next_tradeday_after(day, ndays=1):
    return get_next_tradeday(day, ndays, True)


def get_next_tradeday_before(day, ndays=1):
    return get_next_tradeday(day, ndays, False)


def get_next_tradeday(day, ndays=1, after_or_before=True):
    factor = 1 if after_or_before else -1
    d_today = datetime.datetime.strptime(day, "%Y-%m-%d")
    next_day = d_today + factor * timedelta(days=ndays)
    next_n = ndays
    while next_day.weekday() >= 5:
        next_n = next_n + 1
        next_day = d_today + factor * timedelta(days=next_n)

    return next_day.strftime("%Y-%m-%d")


if __name__ == "__main__":
    next_day = get_next_tradeday('2018-08-10', ndays=8, after_or_before=True)
    print(next_day)
