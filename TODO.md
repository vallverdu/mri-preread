# TODO

Project-manager task list. Initial inventory reviewed against the source and project history on
2026-10-10. Checked items record work already delivered; they were not all completed on this date.
Unchecked items are planned work, with no owner or delivery date assigned yet.

Keep one task per line using `- [ ]` or `- [x]`. Preserve the task ID and wording when changing
its checkbox: project-manager matches tasks by normalized text. Keep completed tasks as history.
Its completion percentage counts these tasks; it does not measure clinical readiness.

## Completed — scan preparation and viewer

- [x] MRI-001: Import NIfTI sequences and extract classic DICOM exports into study folders with editable sequence roles.
- [x] MRI-002: Prepare a brain reference grid, align sequences, and generate brain-focused outlier and hemispheric asymmetry maps.
- [x] MRI-003: Deliver a standalone browser viewer with linked axial, coronal and sagittal views plus 3D Surface, Volume and MIP modes.
- [x] MRI-004: Start with the whole volume and let slice navigation or manual sliders define the 3D cuts.
- [x] MRI-005: Add foldable controls, resizable side panels, custom scroll indicators and reorderable slice panes.
- [x] MRI-006: Add rulers, circular ROI statistics across sequences and CSV measurement export.
- [x] MRI-007: Add location-linked clinician notes, browser draft persistence and portable annotation JSON.
- [x] MRI-008: Add manual voxel masks with 2D and 3D painting, erasing, undo/redo and geometry-checked JSON import/export.

Evidence: [viewer controls](README.md#viewer), [annotation architecture](docs/KNOWLEDGE.md#annotation-and-report-persistence)
and the viewer/annotation tests in `tests/`.

## Completed — model access and automatic research review

- [x] MRI-009: Expose 16 per-study MCP tools for image evidence, statistics, viewer focus and separate model annotations.
- [x] MRI-010: Add local MedGemma download, smoke testing and offline inference using the bundled MLX backend.
- [x] MRI-011: Supply aligned clean sequence images to sampled-plane review and save exact inputs, prompts, responses, model provenance and timings.
- [x] MRI-012: Attach completed MedGemma reports to the viewer after checking input hashes, with navigation to reviewed planes and expandable evidence.
- [x] MRI-013: Add blinded benchmark preparation, frozen-prediction scoring and an expert-mask pilot; document the MedGemma pilot's failure to discriminate.
- [x] MRI-014: Watch completed local DICOM export folders using a final .ready marker, durable jobs, deduplication, failure recovery and human-controlled review states.

Evidence: [scan-to-report workflow](README.md#from-a-scan-to-a-viewable-ai-report),
[automatic worklist](README.md#automatic-local-review-worklist) and
[current evaluation limits](docs/clinical-assistant.md#current-evidence-and-constraints).
Runtime operation and traceability are implemented; useful anomaly detection and AI urgency are not validated.

## Completed — public release and website

- [x] MRI-015: Publish audited MIT source on GitHub while excluding private studies, local configuration, model weights and personal agent files from public source history.
- [x] MRI-016: Publish the clinician-facing website and integration guide through GitHub Pages with source audits and deployment checks.
- [x] MRI-017: Provide a real CC0 public MRI demonstration with source provenance and reproducible derivative checksums.
- [x] MRI-018: Add an image-first automatically loaded volume header with a compact owner-approved preview, front-to-back animation, wheel cutting and rotation.
- [x] MRI-019: Add distinct feature close-ups, retain the original tablet photograph, and use a generated consultation illustration with image licenses in license.txt.

Evidence: [public repository](https://github.com/vallverdu/mri-preread),
[website](https://vallverdu.github.io/mri-preread/), [release procedure](docs/public-release.md)
and [image records](docs/website-photos.md). Header assets use separate owner permission.

## Next — documentation, evaluation and model runtimes

- [ ] MRI-020: Replace outdated publication wording and repository URL placeholders in the hospital integration guide with the published clone instructions.
- [ ] MRI-021: Define the next brain-lesion evaluation protocol with expert references, held-out studies, negative cases and agreed detection/localization metrics before tuning.
- [ ] MRI-022: Compare decision scoring and prompts against the all-positive MedGemma baseline, freezing each run and reporting false flags, missed findings and invalid responses.
- [ ] MRI-023: Evaluate adjacent-plane and multi-sequence evidence with spatial localization and explicit coverage limits, including small lesions between sampled planes.
- [ ] MRI-024: Add a bundled CUDA inference adapter that preserves the existing image-input interface, offline operation and inspectable review traces.
- [ ] MRI-025: Add a reproducible vision-model MCP client example for a supported llama.cpp or other local runtime, with verified image handling and tool routing.
- [ ] MRI-026: Benchmark scan-to-viewer and scan-to-draft latency, memory, storage and failure recovery on representative studies and hardware.

These tasks improve research evaluation and execution options. Current AI output must not set clinical priority.
See [model/runtime boundaries](docs/hardware-and-model.md) and [evaluation plan](docs/clinical-assistant.md#evaluation-before-changing-the-human-queue).

## Next — hospital pilot and reliable operation

- [ ] MRI-027: Verify ingestion, sequence assignments, orientation, alignment and measurements against a trusted viewer using representative institutional vendor/protocol samples.
- [ ] MRI-028: Add explicit image-quality and coverage checks with visible reasons for missing sequences, motion, unusable alignment and unsupported protocols.
- [ ] MRI-029: Implement and test one hospital PACS/DICOMweb intake adapter with a reliable completed-study signal and repeat-export handling.
- [ ] MRI-030: Build an authenticated portal integration example that checks access to both the viewer and its data and supports the portal's content security policy.
- [ ] MRI-031: Add centralized clinician annotation storage with authenticated authorship, review sign-off, conflict handling and an audit trail.
- [ ] MRI-032: Export clinician masks to NIfTI and DICOM SEG with verified mapping back to the original study geometry.
- [ ] MRI-033: Add durable queued workers with isolated study workspaces, bounded concurrency, backpressure and restart recovery for high-volume processing.
- [ ] MRI-034: Test reader usefulness in a shadow pilot, recording review time, corrections, missed findings and false flags without changing the clinical queue.

Scope and acceptance should follow the [institutional integration guide](docs/hospital-integration.md).
Existing local browser drafts and the serial watcher are not a shared hospital record or scalable service.

## Later — extensions that need separate evidence

- [ ] MRI-035: Evaluate an optional stronger brain-masking method across representative protocols and record exclusions and failures.
- [ ] MRI-036: Add enhanced multi-frame MRI ingestion with verified per-frame patient geometry and completeness checks.
- [ ] MRI-037: Define and evaluate a pipeline for one additional anatomical region before extending the brain-specific asymmetry claims.
- [ ] MRI-038: Evaluate condition-specific urgency in shadow mode with independent expert labels and measured waiting-time benefits and delays before considering queue changes.

## Maintaining this list

Mark a task complete only when its stated behavior is delivered and checked; include the task ID and
verification in the implementation commit or pull request. Add follow-up tasks instead of treating
partial work as complete. Reopen a checkbox if its delivered behavior regresses.
Project-manager reads the root `TODO.md` from the repository's default branch on sync; commit and
push updates through the clean public checkout described in [public-release.md](docs/public-release.md).
Keep patient details, reports and local filesystem paths out of task text.
