"""Offline invocation audit Adapter shared by application contract tests."""


class NoAuditFactory:
    def usage_snapshot(self) -> tuple[str, dict[str, int | None]] | None:
        return None

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        pass
