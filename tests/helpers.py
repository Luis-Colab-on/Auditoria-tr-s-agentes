from audit3.schemas import InspectionRecord, Judgment, Opinion, SourceRef


class MockRuntime:
    """Explicit deterministic mock: never counts as a real agent/API validation."""
    mode = "mock"

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler

    async def invoke(self, role, phase, payload, tools, final=False):
        self.calls.append({"role": role, "phase": phase, "payload": payload, "context": tools.context})
        if self.handler:
            special = await self.handler(role, phase, payload, tools, final)
            if special is not None:
                return special
        records = []
        for f in tools.manifest.files:
            if f.category in {"excluded", "prior_report"} or f.lines == 0:
                continue
            cursor = 1
            while cursor <= f.lines:
                result = tools.read_source(f.path, cursor, f.lines)
                if not result["lines"]:
                    break
                end = result["lines"][-1]["line"]
                records.append(InspectionRecord(refs=[SourceRef(path=f.path, start=cursor, end=end, sha256=f.sha256)], requirement="synthetic invariant",
                    analysis="MOCK: control-flow fixture; no semantic AI analysis", flow_verified=False, flow_description="", limitations=[]))
                cursor = end + 1
        if final:
            return Judgment(summary="MOCK: no findings", verdicts=[], new_findings=[], limitations=[])
        return Opinion(summary="MOCK infrastructure exercise", inspections=records, findings=[], positions=[], limitations=[])
