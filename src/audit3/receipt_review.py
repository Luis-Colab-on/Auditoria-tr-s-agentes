"""Review the controller's measurement caveat without changing receipt facts.

Reports produced by build_report read receipts through the authenticated Store.
The origin path is therefore part of the evidence: model prose with the same
words never acquires the receipt's authority. Older receipts need no migration.
"""
import re
from datetime import datetime
from .schemas import EvidenceReceipt
from .security import PolicyError, digest

MEASUREMENT_NOTE = 'Exit code não mede cobertura; contagens não fornecidas são desconhecidas.'
MEASUREMENT_CRITERION = 'executor-measurement'
COUNTERS = ('suites', 'cases', 'assertions', 'failed_assertions')


def supporting_receipt_evidence(report, message):
    """Validate every receipt origin and return the exact supporting pointers."""
    if message.get('text') != MEASUREMENT_NOTE or not message.get('origins'):
        raise PolicyError('Nota de medição fora do contrato do Executor')
    manifest = report.get('manifest', {})
    if report.get('structural_checks', {}).get('source_integrity') is not True:
        raise PolicyError('Nota de medição exige fonte íntegra verificada')
    if not isinstance(manifest.get('requirements'), str) or not manifest['requirements'].strip():
        raise PolicyError('Nota de medição exige objetivo explícito')
    receipts = report.get('receipts', [])
    if not isinstance(receipts, list):
        raise PolicyError('Lista de receipts inválida')
    selected = set()
    for origin in message['origins']:
        if not isinstance(origin, str):
            raise PolicyError('Origem de nota inválida')
        match = re.fullmatch(r'/receipts/(0|[1-9][0-9]*)/limitations/(0|[1-9][0-9]*)', origin)
        if not match:
            # Workflow copies unresolved controller notes into state.limitations.
            # It is not itself a source of receipt authority.
            if re.fullmatch(r'/state/limitations/(0|[1-9][0-9]*)', origin):
                index = int(origin.rsplit('/', 1)[1])
                copies = report.get('state', {}).get('limitations', [])
                if index < len(copies) and copies[index] == MEASUREMENT_NOTE:
                    continue
            raise PolicyError('Nota de medição sem proveniência exclusiva do Executor')
        index, note_index = map(int, match.groups())
        try:
            raw = receipts[index]
            if raw['limitations'][note_index] != MEASUREMENT_NOTE:
                raise PolicyError('Origem da nota não corresponde ao receipt')
            receipt = EvidenceReceipt.model_validate(raw)
            started, finished = map(datetime.fromisoformat, (receipt.started_at, receipt.finished_at))
        except (IndexError, KeyError, TypeError, ValueError):
            raise PolicyError('Receipt de medição incompleto ou inválido') from None
        if (receipt.run_id != manifest.get('run_id') or receipt.source_id != manifest.get('source_id')
            or receipt.profile_hash != manifest.get('profile_hash')
            or sum(isinstance(item, dict) and item.get('id') == receipt.id for item in receipts) != 1):
            raise PolicyError('Receipt de medição não pertence à execução/fonte/perfil atual')
        if (receipt.execution not in {'docker', 'compose'} or receipt.status not in {'passed', 'failed'}
            or raw.get('timeout') is not False or raw.get('output_truncated') is not False
            or type(raw.get('exit_code')) is not int
            or (receipt.status == 'passed') != (receipt.exit_code == 0)):
            raise PolicyError('Receipt de medição não demonstra execução completa')
        if (not receipt.command or not receipt.image_ids or not receipt.versions
            or started.utcoffset() is None or finished.utcoffset() is None or finished < started
            or receipt.stdout_sha256 != digest(receipt.stdout.encode())
            or receipt.stderr_sha256 != digest(receipt.stderr.encode())):
            raise PolicyError('Receipt de medição sem metadados/streams íntegros')
        if any(key not in raw or (raw[key] is not None and (type(raw[key]) is not int or raw[key] < 0)) for key in COUNTERS):
            raise PolicyError('Contagens do receipt ausentes ou inválidas; desconhecido não é zero')
        selected.add(index)
    if not selected:
        raise PolicyError('Cópia narrativa sem receipt original do Executor')
    return ['/manifest/requirements', '/structural_checks/source_integrity',
            *[f'/receipts/{index}' for index in sorted(selected)]]


def validate_receipt_note(report, message, annotation, contract=None):
    """The caller verifies the objective contract before reaching this criterion."""
    if (annotation.get('criterion') != MEASUREMENT_CRITERION or annotation.get('kind') != 'procedure_note'
        or not isinstance(contract, dict) or contract.get('quantitative_measurement_required') is not False):
        raise PolicyError('Nota de medição não pode dispensar métricas exigidas pelo objetivo')
    if annotation.get('evidence') != supporting_receipt_evidence(report, message):
        raise PolicyError('Referências não sustentam a nota de medição do Executor')
