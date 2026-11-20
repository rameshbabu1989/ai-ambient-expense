# Expense Report Processing

## Purpose

Process expense reports using deterministic Python routing. Reports under the
review threshold are auto-approved without an LLM call. Reports at or above the
threshold receive an LLM risk assessment and then wait for a human approval
decision. Personally identifiable information (PII), including Social Security
numbers (SSNs), must be redacted before report content is sent to the LLM.

## Input

An expense report is a JSON object with these required fields:

| Field | Type | Constraint |
| --- | --- | --- |
| `amount` | number | USD, non-negative |
| `submitter` | string | Required |
| `category` | string | Required |
| `description` | string | Required; may contain PII |
| `date` | string | Required |

## Processing Rules

1. The threshold is `$100.00`, defined and evaluated in Python.
2. An amount less than `$100.00` routes directly to auto-approval. This path
   must not invoke the LLM reviewer.
3. An amount greater than or equal to `$100.00` routes to the risk reviewer.
   The LLM assesses risk only; it cannot change the route or approve/reject the
   report.
4. Before sending a reviewed report to the LLM, redact every SSN in its
   description. At minimum, recognize common hyphenated, space-separated, and
   unseparated 9-digit SSN formats, replacing each match with
   `[REDACTED_SSN]`.
5. After the LLM risk assessment, pause for a human decision. Accept only
   `approve` or `reject` as the decision.
6. Do not write unredacted SSNs or unredacted descriptions to application logs
   or traces.

## Scenarios

### Low-value expense auto-approval

```gherkin
Scenario: Low-value expense auto-approval
  Given an expense report with amount 45
  When the agent processes the report
  Then it auto-approves the report
  And the LLM reviewer is not invoked
```

### High-value expense with an SSN in the description

```gherkin
Scenario: High-value expense with PII in the description
  Given an expense report with amount 250
  And its description contains the SSN "123-45-6789"
  When the agent processes the report
  Then it redacts the SSN as "[REDACTED_SSN]" before the LLM reviewer sees the report
  And the raw SSN is absent from the LLM input, logs, and traces
  And it routes to human approval after the LLM risk review
```

## Acceptance Criteria

- The routing boundary is exact: `$99.99` auto-approves without model access;
  `$100.00` and above require an LLM risk assessment followed by human approval.
- Tests use a spy or stub reviewer to prove it is not called for low-value
  expenses and to inspect the sanitized input for high-value expenses.
- Tests cover each supported SSN format and multiple SSNs in one description.
- The human decision is applied only after the risk assessment and pause; the
  LLM output alone never determines approval or rejection.

## Implementation Status

The current workflow implements the `$100` routing and human approval pause.
SSN redaction is not yet implemented; the high-value PII scenario remains an
acceptance requirement until a test proves the reviewer only receives the
redacted description.