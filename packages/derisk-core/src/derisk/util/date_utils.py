from datetime import datetime


def is_datetime(value):
    return isinstance(value, datetime)


def convert_datetime_in_row(row):
    return [
        value.strftime("%Y-%m-%d %H:%M:%S") if is_datetime(value) else value
        for value in row
    ]


def current_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def uniform_time(date_time: datetime | str | int | float) -> datetime:
    """
    将秒时间戳、毫秒时间戳或对应字符串、日期字符串统一转为datetime类型
    精确到秒
    """

    def _parse_int_time(t: int) -> datetime:
        def _parse_int_second(ts: int) -> datetime:
            return datetime.fromtimestamp(ts)

        def _parse_int_millisecond(ms: int) -> datetime:
            return datetime.fromtimestamp(ms / 1000.0)

        return _parse_int_second(t) if t < 99999999999 else _parse_int_millisecond(t)

    def _parse_float_time(t: float) -> datetime:
        return datetime.fromtimestamp(t)

    if not date_time:
        return None

    if isinstance(date_time, datetime):
        return date_time

    # 将字符串格式时间戳转为数值
    try:
        if isinstance(date_time, str):
            date_time = int(date_time)
    except:
        try:
            date_time = float(date_time)
        except:
            pass

    if isinstance(date_time, int):
        return _parse_int_time(date_time)
    elif isinstance(date_time, float):
        return _parse_float_time(date_time)

    try:
        return datetime.strptime(date_time, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
