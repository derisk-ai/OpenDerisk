from datetime import datetime


def is_datetime(value):
    return isinstance(value, datetime)


def convert_datetime_in_row(row):
    return [
        value.strftime("%Y-%m-%d %H:%M:%S") if is_datetime(value) else value
        for value in row
    ]

def convert_datetime(data):
    if isinstance(data, dict):
        return {k: convert_datetime(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_datetime(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    return data


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

    def _parse_str_time(t: str) -> datetime:
        for format in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f','%Y-%m-%d %H:%M:%S']:
            try:
                return datetime.strptime(date_time, format)
            except ValueError:
                pass
        raise ValueError(f"failed to parse time: {t}")


    if not date_time:
        return None

    if isinstance(date_time, datetime):
        return date_time

    # 将字符串格式时间戳转为数值
    try:
        if isinstance(date_time, str):
            date_time = int(date_time)
    except Exception:
        try:
            date_time = float(date_time)
        except Exception:
            pass

    if isinstance(date_time, int):
        return _parse_int_time(date_time)
    elif isinstance(date_time, float):
        return _parse_float_time(date_time)

    return _parse_str_time(date_time)
