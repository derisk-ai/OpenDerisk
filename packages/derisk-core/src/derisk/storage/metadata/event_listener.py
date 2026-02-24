class DbEventListener:
    """Listener function for the DB event target."""

    @classmethod
    def subscribe(cls) -> str:
        """The given DB event target."""
        raise NotImplemented

    @staticmethod
    def listen(conn, cursor, statement, parameters, context, executemany):
        return statement, parameters
