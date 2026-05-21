# malformed_schema_rejected

The stored output is intentionally malformed: it labels a trap `REAL` but
omits the required citation. The evaluator should count schema parsing as
failed without calling any provider.
