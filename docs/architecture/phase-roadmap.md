# Phase Roadmap

| Phase | Scope |
|---|---|
| 0 | Foundation |
| 1 | Accounts / Authentication / RBAC |
| 2 | Organization Management |
| 3 | Person / Employee Core |
| 4 | Employment / Position / Assignment |
| 5 | Employee Lifecycle |
| 6 | Dynamic Theme Engine |
| 7 | Recruitment / ATS |
| 8 | Onboarding |
| 9 | Offboarding |
| 10 | Transfers / Promotions / Movements |
| 11 | Documents |
| 12 | Workflow Engine |
| 13 | Approval Engine |
| 14 | Notifications |
| 15 | HR Cases |
| 16 | Headcount / Workforce Planning |
| 17 | Search |
| 18 | Imports / Bulk Upload |
| 19 | Data Quality |
| 20 | Audit / Security Audit |
| 21 | Reports |
| 22 | Dashboards / ApexCharts |
| 23 | REST API Expansion |
| 24 | Electron Desktop Application |
| 25 | Security Hardening |
| 26 | Performance / Scalability |
| 27 | Production Deployment |
| 28 | Enterprise QA / UAT |

## Integration contract
Organizations ← Employee refs Organization · Employees ← refs Person · Positions ← Assignment refs Position · Lifecycle ← refs Employment · Recruitment → `HireService` creates Employee · Onboarding ← created from hire event · Movements → `MovementService` updates Assignment · Offboarding → `OffboardingService` changes Employment/Lifecycle · Reports ← selectors · Electron ← API over services.

Each phase ends with a commit and push to the repository.
