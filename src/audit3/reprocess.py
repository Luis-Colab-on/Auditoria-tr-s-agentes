"""Read-only reprocessing of one original completed response at a time."""
import copy
from pathlib import Path
from .evidence import Store
from .schemas import Judgment
from .security import PolicyError, object_hash, digest
from .workflow import Workflow
from .tools import SourceTools, ToolContext
from .report import build_report
from .completion import assess_completion, VERSION


class ReadOnlyStore(Store):
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.key = (self.root / '.integrity-key').read_bytes()

    def put(self, *args, **kwargs):
        raise PolicyError('Reprocessamento não pode escrever no run')

    def event(self, *args, **kwargs):
        raise PolicyError('Reprocessamento não pode criar evidência de execução')

    def lock(self, *args, **kwargs):
        raise PolicyError('Reprocessamento não pode iniciar/retomar execução')


class OverlayStore:
    def __init__(self, store, run_id, overrides):
        self.store, self.run_id, self.overrides = store, run_id, overrides
        self.root = store.root

    def get(self, run_id, name):
        if run_id != self.run_id:
            raise PolicyError('Overlay de outro run')
        return copy.deepcopy(self.overrides[name]) if name in self.overrides else self.store.get(run_id, name)

    def exists(self, run_id, name):
        return name in self.overrides or self.store.exists(run_id, name)

    def names(self, run_id, namespace):
        return self.store.names(run_id, namespace)

    def path(self, *args, **kwargs):
        return self.store.path(*args, **kwargs)

    def put(self, *args, **kwargs):
        raise PolicyError('Overlay somente leitura')

    event = put
    lock = put


def response_view(store, run_id, invocation_id, raw, certificates):
    checkpoint = store.get(run_id, 'codex-turns/' + invocation_id)
    if (checkpoint['status'] != 'completed' or checkpoint['role'] != 'juiz'
        or checkpoint['phase'] != 'final' or checkpoint['output'].encode() != raw):
        raise PolicyError('Resposta não corresponde ao checkpoint original concluído')
    output = Judgment.model_validate_json(raw)
    import json
    if output.model_dump(mode='json') != json.loads(raw):
        raise PolicyError('Reprocessamento não pode modificar a resposta')
    phase = copy.deepcopy(store.get(run_id, 'roles/juiz/phases/final'))
    phase.update(invocation_id=invocation_id, output=output.model_dump(mode='json'),
        published_at=checkpoint['finished_at'],
        derived_response_selection={'original_sha256': digest(raw), 'not_historical_publication': True})
    view = OverlayStore(store, run_id, {'judgment': output.model_dump(mode='json'),
        'roles/juiz/phases/final': phase, 'assessment/causal-certificates': certificates})
    workflow = Workflow(view, run_id)
    tools = SourceTools(view, workflow.manifest, workflow.config, None,
        ToolContext(run_id, 'juiz', 'final', invocation_id))
    workflow.validate_output(output, tools, final=True)
    return view


def reprocess_response(store, run_id, invocation_id, raw, certificates, completion_review):
    view = response_view(store, run_id, invocation_id, raw, certificates)
    report = build_report(view, run_id)
    completion = assess_completion(report, completion_review)
    original_state = copy.deepcopy(report['state'])
    report['state'] = {**original_state, 'status': completion['status'],
        'limitations': [entry['text'] for entry in completion['limitations']],
        'completion_blockers': completion['blockers'], 'assessment_version': VERSION,
        'technical_result': 'offline_reprocessed: decisions recorded for the selected original response'}
    report['limitations'] = [entry['text'] for entry in completion['limitations']]
    report['validation'] = 'reprocessamento offline de evidências reais; nenhuma nova execução'
    report['completion_assessment'] = completion
    report['derivation'] = {'version': VERSION, 'new_real_execution': False,
        'original_response_sha256': digest(raw), 'selected_invocation_id': invocation_id,
        'original_historical_state': original_state, 'response_changed': False,
        'certificates_hash': object_hash(certificates), 'completion_review_hash': object_hash(completion_review)}
    return report, view
