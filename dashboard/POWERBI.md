# Power BI dashboard (build time: ~45 min)

## 1. Load data
Power BI Desktop → **Get data → Text/CSV**, load all three (after the pipeline has run at least once):

| File | Grain | Refreshed |
|---|---|---|
| `dashboard/test_results.csv` | one row per test per run | appended every run |
| `dashboard/jira_issues.csv` | one row per Jira bug | fully refreshed each run (needs Jira credentials) |
| `dashboard/triage_eval.csv` | one row per labelled canary failure | appended every canary run |

Set types: `run_date`, `created`, `resolved` → Date/Time; `duration_s`, `age_days`, `cycle_days` → Decimal.
Add a `Date` table (`Date = CALENDAR(MIN(test_results[run_date]), MAX(test_results[run_date]))`) and relate it to `test_results[run_date]` and `jira_issues[created]`.

## 2. Measures
```DAX
Tests Run      = COUNTROWS(test_results)
Tests Passed   = CALCULATE([Tests Run], test_results[outcome] = "passed")
Pass Rate      = DIVIDE([Tests Passed], [Tests Run])

Open Defects   = CALCULATE(COUNTROWS(jira_issues), jira_issues[status_category] <> "done")
Closed Defects = CALCULATE(COUNTROWS(jira_issues), jira_issues[status_category] = "done")
Avg Open Age (days) = AVERAGEX(FILTER(jira_issues, jira_issues[status_category] <> "done"), jira_issues[age_days])
Avg Cycle Time (days) = AVERAGE(jira_issues[cycle_days])      -- resolved bugs only

Triage Accuracy = DIVIDE(SUM(triage_eval[correct]), COUNTROWS(triage_eval))
```
Age bucket (calculated column on `jira_issues`):
```DAX
Age Bucket = SWITCH(TRUE(), jira_issues[age_days] < 1, "<1 day", jira_issues[age_days] < 3, "1-3 days", jira_issues[age_days] < 7, "3-7 days", "7+ days")
```

## 3. Pages / visuals
| Visual | Fields | Answers |
|---|---|---|
| Line chart | `Date[Date]` × `Pass Rate` | Is quality trending up or down? |
| Stacked column | `jira_issues[severity]` × count, legend `classification` | Severity split and what kind of failures dominate |
| Column | `Age Bucket` × `Open Defects` | Defect ageing |
| Cards | `Avg Cycle Time (days)`, `Open Defects`, `Triage Accuracy` | Headline numbers |
| Stacked bar | `test_results[module]` × count, legend `scenario_type` | **Scenario coverage by module** (positive / negative / boundary mix). This is test distribution, not code coverage; label it that way. |
| Table | `key`, `summary`, `severity`, `status`, `age_days` | Drill-down to the Jira ticket |

Add slicers for `module` and `canary` (default: exclude canaries so the headline numbers describe real findings only).

## 4. Make the numbers real
- Cycle time only exists for *closed* bugs. Close a few tickets by moving them to Done in Jira, or let the pipeline auto-close them when the test passes again. Day-scale cycle times need the scheduled workflow to run for a few days.
- Do not publish dashboards built from `scripts/make_mock_run.py` output.
