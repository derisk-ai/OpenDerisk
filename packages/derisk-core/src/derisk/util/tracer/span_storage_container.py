import datetime
import logging
import queue
import threading
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import List

from derisk.component import SystemApp, ComponentType
from derisk.util.tracer.base import Span, SpanStorage

logger = logging.getLogger(__name__)


class SpanStorageContainer(SpanStorage):
    name = ComponentType.TRACER_SPAN_STORAGE.value

    def __init__(
        self,
        system_app: SystemApp | None = None,
        batch_size=10,
        flush_interval=10,
        executor: Executor = None,
    ):
        super().__init__(system_app)
        if not executor:
            executor = ThreadPoolExecutor(thread_name_prefix="trace_storage_sync_")
        self.executor = executor
        self.storages: List[SpanStorage] = []
        self.last_date = (
            datetime.datetime.now().date()
        )  # Store the current date for checking date changes
        self.queue = queue.Queue()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.last_flush_time = time.time()
        self.flush_signal_queue = queue.Queue()
        self.flush_thread = threading.Thread(
            target=self._flush_to_storages, daemon=True
        )
        self._stop_event = threading.Event()
        self.flush_thread.start()
        self._stop_event.clear()

    def append_storage(self, storage: SpanStorage):
        """Append sotrage to container

        Args:
            storage ([`SpanStorage`]): The storage to be append to current container
        """
        self.storages.append(storage)

    def append_span(self, span: Span):
        self.queue.put(span)
        if self.queue.qsize() >= self.batch_size:
            try:
                self.flush_signal_queue.put_nowait(True)
            except queue.Full:
                pass  # If the signal queue is full, it's okay. The flush thread will
                # handle it.

    def _flush_to_storages(self):
        while not self._stop_event.is_set():
            interval = time.time() - self.last_flush_time
            if interval < self.flush_interval:
                try:
                    self.flush_signal_queue.get(
                        block=True, timeout=self.flush_interval - interval
                    )
                except Exception:
                    # Timeout
                    pass

            spans_to_write = []
            while not self.queue.empty():
                spans_to_write.append(self.queue.get())
            for s in self.storages:

                def append_and_ignore_error(
                    storage: SpanStorage, spans_to_write: List[SpanStorage]
                ):
                    try:
                        storage.append_span_batch(spans_to_write)
                    except Exception as e:
                        logger.exception(
                            f"Append spans to storage {str(storage)} failed: {str(e)},"
                            f" span_data: {spans_to_write}"
                        )

                try:
                    self.executor.submit(append_and_ignore_error, s, spans_to_write)
                except RuntimeError:
                    append_and_ignore_error(s, spans_to_write)
            self.last_flush_time = time.time()

    def before_stop(self):
        try:
            self.flush_signal_queue.put(True)
            self._stop_event.set()
            self.flush_thread.join()
        except Exception:
            pass
