# Recruitment / ATS Architecture

Bounded domain `apps/recruitment` (Phase 7). **Candidate ≠ Employee.**

```
Manpower Requirement → Job Requisition → Job Posting → Candidate → Application → Screening
→ Interview → Assessment → Selection → Offer → Accepted → Hire → Employee → Onboarding
```
Entities: Candidate, JobRequisition, JobPosting, Application, ApplicationStage, Interview, InterviewPanel, Assessment, Offer, CandidateNote, RecruitmentSource.

Boundary contract: recruitment depends on `organizations`, `positions`, `headcount` (requisition ← approved headcount). Hiring is a single controlled `HireService.hire(application)` (atomic): creates Person/Employee/Employment/Assignment, writes audit, enqueues `EmployeeHired` → onboarding instance is created by an event handler. Recruitment never writes employee tables directly.
