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


def initial_investigation(store, manifest, role):
    """Explicit opt-in for positive recovery fixtures, using authentic tool events."""
    from audit3.config import Config
    from audit3.tools import SourceTools, ToolContext
    phase = 'blind' if role == 'juiz' else 'initial-0000'
    tools = SourceTools(store, manifest, Config.model_validate(store.get(manifest.run_id, 'config')),
                        None, ToolContext(manifest.run_id, role, phase, 'mock-prior-investigation'))
    records = []
    for f in manifest.files:
        if f.category in {'excluded', 'prior_report'} or not f.lines:
            continue
        start = 1
        while start <= f.lines:
            result = tools.read_source(f.path, start, f.lines)
            end = result['lines'][-1]['line']
            records.append(InspectionRecord(refs=[SourceRef(path=f.path, start=start, end=end, sha256=f.sha256)],
                requirement='Synthetic input invariant', analysis='MOCK explicit inspection for recovery fixture',
                flow_verified=False, flow_description='', limitations=[]))
            start = end + 1
    return Opinion(summary='MOCK inspected initial opinion', inspections=records, findings=[], positions=[], limitations=[])
