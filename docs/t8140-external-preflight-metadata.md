# Optional T8140 external preflight metadata

The existing optional external-controller handoff now emits a separate
`FDT: T8140 external preflight:` prefix. It reports alias and node selection,
the result of the existing conditional power check, whether validation ran,
the last attempted validation step/result, and firmware-version/compatibility
property lengths. Only well-formed tuples of one to five big-endian32-bit
version components are printed. Missing, empty, misaligned or oversized
properties are labelled and never interpreted as tuples.

The firmware metadata is inspected after the external snapshot has been
restored on a validation failure, so it describes the retained DT. No device
path, physical address, firmware buffer, identity or raw ADT is printed by the
new prefix. Existing diagnostic output is unchanged; operators collecting
only this metadata must select the new prefix, rather than exporting an
unfiltered console containing other diagnostics.

There is no extra power, register, reset or service operation. The existing
power check still runs once only when an external path was selected.
Validation and external-only rollback, disabled external consumers, internal
panel ownership and SEP/boot identity behavior are unchanged.
`controller_validated` reports the existing preflight result;
`display_qualified=0` makes explicit that it is not external-link/KMS proof.
The firmware tuple is data already supplied to the DT, not an assertion that
the kernel supports that external firmware interface.

The separate public m1n1 PR26 changes external started/stopped-idle ASC
admission and pre-boot failure isolation. This logging does not duplicate or
qualify those changes. A combined candidate must integrate both on the
reviewed current source, retain PR26's hardware-pending status and earn its
own tests/boot evidence. Kernel external-controller/profile/graph support is
also separate and remains required.

Off-target tests check the log's read/privacy surface and that all original
preflight operations remain byte-identical after removing observer statements
and reversing the one-for-one power-check factoring. An extracted-real-C
negative test exercises absent nodes/properties, empty/negative/misaligned/
oversized lengths, single/five-cell tuples and path redaction. Host test
execution is distinct from a firmware build and never proves hardware ready.

Actual collection requires a separately authorized controller operation.
No boot, proxy fetch or hardware test is performed by this source change.
Cold-boot observations require dock connection before power-on, coordinated
owner attendance and exact original boot-artifact rollback. This code never
forces a powered-off external controller on. A persistent Stage1 change
requires the target OS's paired recovery and owner authentication; this
logging does not request that installation. Unknown external firmware
methods, endpoints or DMA ownership are not inferred from a version tuple.
