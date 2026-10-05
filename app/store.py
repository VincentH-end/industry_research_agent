from collections import OrderedDict

from .schemas import IndustryReport


class ReportStore:
    def __init__(self, max_items: int = 100) -> None:
        self.max_items = max_items
        self._items: OrderedDict[str, IndustryReport] = OrderedDict()
        self._owners: dict[str, str] = {}
        self._traces: dict[str, list[dict]] = {}

    def put(self, report: IndustryReport, owner: str = "anonymous-dev", trace: list[dict] | None = None) -> None:
        self._items[report.report_id] = report
        self._owners[report.report_id] = owner
        self._traces[report.report_id] = trace or []
        self._items.move_to_end(report.report_id)
        while len(self._items) > self.max_items:
            expired, _ = self._items.popitem(last=False)
            self._owners.pop(expired, None)
            self._traces.pop(expired, None)

    def get(self, report_id: str) -> IndustryReport | None:
        return self._items.get(report_id)

    def owned(self, report_id: str, owner: str) -> bool:
        return self._owners.get(report_id) == owner

    def trace(self, report_id: str) -> list[dict]:
        return self._traces.get(report_id, [])
