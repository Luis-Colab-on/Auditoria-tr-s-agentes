from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from .evidence import Store
from .schemas import RunManifest
from .security import atomic_write, canonical, digest, redact
from .completion import assess_completion, protocol_phases, VERSION as ASSESSMENT_VERSION
from .causality import causal_groups
from .config import Config
from .tools import SourceTools, ToolContext
from .security import PolicyError, object_hash


def receipt_observation(store: Store, run_id: str):
    """Controller-only intermediate measurement; never a role's evidence view."""
    manifest = store.get(run_id, 'manifest')
    published = store.exists(run_id, 'barrier')
    receipts = []
    for name in store.names(run_id, 'receipts'):
        receipt = store.get(run_id, 'receipts/' + name)
        executed = receipt['execution'] in {'docker', 'compose'}
        qualified = (executed and receipt['status'] in {'passed', 'failed'}
            and not receipt['timeout'] and not receipt['output_truncated']
            and receipt['run_id'] == run_id and receipt['source_id'] == manifest['source_id']
            and receipt['profile_hash'] == manifest['profile_hash'])
        receipts.append({'id': receipt['id'], 'owner': receipt['owner'],
            'execution': receipt['execution'], 'status': receipt['status'],
            'visibility': 'published' if published or receipt['owner'] == 'baseline' else 'hidden_by_barrier',
            'execution_observed': executed,
            'qualifying_model_reproduction': qualified and receipt['owner'] in {'auditor', 'defensor', 'juiz'}})
    qualified = [r for r in receipts if r['qualifying_model_reproduction']]
    unresolved = [name for name in store.names(run_id, 'execution-attempts')
        if not store.exists(run_id, 'receipts/' + name)
        and store.get(run_id, 'execution-attempts/' + name).get('status') in {'running', 'ambiguous'}]
    if qualified:
        status = 'executed_hidden_by_barrier' if all(r['visibility'] == 'hidden_by_barrier' for r in qualified) else 'executed_published'
    elif unresolved:
        status = 'unknown_pending_receipt'
    elif any(r['execution_observed'] and r['owner'] != 'baseline' for r in receipts):
        status = 'executed_without_qualifying_receipt'
    else:
        status = 'not_executed'
    return {'controller_only': True, 'model_reproduction_status': status,
        'qualifying_model_reproduction_ids': [r['id'] for r in qualified], 'receipts': receipts,
        'unresolved_execution_attempts': unresolved}


def coverage(store: Store, manifest: RunManifest):
    roles = {role: {} for role in ("auditor", "defensor", "juiz")}
    for role in roles:
        for f in manifest.files:
            if f.category not in {"excluded", "prior_report"}:
                roles[role][f.path] = {"inventoried": True, "total_lines": f.lines, "consulted": set(), "analysis_recorded": set(), "flow_verified": set()}
    config = Config.model_validate(store.get(manifest.run_id, "config"))
    for role in roles:
        phase = "blind" if role == "juiz" else "initial-0000"
        tools = SourceTools(store, manifest, config, None, ToolContext(manifest.run_id, role, phase, "coverage"))
        for event in tools.source_read_events():
            d = event["data"]
            roles[role][d["path"]]["consulted"].update(range(d["start"], d["end"] + 1))
        for name in store.names(manifest.run_id, f"roles/{role}/phases"):
            if not (name == "blind" if role == "juiz" else name.startswith("initial-")):
                continue
            record = store.get(manifest.run_id, f"roles/{role}/phases/{name}")
            tools.read_before = record.get("published_at")
            if not tools.read_before:
                continue
            from .schemas import InspectionRecord
            for raw in record["output"].get("inspections", []):
                try:
                    inspection = InspectionRecord.model_validate(raw)
                    tools.validate_inspection(inspection)
                except (PolicyError, ValueError):
                    continue
                for ref in inspection.refs:
                    entry = roles[role][ref.path]
                    entry["analysis_recorded"].update(range(ref.start, ref.end + 1))
                    if inspection.flow_verified:
                        entry["flow_verified"].update(range(ref.start, ref.end + 1))
    gaps = []
    for role, entries in roles.items():
        for path, entry in entries.items():
            all_lines = set(range(1, entry["total_lines"] + 1))
            for key in ("consulted", "analysis_recorded", "flow_verified"):
                entry[key + "_lines"] = len(entry[key])
                entry[key + "_ranges"] = intervals(entry[key])
                entry["missing_" + key] = intervals(all_lines - entry[key])
                del entry[key]
            if role != "juiz" and (entry["missing_consulted"] or entry["missing_analysis_recorded"]):
                gaps.append(f"{role}: {path}: leitura/análise incompletas")
    from .investigation import assess_independent_investigation
    independent = assess_independent_investigation(store, manifest)
    gaps.extend(independent["gaps"])
    receipts = [store.get(manifest.run_id, "receipts/" + name) for name in store.names(manifest.run_id, "receipts")]
    executed = [r["id"] for r in receipts if r["execution"] in {"docker", "compose"} and r["status"] in {"passed", "failed"}]
    if not executed:
        gaps.append("Nenhum teste efetivamente executado no ambiente isolado.")
    if any(r["status"] in {"blocked", "not_executed", "cancelled"} for r in receipts):
        gaps.append("Há verificações bloqueadas/não executadas/canceladas; consulte receipts.")
    excluded = [f.model_dump() for f in manifest.files if f.category == "excluded"]
    if excluded:
        gaps.append(f"{len(excluded)} arquivos omitidos: escopo limitado pelo inventário.")
    return {"roles": roles, "independent_investigation": independent, "excluded": excluded, "executed_test_receipts": executed, "gaps": gaps,
        "interpretation": "Leitura e análise abaixo consideram somente investigação inicial autenticada antes da barreira. Juiz realiza inspeção dirigida, sem exigência de cobertura integral. Inventário, leitura, análise, fluxo declarado e execução são medidas distintas; não provam compreensão integral."}


def intervals(values):
    result = []
    for n in sorted(values):
        if result and result[-1][1] + 1 == n:
            result[-1][1] = n
        else:
            result.append([n, n])
    return result


def structural_checks(store, manifest, state, judgment):
    """Re-evaluate immutable evidence without rewriting historical records."""
    from .snapshot import verify_source
    from .workflow import Workflow
    from .schemas import Judgment
    from .operational import total_seconds
    result = {'evidence_context_hash': object_hash({
        'events': [store.get(manifest.run_id, 'events/' + n) for n in store.names(manifest.run_id, 'events')],
        'tests': [store.get(manifest.run_id, 'tests/' + n) for n in store.names(manifest.run_id, 'tests')],
        'barrier': store.get(manifest.run_id, 'barrier') if store.exists(manifest.run_id, 'barrier') else None,
        'operational': [store.get(manifest.run_id, 'operational/' + n) for n in store.names(manifest.run_id, 'operational')]})}
    config = Config.model_validate(store.get(manifest.run_id, 'config'))
    def check(key, operation):
        try:
            operation()
        except (PolicyError, ValueError, KeyError, OSError) as exc:
            result[key] = False
            result[key + '_error'] = redact(str(exc))[:1000]
        else:
            result[key] = True
    check('source_integrity', lambda: verify_source(store, manifest))
    def final():
        if not judgment:
            raise PolicyError('Julgamento final ausente')
        record = store.get(manifest.run_id, 'roles/juiz/phases/final')
        if record['output'] != judgment:
            raise PolicyError('Julgamento diverge da fase final persistida')
        tools = SourceTools(store, manifest, config, None,
            ToolContext(manifest.run_id, 'juiz', 'final', 'report-validation'))
        Workflow(store, manifest.run_id, runtime=object()).validate_output(
            Judgment.model_validate(judgment), tools, final=True)
    check('final_validation', final)
    def limits():
        calls = store.get(manifest.run_id, 'ledger')['calls']
        if len(calls) > config.limits.max_calls:
            raise PolicyError('Limite de chamadas excedido')
        if state.get('elapsed_seconds', 0) > total_seconds(store, manifest.run_id, config):
            raise PolicyError('Limite global excedido sem extensão válida')
        if any(c['status'] == 'in_flight' for c in calls):
            raise PolicyError('Chamada ainda em andamento/ambígua')
    check('limits_valid', limits)
    return result


def build_report(store: Store, run_id: str, *, use_review=True):
    manifest = RunManifest.model_validate(store.get(run_id, "manifest"))
    state = store.get(run_id, "state")
    published = store.exists(run_id, "barrier")
    opinions = {role: [store.get(run_id, f"roles/{role}/phases/{n}") for n in store.names(run_id, f"roles/{role}/phases")] for role in ("auditor", "defensor", "juiz")} if published else {}
    findings = {}
    for records in opinions.values():
        for record in records:
            for f in record["output"].get("findings", []):
                findings.setdefault(f["id"], f)
    judgment = store.get(run_id, "judgment") if store.exists(run_id, "judgment") else None
    verdicts = judgment["verdicts"] if judgment else []
    if judgment:
        for f in judgment["new_findings"]:
            findings.setdefault(f["id"], f)
    decided = {v["finding_id"] for v in verdicts}
    pending = [{"finding_id": fid, "classification": "hipótese não confirmada", "decision": "investigar", "rationale": "Sem decisão técnica validada/contraditório concluído; não impõe correção."} for fid in findings if fid not in decided]
    receipts = [store.get(run_id, "receipts/" + n) for n in store.names(run_id, "receipts")]
    receipts = [r for r in receipts if published or r["owner"] == "baseline"]
    ledger = store.get(run_id, "ledger")
    groups, causal_gaps = [], []
    if judgment:
        tools = SourceTools(store, manifest, Config.model_validate(store.get(run_id, 'config')), None,
            ToolContext(run_id, 'juiz', 'final', 'report-validation'))
        certificate_name = 'assessment/causal-certificates'
        certificates = store.get(run_id, certificate_name) if store.exists(run_id, certificate_name) else []
        try:
            groups = causal_groups(list(findings.values()), verdicts, tools, tools.source_bytes_for_validation, certificates)
        except PolicyError as exc:
            causal_gaps.append(str(exc))
    if causal_gaps:
        groups = [{'id': 'candidate:' + v['finding_id'], 'member_ids': [v['finding_id']],
                   'evidence_ids': v['evidence_ids'], 'proofs': []}
                  for v in verdicts if v['classification'] == 'falha comprovada']
    grouped_ids = {fid for group in groups for fid in group['member_ids']}
    all_groups = groups + [{'id': 'candidate:' + fid, 'member_ids': [fid],
        'evidence_ids': f['evidence_ids'], 'proofs': []} for fid, f in findings.items() if fid not in grouped_ids]
    metrics = {"suites": sum_known(receipts, "suites"), "cases": sum_known(receipts, "cases"), "assertions": sum_known(receipts, "assertions"),
        "failed_assertions": sum_known(receipts, "failed_assertions"), "unique_finding_ids": len(findings), "unique_findings_after_demonstrated_deduplication": len(all_groups),
        "established_root_causes": sum(bool(g['proofs']) for g in groups),
        "receipt_statuses": {status: sum(r["status"] == status for r in receipts) for status in ("passed", "failed", "skipped", "blocked", "not_executed", "cancelled")}}
    report = {"schema_version": "1.0", "manifest": manifest.model_dump(mode="json"), "state": state,
        "coverage": coverage(store, manifest), "findings": list(findings.values()), "verdicts": verdicts + pending,
        "opinions": opinions, "judgment": judgment, "receipts": receipts, "metrics": metrics, "usage": ledger,
        "runtime": store.get(run_id, "runtime") if store.exists(run_id, "runtime") else {"backend": manifest.backend, "authentication": "unknown", "financial": "unknown", "model": manifest.models, "effort": "unknown", "speed": "unknown"},
        "comparisons": [store.get(run_id, "comparisons/" + n) for n in store.names(run_id, "comparisons")],
        "deduplicated_findings": all_groups, 'proven_causal_groups': groups,
        'causal_validation': {'version': ASSESSMENT_VERSION, 'valid': not causal_gaps, 'gaps': causal_gaps},
        "validation": "execução real registrada" if ledger["calls"] and (state.get("runtime_mode"), manifest.backend) in {("codex-app-server", "codex-app-server"), ("openai-agents", "openai-agents")} and judgment else "implementado, integração real ainda não validada",
        "limitations": manifest.limitations + state.get("limitations", []), "prior_reports_released": published}
    review_name = 'assessment/completion-review'
    additional_round = (store.get(run_id, 'material-review')['additional_round']
                        if store.exists(run_id, 'material-review') else False)
    report['required_phases'] = protocol_phases(manifest, Config.model_validate(store.get(run_id, 'config')), additional_round)
    report['structural_checks'] = structural_checks(store, manifest, state, judgment)
    review = store.get(run_id, review_name) if use_review and store.exists(run_id, review_name) else None
    report['completion_review'] = review
    try:
        report['completion_assessment'] = assess_completion(report, review)
    except PolicyError as exc:
        report['completion_assessment'] = assess_completion(report)
        report['completion_assessment']['blockers'].append({'kind': 'invalid_review', 'text': str(exc)})
        report['completion_assessment']['status'] = 'partial'
        report['completion_assessment']['review_status'] = 'invalid'
    report['acceptance'] = {'status': 'not_evaluated', 'reason': 'Aceitação do smoke exige verificação explícita do processo real'}
    if store.exists(run_id, 'assessment/smoke-acceptance'):
        from .completion import context_hash
        accepted = store.get(run_id, 'assessment/smoke-acceptance')
        if (accepted.get('context_hash') == context_hash(report)
            and accepted.get('review_id') == report['completion_assessment'].get('review_id')
            and report['completion_assessment']['status'] == 'completed'):
            report['acceptance'] = accepted
        else:
            report['acceptance'] = {'status': 'pending', 'reason': 'Aceitação anterior não corresponde às evidências atuais'}
    return report


def sum_known(receipts, key):
    return sum(r[key] for r in receipts) if receipts and all(r[key] is not None for r in receipts) else None


def markdown(report):
    m, s = report["manifest"], report["state"]
    lines = ["# Auditoria audit3", "", f"Execução: `{m['run_id']}`", f"Fonte: `{m['source_id']}`", f"Commit: `{m['commit'] or 'não aplicável (ZIP)'}`", "",
        f"Estado operacional: **{s['status']}**", f"Resultado técnico: **{s['technical_result']}**", "", report["validation"], "",
        "## Decisões", "", "| Achado | Classificação | Decisão |", "|---|---|---|"]
    completion = report['completion_assessment']
    lines += ["Conclusão derivada do escopo: **" + completion['status'] + "**",
        "Revisão: " + str(completion.get('review_id') or completion['review_status']),
        "Aceitação do smoke: " + report.get('acceptance', {}).get('status', 'not_evaluated'), "",
        "Pendências/bloqueios: " + json.dumps(completion['blockers'], ensure_ascii=False), ""]
    for verdict in report["verdicts"]:
        lines.append(f"| {verdict['finding_id']} | {verdict['classification']} | {verdict['decision']} |")
    if not report["verdicts"]:
        lines.append("| — | Sem decisão sobre defeitos | Veja cobertura e estado operacional |")
    for finding in report["findings"]:
        lines += ["", "### " + finding["id"] + ": " + finding["title"], "", "Invariante: " + finding["invariant"], "", "Gatilho: " + finding["trigger"], "", "Condições: " + "; ".join(finding["necessary_conditions"]), "", "Fluxo: " + finding["complete_flow"], "", "Proteções consideradas: " + "; ".join(finding["protections_considered"]), "", "Esperado: " + finding["expected"], "", "Observado: " + finding["observed"], "", "Ambiente real: " + finding["real_environment_relevance"], "", "Origem: " + finding["origin"]]
        for v in report["verdicts"]:
            if v["finding_id"] == finding["id"]:
                lines += ["", "Decisão fundamentada: " + v["rationale"]]
    lines += ["", "## Cobertura e limitações", "", report["coverage"]["interpretation"], ""]
    lines += ["- " + item for item in sorted(set(report["limitations"] + report["coverage"]["gaps"]))]
    lines += ["", "## Execução e métricas", "", "```json", json.dumps(report["metrics"], ensure_ascii=False, indent=2), "```", "",
        "Backend/autenticação/franquia: " + json.dumps(report["runtime"], ensure_ascii=False),
        ("Consumo em dólares: desconhecido/não aplicável ao Pro; não convertido por tarifas API." if report["runtime"]["backend"] == "codex-app-server" else "Custo histórico conforme registro original (sem conversão nova): " + str(report["usage"]["known_cost_usd"])),
        "Chamadas com custo desconhecido: " + str(report["usage"]["unknown_cost_calls"]), "",
        "Suítes, casos, asserções, achados únicos e causas-raiz não são intercambiáveis. null significa desconhecido.", "",
        "Receipts registram procedência; a expectativa do teste ainda exige revisão técnica. Cenários sintéticos não comprovam frequência nem ocorrência em produção.", "",
        "Os detalhes de posições, réplicas, intervalos e evidências estão no JSON. Não são armazenados raciocínios internos privados.", ""]
    return redact("\n".join(lines))


def write_report(store: Store, run_id: str):
    report = build_report(store, run_id)
    atomic_write(store.path(run_id, "report.md"), markdown(report).encode())
    atomic_write(store.path(run_id, "report.json"), redact(json.dumps(report, ensure_ascii=False, indent=2)).encode())
    atomic_write(store.path(run_id, "coverage.json"), canonical(report["coverage"]))
    return report


def export_zip(store: Store, run_id: str, destination: Path, selected: list[str] | None = None, *, review=None):
    # Exports derive a report without rewriting original report/coverage files.
    if destination.resolve().is_relative_to(store.root.resolve()):
        raise PolicyError('Exportação exige destino separado do Store original')
    report = build_report(store, run_id, use_review=review is None)
    if review is not None:
        from .scope_review import review_report
        evaluation = review_report(report, review)
        report['completion_review'] = evaluation['review']
        report['completion_assessment'] = evaluation['completion_assessment']
        report['acceptance'] = {'status': 'not_evaluated', 'reason': 'Revisão de escopo não substitui aceitação específica'}
    content = {"report.md": markdown(report).encode(), "report.json": canonical(report), "coverage.json": canonical(report["coverage"]), "manifest.json": canonical(report["manifest"])}
    available = {r["id"]: r for r in report["receipts"]}
    if selected is None:
        selected = sorted({eid for f in report["findings"] for eid in f["evidence_ids"]} | {r["id"] for r in report["receipts"] if r["owner"] == "baseline"} | {eid for v in report["verdicts"] for eid in v.get("evidence_ids", [])})
    for eid in selected:
        if eid not in available:
            raise PolicyError("evidência não publicada/não existente")
        content["evidence/" + eid + ".json"] = canonical(available[eid])
        content["evidence/" + eid + "-test.json"] = canonical(store.get(run_id, "tests/" + eid))
    content = {path: redact(data.decode()).encode() for path, data in content.items()}
    content["checksums.json"] = canonical({path: digest(data) for path, data in content.items()})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in content.items():
            archive.writestr(path, data)
    with destination.open('xb') as target:
        target.write(buffer.getvalue())
    return destination
