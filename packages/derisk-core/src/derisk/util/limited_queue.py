class LimitedQueue:
    def __init__(self, capacity: int):
        self._list = []
        self._next_idx = 0
        self._capacity = capacity

    def put(self, item) -> "LimitedQueue":
        if len(self._list) < self._capacity:
            self._list.append(item)
            return self

        self._list[self._next_idx] = item
        self._next_idx = (self._next_idx + 1) % self._capacity
        return self

    def get(self) -> list:
        return (
            self._list
            if self._next_idx == 0
            else self._list[self._next_idx :] + self._list[: self._next_idx]
        )
