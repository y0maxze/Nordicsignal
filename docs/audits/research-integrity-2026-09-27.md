# Research integrity follow-up

Found and fixed two reproducible data-integrity defects:

- A colon in an unrecognised continuation label (for example a condition or note) terminated extraction and could discard a qualification attached to a share count. Only recognised field labels now delimit a field. Unrecognised continuation text is preserved, preventing an exact-count dilution calculation.
- Concurrent profile collectors could overwrite a more recently stored profile. Snapshot updates now compare the original identity, payload and attempt time; concurrent inserts are also protected. A superseded fetch cannot create a history revision.

The parser is version 2. Version-1 terms and dilution are withheld from both current and historical API views pending fresh validation, because old extracted text may have lost qualifications. Original archived payloads remain unchanged for audit. A failed source fetch cannot reintroduce version-1 terms. Failure retention still applies to the current safe parser version.

Document capture and history recording use completion time rather than batch-start time. PWA cache v19 includes explicit revalidation language. Frozen scoring, Opportunity, High Conviction, sizing, push rules and credentials are unchanged.
