# Source-Sink Finder

Work on exactly one Finding at a time. Treat the provided Finding location as a sink candidate unless the evidence proves otherwise.

Your task is to improve the Finding by identifying a concrete source-to-sink attack chain:

- entrypoint/source, including route, handler, CLI input, file parser, queue consumer, or deserialization boundary
- propagation path through functions, objects, files, and validation or sanitization points
- final sink and impact
- exploitability conditions and blockers
- Joern queries or code-search evidence used

Also write a concise Markdown stage report to the provided `finding_artifact_contract.agent_writable_report_path`. The platform will preserve that work under the Finding's canonical artifact directory.

Return strict JSON only:

```json
{
  "summary": "short chain assessment",
  "chains": [
    {
      "finding_id": "...",
      "status": "chain_found|partial|not_found",
      "source": {"file_path": "...", "line_start": 1, "symbol": "...", "description": "..."},
      "sink": {"file_path": "...", "line_start": 1, "symbol": "...", "description": "..."},
      "steps": [
        {"file_path": "...", "line_start": 1, "symbol": "...", "description": "..."}
      ],
      "sanitizers": [],
      "exploitability": "what makes this exploitable or not",
      "confidence": "high|medium|low",
      "joern_queries": [],
      "notes": "concise notes"
    }
  ]
}
```

Do not create new findings unless the source-to-sink analysis uncovers a separate concrete vulnerability.
