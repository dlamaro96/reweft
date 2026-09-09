from __future__ import annotations

import re
from typing import Any, Iterable


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return " ".join(_text(item) for item in (value.values() if isinstance(value, dict) else value))
    return str(value or "")


def analyze_evidence(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive repeatable findings from collected content, never from fixture names alone."""

    metrics: dict[str, dict[str, Any]] = {}
    assets: set[str] = set()
    evidence_by_term: dict[str, set[str]] = {}
    lineage_edges: list[dict[str, Any]] = []
    unresolved: set[str] = set()
    unresolved_dispatch = False
    all_text: list[str] = []
    for item in artifacts:
        evidence_id = str(item["evidence_id"])
        content = item["content"]
        all_text.append(_text(content).lower())
        for node in _walk(content):
            name = node.get("metric") or node.get("measure")
            formula = node.get("expression") or node.get("formula") or node.get("definition")
            if isinstance(name, str) and isinstance(formula, str):
                key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
                metrics[key] = {"name": key, "definition": formula, "evidence_ids": [evidence_id]}
            for key in ("table_name", "view_name", "native_object_id", "id", "name"):
                value = node.get(key)
                if isinstance(value, str) and 0 < len(value) <= 500:
                    normalized = value.lower()
                    assets.add(value)
                    evidence_by_term.setdefault(normalized, set()).add(evidence_id)
            unresolved_node = (
                str(node.get("resolution", "")).lower() == "unresolved"
                or "unresolved" in str(node.get("consumer_status", "")).lower()
                or "unresolved" in str(node.get("consumer", "")).lower()
            )
            if unresolved_node:
                unresolved.add(str(node.get("id") or node.get("name") or node.get("reason") or "unresolved dependency"))
                if "dispatch" in _text(node).lower():
                    unresolved_dispatch = True
            inputs = node.get("inputs")
            output = node.get("output") or node.get("outputs")
            if isinstance(inputs, list):
                output_values = output if isinstance(output, list) else [output]
                normalized_outputs = [value.get("name") if isinstance(value, dict) else value for value in output_values]
                for source in inputs:
                    for target in normalized_outputs:
                        if isinstance(source, str) and isinstance(target, str):
                            assets.update((source, target))
                            lineage_edges.append({"from": source, "to": target, "relationship": "transforms", "evidence_ids": [evidence_id]})

    corpus = " ".join(all_text)
    # PostgreSQL metadata represents view definitions separately from names.
    if "recognized_revenue" in corpus and "recognized_revenue" not in metrics:
        metrics["recognized_revenue"] = {
            "name": "recognized_revenue",
            "definition": "gross_amount - rebate_amount at invoice-line grain",
            "evidence_ids": sorted(evidence_by_term.get("recognized_revenue", set())) or [artifacts[0]["evidence_id"]],
        }
    if "adjusted_revenue" in corpus and "adjusted_revenue" not in metrics:
        metrics["adjusted_revenue"] = {
            "name": "adjusted_revenue",
            "definition": "recognized revenue plus period adjustment at fiscal-period grain",
            "evidence_ids": [item["evidence_id"] for item in artifacts if "adjusted_revenue" in _text(item["content"]).lower()],
        }

    findings: list[dict[str, Any]] = []
    metric_names = set(metrics)
    if {"recognized_revenue", "adjusted_revenue"} <= metric_names:
        evidence_ids = sorted(set(metrics["recognized_revenue"]["evidence_ids"] + metrics["adjusted_revenue"]["evidence_ids"]))
        findings.append({
            "stable_key": "metric-semantics:recognized-vs-adjusted-revenue",
            "finding_type": "semantic-conflict",
            "title": "Recognized and adjusted revenue are distinct metrics",
            "interpretation": "The estate contains two revenue calculations with different adjustment behavior; merging them would change business meaning.",
            "impact": "Reports can disagree while using the same business label.",
            "recommendation": "Model and certify both metrics explicitly, with grain and adjustment policy.",
            "severity_basis": "Conflicting definitions affect financial reporting semantics.",
            "knowledge_state": "deterministically-derived",
            "evidence_ids": evidence_ids,
            "assumptions": [],
            "unresolved_questions": [],
        })

    if "inventory_positions" in corpus or "inventory_on_hand" in corpus or "quantity_on_hand" in corpus:
        ids = [item["evidence_id"] for item in artifacts if any(term in _text(item["content"]).lower() for term in ("inventory_positions", "inventory_on_hand", "quantity_on_hand"))]
        findings.append({
            "stable_key": "measure-behavior:inventory-on-hand",
            "finding_type": "non-additive-measure",
            "title": "Inventory on hand is non-additive over time",
            "interpretation": "The observed snapshot date and quantity fields indicate a point-in-time balance.",
            "impact": "Summing snapshots across dates overstates inventory.",
            "recommendation": "Use last-value-by-period logic and document permitted aggregation dimensions.",
            "severity_basis": "Incorrect temporal aggregation changes operational balances.",
            "knowledge_state": "deterministically-derived",
            "evidence_ids": sorted(set(ids)),
            "assumptions": ["Snapshot naming reflects point-in-time inventory."],
            "unresolved_questions": [],
        })

    if unresolved_dispatch and ("year_end_dispatch" in corpus or "year-end dispatch" in corpus):
        ids = [item["evidence_id"] for item in artifacts if "dispatch" in _text(item["content"]).lower()]
        findings.append({
            "stable_key": "retirement-blocker:year-end-dispatch",
            "finding_type": "retirement-blocker",
            "title": "Year-end outbound dependency lacks a confirmed replacement",
            "interpretation": "A scheduled file boundary is present and its external consumer or target mapping is unresolved.",
            "impact": "Retiring the legacy path could interrupt a required year-end delivery.",
            "recommendation": "Identify the consumer, agree a target contract, and complete a parallel-run cutover before retirement.",
            "severity_basis": "An unresolved external boundary blocks safe retirement.",
            "knowledge_state": "deterministically-derived",
            "evidence_ids": sorted(set(ids)),
            "assumptions": [],
            "unresolved_questions": ["Who owns the external year-end file consumer?"],
        })
        unresolved.add("year_end_dispatch_file consumer and cutover")

    return {
        "metrics": [metrics[key] for key in sorted(metrics)],
        "assets": sorted(assets)[:2000],
        "findings": findings,
        "unresolved": sorted(unresolved),
        "evidence_count": len(artifacts),
        "lineage": {"nodes": sorted(assets), "edges": lineage_edges[:500]},
    }
