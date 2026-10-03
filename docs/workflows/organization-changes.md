# Organization change workflows

Every change below runs in one database transaction:
1. validation
2. update
3. relationship row
4. `OrganizationHistory`
5. `AuditLog`

The same applies from the web UI, the API and commands.

## Open a restaurant
1. Create it under an area, with status *Planned* (default) or *Active*. The code `RST-<city>-NNN` is generated.
2. When it opens, run *Activate*. If no opening date was set, it becomes the effective date. The area must be active.

## Temporarily close and reopen
*Temporarily close* (renovation, incidents): the restaurant stays live, so its area cannot be deactivated. *Reopen* returns it to active.

## Permanently close
*Close* sets `closing_date` and `effective_to`. A closed restaurant can be *reopened*, which clears the closing date, if its area is active. It can be *archived* once it will never reopen.

## Move a unit
Choose the new parent and the effective date (default today) and give a reason.
* Allowed: restaurant → another area, area → another region, region → another operations division, department → another location, location → another corporate division.
* The new parent must be live and in the same company. Your scope must cover both the unit and the new parent.
* The old relationship is closed at the effective date and a new one opens. The unit keeps its code (for example `DEPT-LHR-LEG` stays even when moved to Karachi).
* Historical queries keep answering with the old parent for dates before the move.

## Deactivate or archive a structural unit
First deactivate, close or move all of its live children. Then *Deactivate* sets `effective_to`. *Archive* requires the unit to be inactive.

## Code corrections
Not supported. Codes are immutable (ADR-014). To fix a wrongly created unit, archive it and create a new one. Both stay in history.
