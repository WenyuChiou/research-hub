import type { Locale, Operation, ProjectDetail } from "./types";

export const en = {
  sourceLocallySaved: "Locally saved",
  sourceUnverifiedFile: "Unverified source link",
  recoveryPark: "Park unresolved request…",
  recoveryParkConfirm: "Keep unresolved identity and park",
  recoveryParkWarning:
    "Parking is not server cancellation and does not prove the save failed. A late copy or task may still appear. Keep checking this exact request; do not repeat the same intent as a new request.",
  recoveryParked:
    "Parked locally; the outcome is still shown separately. This request has not been cancelled or replayed.",
  recoverySeparate: "Start a separate intent",
  recoveryParkSessionWarning:
    "The parked disposition could not be saved for reload. Continue only in this session? Reload may block again on the unchanged pending request.",
  recoveryParkSession: "Park for this session only",

  abstractRestoreBlocked:
    "The exact saved copy was not reopened: a Prepare outcome is still locked, or its current linkage is unavailable. No selection or uncertainty was reset. Inspect the pending task before changing its source.",
  intakeAdd: "Add existing text",
  intakeScopeNote:
    "Save one Hub-owned local copy of existing text (up to 40,000 UTF-8 bytes). The original file stays unchanged. No PDF reading, model call, identity verification or external integration write occurs.",
  intakeInput: "Text input",
  intakePasteMode: "Paste abstract or text",
  intakeFileMode: "Choose a .txt or .md file",
  intakeTitle: "Text title",
  intakeLocator: "Publication or source locator (optional)",
  intakeLocatorNote:
    "A locator is unverified metadata and is never fetched. If omitted, this is labeled a saved local text copy, not a publication link.",
  intakeDeclaredScope: "Declared coverage",
  intakeScopeUnknown: "Scope unknown or mixed text",
  intakeScopeAbstract: "This material is an abstract",
  intakePaste: "Paste abstract or text",
  intakePasteNote:
    "Pasting creates new text from this field; it does not preserve the original clipboard or file bytes. Nothing is truncated.",
  intakeFile: "Existing UTF-8 text file",
  intakeFileNote:
    "Strict UTF-8 .txt or .md only, up to 40,000 bytes. The saved file preserves original bytes, including BOM and line endings; this preview is not an editor.",
  intakeBytes: "bytes",
  intakeLocalPreview: "Selected file preview (not saved yet)",
  intakeSave: "Save Hub text copy",
  intakeUnavailable:
    "Saving new text copies is unavailable on this server/platform. Existing metadata-only sources and registered-text reading still work. This implementation does not support Windows text intake.",
  intakeMetadataInvalid:
    "Enter a nonempty title and an optional locator, each at most 2,000 Unicode characters. Invalid Unicode cannot be saved.",
  intakeFileRequired: "Choose a valid text file before saving.",
  intakeRecoveryTitle: "Saved text recovery",
  intakeRecoveryBound:
    "Only exact text-intake identities are checked, at most three automatically per project visit. No source bytes are reconstructed from a key and no model is run.",
  intakePendingItem: "Local text save",
  intakeFound:
    "This exact source and evidence copy are saved. Open the linked text; this does not prepare or run a task, or mark the source reviewed.",
  intakeNotObserved:
    "No committed text save is visible yet. The earlier save may still finish or leave an unregistered copy. This is not proof of failure; do not start a replacement request.",
  intakePendingUnknown:
    "This text save is unresolved. Keep its exact identity; no guessed source, automatic retry or new request is created.",
  intakeCheck: "Check saved text",
  intakeRetrySame: "Retry the same text save",
  intakeNoPayload:
    "The original input is no longer in this session. Only read-only checking is available; the bytes and metadata cannot be reconstructed from the key.",
  intakeOpenSaved: "Open saved text",
  intakeStorageUnavailable:
    "Browser storage is unavailable. Text-save identity is retained only in this session; reload or closure may lose recovery. Title, locator, filenames and text are never saved in browser storage.",
  intakeStorageConfirm:
    "No text was sent because its identity could not be stored. Continue explicitly with in-session recovery only, or cancel this unsent request.",
  intakeSessionOnly: "Save with in-session recovery only",
  intakeSavingLeave:
    "Saving the local copy. You may leave; a pending request may still finish. No model is being run.",
  intakeSavedUnavailable:
    "The source and copy are registered, but the saved bytes are now stale or unavailable. No text is reconstructed or repaired; recheck the registered evidence before selecting an abstract.",
  intakeResolveFirst:
    "Resolve the pending text save using its recovery controls before starting another. Reading and other work remain available.",
  intakeLocalLocator: "Saved local text; publication locator not provided.",
  abstractSelectEntire: "Select entire text as the abstract",

  prepareRecoveryTitle: "Saved preparation recovery",
  prepareRecoveryBound:
    "Only exact saved request identities are checked. At most three are checked automatically per project visit; other checks and same-request retries are explicit. Nothing runs a model.",
  preparePendingItem: "Abstract preparation",
  prepareFound:
    "This exact preparation is saved. Open the same task; recovery does not create a replacement or start execution.",
  prepareNotObserved:
    "No saved preparation is visible yet. The earlier request may still finish; this is not proof of failure or permission to create a new request.",
  preparePendingUnknown:
    "The outcome of this exact preparation is still unknown. Its request identity is retained; no task is guessed or automatically resubmitted.",
  prepareCheck: "Check saved preparation",
  prepareRetrySame: "Retry the same preparation request",
  prepareNoPayload:
    "The original input is no longer in this session. Only read-only checking is available; no payload will be reconstructed or submitted.",
  prepareOpenRecovered: "Open recovered task",
  prepareLegacyFallback:
    "This backend does not advertise compatible preparation recovery. Prepare uses the existing keyless route; lost replies cannot be recovered durably by this UI. No recovery guarantee is claimed.",
  prepareResolveFirst:
    "A preparation in this project is unresolved. Use its recovery controls rather than starting another request. Reading and other work remain available.",
  prepareStorageUnavailable:
    "Browser storage is unavailable. Request identity can be retained only in this live session; reload or closure may lose automatic recovery. No source text, instructions or credentials are stored.",
  prepareStorageConfirm:
    "The request has not been sent because its identity could not be saved in browser storage. Continue only with in-session recovery, or keep working without submitting.",
  prepareSessionOnly: "Prepare with in-session recovery only",
  returnScope: "Saved work in the selected project:",
  returnNotResume:
    "This is saved project state, not a saved reading position or last-visited project.",
  returnPending: "Tasks to revisit",
  returnAccepted: "Human-accepted task records",
  returnAcceptanceNote:
    "Acceptance history is separate from current candidate eligibility and delivery. Open a task to inspect current checks before taking action.",
  returnTaskUpdated: "Task last updated",
  returnUnknown: "Unknown / not recorded",
  returnOpenTask: "Open task",
  returnBoundedTasks:
    "Up to five most recently updated tasks. Open review & delivery for all tasks, including older unfinished work.",
  returnEmpty:
    "No saved tasks yet. Open Literature to add a source record or search for metadata; registering a source does not mean its full text has been read.",
  returnLocalBundles: "Saved local bundle state",
  returnDeliveryScope:
    "These actions create local ZIP files only. They do not show delivery to Zotero, Obsidian or NotebookLM; external delivery is unknown here.",
  returnBundleReview: "Local bundle awaiting human review",
  returnNoReceipt:
    "No local receipt recorded. This does not establish success or failure; inspect the action before retrying.",
  returnNoBundles:
    "No local bundle actions recorded. Accepted content is not changed by this absence.",
  returnReceiptHistory:
    "Last recorded receipt only; the file has not been re-verified by opening this page.",
  returnBoundedBundles:
    "Up to five most recently created local bundle actions; this is not a last-delivery or external-sync timeline.",
  returnInspectBundles: "Inspect local bundle actions",
  returnOverview: "Back to project overview",
  returnTargetMissing:
    "The selected task is no longer present in this project. Review the refreshed project state; no other task was selected.",
  abstractPreparingLeave:
    "Preparation is in flight. Leaving this source does not cancel the save; inspect the original project's tasks before submitting again.",
  abstractPrepareUncertain:
    "The preparation response did not establish whether a task was saved. Do not submit another task blindly. Open Review and use Refresh to inspect existing tasks; no task has been automatically matched or retried.",
  abstractPreparedKnown:
    "This task was saved. Open the prepared task rather than creating a duplicate.",
  abstractOpenPrepared: "Open prepared task",
  abstractReviewExisting: "Review existing tasks",
  abstractRunUncertain:
    "The Run response is uncertain; this task may already have started. Refresh and inspect this same task. An unchanged ready state does not resolve the uncertainty, so Run stays locked. No model call was retried automatically.",
  "paper-abstract-draft": "Abstract-only draft",
  abstractIdentity:
    "Publication identity is unverified; publication version is unknown. Choosing a record and file does not verify that they belong together.",
  abstractScope:
    "Restricted drafting from the selected abstract only: no retrieval, PDF reading, full skill CLI workflow, external writes or independent semantic audit.",
  abstractNoText:
    "No registered evidence text is available here. This draft path supports existing UTF-8 .md/.txt evidence only, not PDFs or metadata alone. You can keep reading the source link and managing its record; no new abstract file is required to leave this step.",
  abstractChooseFile: "Choose existing evidence text",
  abstractChooseFilePlaceholder: "Choose a registered text file",
  abstractReadText: "Read selected saved text",
  abstractPreviewInvalid:
    "The selected text preview could not be verified. Choose the file again.",
  abstractSelectHelp:
    "Select the abstract passage in the text below with the mouse or keyboard. Nothing is selected automatically; your original file is not edited.",
  abstractText: "Registered source text (read only)",
  abstractSelected: "Passage selected for this task",
  abstractNothingSelected: "Select a nonempty passage to prepare a draft.",
  abstractDeclare:
    "Preparing this task declares that the selected passage is the abstract for the source shown above. This is your selection, not an automatic identity or full-text check.",
  abstractPurpose: "Purpose or question (optional)",
  abstractPrepare: "Prepare from this abstract",
  abstractPrepareNote:
    "Preparation saves a task without calling a model. Review the selected passage, then use Run explicitly to send this passage, your instructions and the packaged drafting instructions to the configured runner.",
  abstractRunner: "Last reported runner status",
  abstractCostUnknown:
    "Model context fit, token use and cost are not known here. Availability is not proof that a real draft run will succeed.",
  abstractReview: "Source-aware draft review",
  abstractBindingNote:
    "An exact quote match is not evidence that the claim follows from it. Check meaning, numbers, missing context and limitations yourself; semantic review remains pending until a human decides.",
  abstractStoredPassage:
    "Exact saved passage used by this task (not a new read or freshness guarantee):",
  abstractReturnSource: "Return to this source",
  abstractMissingPassage:
    "The saved passage is unavailable in this task response. No full-text reading or source verification is claimed.",
  abstractCandidate: "Returned candidate (not automatically accepted)",
  abstractNoCandidate:
    "No returned candidate yet. Preparing a task is not model execution.",
  abstractRunnerUnavailable:
    "The connected runner is unavailable or unknown, so Run is disabled for this draft. Return to the source to continue reading; no JSON or terminal step is required.",
  abstractOpen: "Draft from an existing abstract",
  abstractHandoffUnsupported:
    "This task was prepared for external handoff. This UI supports connected abstract drafting only; return to the source rather than entering a response as generic prose or JSON.",
  abstractTargetMissing:
    "The selected source or task is no longer present in this project. No other item was selected.",
  pollDelayed:
    "Updates are delayed. Retrying automatically; displayed data may be out of date.",
  pollStopped:
    "Updates stopped. Check the error and use Refresh to try again; displayed data may be out of date.",
  pollLastSuccess: "Last successful update:",
  writingChecks: "Manuscript checks",
  writingAuthorityNote:
    "Use the current writing authority and its editable manuscript state. Research records do not automatically overwrite that state.",
  writingAuthorityUnbound:
    "Bind the public writing adapter to initialize manuscript authority; no manuscript checks have passed yet.",
  bindManuscript: "Bind manuscript state",
  inspectImpact: "Inspect change impact",
  manuscriptBound:
    "Manuscript state bound. Inspect its reference and authority below.",
  impactUpdated: "Change-impact report updated.",
  authorityStatePath: "Authority state reference",
  authorityState: "Inspect current authority state",
  runWritingCheck: "Run manuscript check",
  writingCheck: "Check",
  candidatePath: "Candidate path (optional)",
  candidatePathHint:
    "Relative path inside this workspace, when required by the selected check.",
  checkState: "State",
  checkConsistency: "Consistency",
  checkProse: "Prose",
  checkCandidate: "Candidate",
  checkDocx: "DOCX",
  auditScopeNote:
    "Checks use the scientific-writing adapter. A report does not grant semantic acceptance.",
  auditUpdated: "Manuscript report updated. Inspect its findings below.",
  auditReport: "Manuscript check report",
  auditFindings: "Findings require attention",
  auditChecksPassed: "Adapter checks passed",
  semanticNotPerformed: "Semantic acceptance was not performed.",
  checkExitCode: "Check exit code",
  adapterFingerprint: "Writing adapter SHA-256",
  impactReport: "Change-impact report",
  impactScopeNote:
    "Changes are not synchronized semantically. Review affected records and any acceptance that is no longer current.",
  affectedRecords: "Affected records",
  noImpacts: "No affected records reported.",
  staleAcceptance: "Acceptance requiring review",
  acceptanceStale: "Acceptance is no longer current",
  noStaleTasks: "No stale task acceptance reported.",
  proposalDelivery: "Local proposal delivery",
  deliveryScopeNote:
    "This local ZIP hands off accepted proposals. It does not authorize publication or certify that every manuscript release check has passed.",
  deliverySelectionNote:
    "Select human-accepted tasks with candidate files. Preparing a bundle does not approve or create it.",
  acceptedCandidates: "Accepted candidate tasks",
  noAcceptedCandidates:
    "No eligible candidate files yet. Only human-accepted files whose latest revision check is current are selectable here.",
  deliveryFreshnessBlocked:
    "Changed or unverified candidates are not selectable. See each task's revision check; refresh missing checks or review the intended revision before preparing a new task.",
  taskRevisionCheck: "Input and output revision check",
  taskRevisionCurrent: "Matches prepared revisions",
  taskRevisionStale: "Revision changed",
  taskRevisionUnknown: "Revision not verified",
  taskRevisionCurrentNote:
    "The latest response matches the prepared revisions. This is not scientific validation or new human approval; the server still checks inputs and candidate files before delivery.",
  taskRevisionStaleNote:
    "An input or candidate no longer matches the prepared revision. Review the intended version before preparing a new task; this candidate cannot be selected for delivery.",
  taskRevisionUnknownNote:
    "The latest response does not verify the input and candidate revisions. Refresh to check again; unverified candidates cannot be selected for delivery.",
  taskRevisionHistoricalAcceptance:
    "Previous human acceptance applies to the reviewed revision, not to changed or unavailable files. The decision history is preserved.",
  selectAcceptedTask:
    "Select at least one currently accepted task with candidate files.",
  prepareDelivery: "Prepare local bundle",
  deliveryPrepared: "Local bundle prepared for human review.",
  proposalBundle: "Accepted-proposal bundle",
  deliveryPacket: "Inspect bundle contents",
  deliveryApproved: "Approved to create bundle",
  deliveryPending: "Pending local action",
  deliveryComplete: "Local bundle created",
  chooseOutcome: "Choose an outcome",
  approveLocalBundle: "Approve local bundle",
  cancelDelivery: "Cancel bundle",
  createLocalBundle: "Create approved local ZIP",
  inspectDeliveryReceipt: "Inspect execution receipt",
  deliveryExecutionUpdated:
    "Local bundle action updated. Inspect its status and receipt.",
  deliveryReconciled:
    "Execution outcome reconciled. Inspect the receipt below.",
  deliveryReceipt: "Local execution receipt",
  localReceiptNote:
    "The receipt identifies a local file. Private workspace files are not served for download.",
  receiptVerifiedAt: "Receipt verified at",
  taskRecovery: "Interrupted-run recovery",
  taskRecoveryNote:
    "Use after a suspected server restart to inspect the interrupted task. Recovery is an explicit action; work is never replayed automatically.",
  inspectInterruptedRun: "Inspect interrupted run",
  taskCancelled: "Task cancelled.",
  recoveryInspected: "Recovery inspected. Review the updated task state.",
  app: "Research Hub",
  workspace: "Researcher workspace",
  local: "LOCAL WORKSPACE",
  overview: "Overview",
  literature: "Literature",
  evidence: "Evidence",
  design: "Design & results",
  manuscript: "Manuscript",
  review: "Review & delivery",
  overviewSubtitle: "A clear view of your question, evidence, and next step.",
  literatureSubtitle: "Discover sources. Record what belongs, and why.",
  evidenceSubtitle: "Connect each claim to its sources and its limits.",
  designSubtitle: "Make the reasoning behind your results inspectable.",
  manuscriptSubtitle: "Build the argument before you build the prose.",
  reviewSubtitle:
    "Inspect agent work, resolve comments, and record your decision.",
  projects: "Projects",
  project: "Project",
  newProject: "New project",
  createProject: "Create project",
  cancel: "Cancel",
  title: "Title",
  projectId: "Project ID",
  projectIdHint: "A short identifier, such as river-adaptation.",
  archetype: "Research approach",
  empirical: "Empirical research",
  reviewStudy: "Literature review",
  goal: "Research goal",
  startTitle: "Give your research a home.",
  startBody:
    "Create a project to bring your question, literature, evidence, and manuscript into one connected workspace.",
  startEyebrow: "FROM QUESTION TO CONTRIBUTION",
  chooseProject: "Choose a project",
  noProject: "No project selected",
  skip: "Skip to main content",
  navigation: "Research workspace navigation",
  language: "Interface language",
  refresh: "Refresh",
  retry: "Try again",
  loading: "Loading your workspace…",
  loadError: "Workspace could not be loaded.",
  refreshRetained:
    "Refresh failed. Showing the last known state of this project; it may be out of date. Pending inputs and uncertain actions are retained, not retried.",
  refreshError:
    "Your action was saved, but the view could not refresh. Refresh to see the latest state.",
  errorHelp: "Your entries are still here. Check the message and try again.",
  saved: "Saved to this project.",
  saving: "Saving…",
  dismiss: "Dismiss message",
  nextStep: "YOUR NEXT STEP",
  researchQuestion: "Research question",
  noQuestion: "Start with the question your work should answer.",
  addQuestion: "Record question",
  question: "Question",
  projectBrief: "Project brief",
  noGoal: "No research goal recorded.",
  workbench: "At the workbench",
  recentActivity: "Task activity",
  noTasks:
    "No tasks yet. Prepare a task when you are ready to involve an agent.",
  readiness: "Workspace readiness",
  setupSnapshot: "Saved setup observations",
  snapshotScope:
    "Local saved snapshot, not live verification. Current readiness remains unknown. This snapshot field adds no setup, login or network probes. Existing capability checks are separate.",
  snapshotMissing: "No saved snapshot",
  snapshotInvalid: "Snapshot unavailable or invalid",
  snapshotClockSkew:
    "Snapshot timestamp is in the future; observations withheld",
  snapshotStale: "Old snapshot; observations withheld",
  snapshotSaved: "Historical observations only",
  snapshotObserved: "Observed at",
  snapshotWindow:
    "Display-age limit (seconds, not a capability validity guarantee)",
  snapshotNext:
    "To save a new observation, explicitly run research-hub setup --autonomous --save-report --vault <workspace-root> in a terminal. That command may probe Zotero; refreshing this page does not.",
  snapshotEnvironment: "Required environment presence",
  snapshotVault: "Vault filesystem checks",
  snapshotZotero: "Zotero read probe",
  snapshotNlm: "NotebookLM authentication",
  snapshotCli: "Model CLI invocation",
  snapshotSkills: "Host skill discovery",
  snapshotPassed: "Reported pass (historical)",
  snapshotFailed: "Reported failure (historical)",
  snapshotCancelled: "Cancelled (historical)",
  snapshotSkipped: "Skipped (historical)",
  snapshotUnknown: "Unknown",
  available: "available",
  unavailable: "unavailable",
  codex: "Codex connection",
  writing: "Writing support",
  approval: "Human approval",
  protection: "Protection scope",
  sourceCount: "sources",
  claimCount: "claims",
  artifactCount: "files",
  taskCount: "tasks",
  records: "Research records",
  sources: "Source library",
  noSources:
    "No sources recorded. Search for literature or add a source you already use.",
  source: "Source",
  search: "Search literature",
  searchQuery: "Search question or keywords",
  searchAction: "Find sources",
  searching: "Searching…",
  searchResults: "Search results",
  noResults:
    "No results for this search. Try more specific keywords or add a source manually.",
  addSource: "Record source",
  locator: "URL or source locator",
  doi: "DOI (optional)",
  identity: "Identity",
  unverified: "Unverified",
  openSource: "Open source",
  screening: "Screening decisions",
  screenSource: "Record screening decision",
  sourceId: "Source ID",
  decision: "Decision",
  include: "Include",
  exclude: "Exclude",
  rationale: "Rationale",
  noScreening:
    "No screening decisions. Record inclusion or exclusion with a reason.",
  sourceHelp: "Select a recorded source to retain a traceable decision.",
  claims: "Claim–evidence ledger",
  addClaim: "Record claim",
  claim: "Claim",
  uncertainty: "Uncertainty or limitation",
  sourceIds: "Supporting source IDs",
  sourceIdsHelp:
    "Choose the sources that support this claim. Leave blank when evidence is still missing.",
  noClaims:
    "No claims recorded. Add a claim, connect its sources, and state its uncertainty.",
  unsupported: "No supporting sources recorded",
  analysis: "Analysis log",
  addAnalysis: "Record analysis",
  method: "Method",
  result: "Result",
  limitation: "Limitation",
  noAnalysis:
    "No analyses recorded. Capture the question, method, result, and what the result cannot establish.",
  artifacts: "Project files",
  registerArtifact: "Register existing file",
  filePath: "Path inside workspace",
  filePathHint:
    "Enter the path of an existing file in the selected workspace. Its original bytes are not uploaded.",
  fileRole: "File role",
  main_manuscript: "Main manuscript",
  figure: "Figure",
  table: "Table",
  supplement: "Supplement",
  reviewer_response: "Reviewer response",
  noArtifacts:
    "No files registered. Link an existing workspace file to make its role and fingerprint inspectable.",
  current: "Current",
  changed: "Changed",
  fingerprint: "SHA-256 fingerprint",
  argument: "Argument outline",
  addOutline: "Add outline section",
  section: "Section",
  function: "Function in the argument",
  bridge: "Bridge to the next section",
  noOutline:
    "No outline sections. Define each section’s purpose, claim, evidence, and bridge before drafting.",
  manuscriptState: "Manuscript record",
  workflowState: "Workflow record",
  inspect: "Inspect record",
  noManuscript:
    "No manuscript record yet. Register your main manuscript or prepare an outline task.",
  prepareTask: "Prepare agent task",
  operation: "Operation",
  mode: "Execution mode",
  handoff: "Host handoff",
  connected: "Connected Codex",
  instructions: "Instructions and acceptance criteria",
  taskHelp:
    "Preparing a task does not start an agent. You will choose when to run it or download a handoff packet.",
  createTask: "Prepare task",
  frame: "Frame the question",
  outline: "Build an outline",
  draft: "Draft a section",
  revise: "Revise the work",
  rebuttal: "Prepare a response",
  synthesize: "Synthesize evidence",
  audit: "Audit evidence",
  reviewOperation: "Review the work",
  frameHint: "Clarify the question, scope, and expected contribution.",
  synthesizeHint:
    "Bring your sources into a traceable account of what is known.",
  outlineHint: "Turn evidence into a sequence of claims and sections.",
  draftHint: "Develop prose from your recorded outline and evidence.",
  reviewHint:
    "Check the manuscript against its evidence and your acceptance criteria.",
  ready: "Ready to run",
  running: "Running",
  awaiting_agent: "Awaiting agent",
  awaiting_human: "Awaiting human review",
  accepted: "Accepted by human",
  failed: "Failed",
  cancelled: "Cancelled",
  declined: "Declined",
  revision_requested: "Revision requested",
  pending: "Prepared",
  queued: "Queued",
  prepared: "Prepared",
  completed: "Accepted by human",
  blocked: "Blocked",
  executionNote:
    "Execution completion is not research acceptance. Inspect the output and record a human decision.",
  taskDetails: "Task details",
  actionHash: "Action fingerprint",
  taskOutput: "Returned output",
  taskDiagnostics: "Execution diagnostics and local log paths",
  noOutput: "No output has been returned for this task.",
  runTask: "Run connected task",
  downloadHandoff: "Download handoff packet",
  handoffDownloaded:
    "Handoff packet downloaded. The task is still awaiting an agent.",
  importResult: "Import host output",
  prose: "Agent output",
  outputStatus: "Execution outcome",
  completedOption: "Completed",
  failedOption: "Failed",
  outputArtifacts: "Output files (optional)",
  outputArtifactsHelp:
    "One candidate file per line: path | SHA-256. Use a new path inside this workspace, never an original file path.",
  invalidArtifacts:
    "Each output file needs a path and a 64-character SHA-256 fingerprint, separated by |.",
  importAction: "Import for human review",
  importHelp:
    "Imported output awaits human review; it is never accepted automatically.",
  humanDecision: "Human decision",
  actor: "Reviewer name",
  outcome: "Outcome",
  accept: "Accept",
  decline: "Decline",
  requestRevision: "Request revision",
  cancelTask: "Cancel task",
  recordDecision: "Record decision",
  approvalUnavailable:
    "Enable local human approval to record a decision here, or use the interactive CLI command below.",
  comments: "Review comments",
  addComment: "Record review comment",
  comment: "Comment",
  severity: "Severity",
  minor: "Minor",
  major: "Major",
  critical: "Critical",
  noComments:
    "No review comments recorded. Capture a specific concern and its severity.",
  status: "Status",
  OPEN: "Open",
  CLOSED: "Closed",
  RESOLVED: "Resolved",
  warnings: "Needs attention",
  preparing: "Preparing…",
  required: "required",
  taskCreated: "Task prepared. Choose Run or Download handoff when ready.",
  runStarted: "Task run requested. Review its status below.",
  resultImported: "Output imported for human review.",
  decisionSaved: "Human decision recorded.",
  inputHash: "Input fingerprint from the handoff packet",
  inputHashHelp:
    "Paste the 64-character input_hash from the packet used by the agent. This binds the output to that specific request.",
  browseEvidence: "Inspect evidence",
  viewReview: "Open review & delivery",
  viewLiterature: "Explore literature",
  noCapability: "Not reported",
};
export type MessageKey = keyof typeof en;
export const zhTW: Record<MessageKey, string> = {
  sourceLocallySaved: "本機儲存時間",
  sourceUnverifiedFile: "來源連結未核實",
  recoveryPark: "暫擱結果未明的請求…",
  recoveryParkConfirm: "保留未明請求身分並暫擱",
  recoveryParkWarning:
    "暫擱不是取消伺服器請求，也不代表儲存失敗。副本或任務仍可能稍後出現。請繼續查詢這個確切請求，不要把相同意圖另送成新請求。",
  recoveryParked: "已在本機暫擱；結果另行顯示。請求未被取消，也未重送。",
  recoverySeparate: "另起一個獨立意圖",
  recoveryParkSessionWarning:
    "暫擱狀態無法保存供重開使用。是否僅在本次工作階段繼續？重開後可能再次被原本未明的請求阻擋。",
  recoveryParkSession: "僅在本次工作階段暫擱",
  abstractRestoreBlocked:
    "未重新開啟精確副本：準備結果仍鎖定，或目前連結無法確認。未重設選取內容或未決狀態；變更來源前請先檢查待處理任務。",
  intakeAdd: "加入現有文字",
  intakeScopeNote:
    "將現有文字儲存成 Hub 管理的本機副本（最多 40,000 UTF-8 位元組），不改動原檔。不讀取 PDF、不呼叫模型、不驗證身分，也不寫入外部整合。",
  intakeInput: "文字輸入方式",
  intakePasteMode: "貼上摘要或文字",
  intakeFileMode: "選擇 .txt 或 .md 檔",
  intakeTitle: "文字標題",
  intakeLocator: "出版來源或位置（選填）",
  intakeLocatorNote:
    "來源位置是未驗證的中繼資料，不會連線讀取；留空時標示為本機文字，不冒充出版連結。",
  intakeDeclaredScope: "聲明涵蓋範圍",
  intakeScopeUnknown: "範圍未知或混合文字",
  intakeScopeAbstract: "這份內容是摘要",
  intakePaste: "貼上摘要或文字",
  intakePasteNote:
    "貼上會由此欄位建立新文字，不宣稱保留原剪貼簿或檔案位元組，不會截斷內容。",
  intakeFile: "現有 UTF-8 文字檔",
  intakeFileNote:
    "僅接受嚴格 UTF-8 的 .txt 或 .md，最多 40,000 位元組。保留原始位元組（含 BOM 與換行）；此預覽不能編輯。",
  intakeBytes: "位元組",
  intakeLocalPreview: "選取檔案預覽（尚未儲存）",
  intakeSave: "儲存 Hub 文字副本",
  intakeUnavailable:
    "此伺服器或平台目前不能儲存新文字副本；仍可使用僅含中繼資料的來源及已註冊文字閱讀。此實作尚不支援 Windows 文字加入。",
  intakeMetadataInvalid:
    "請填寫非空標題及選填來源位置，各最多 2,000 個 Unicode 字元，不接受無效 Unicode。",
  intakeFileRequired: "請先選擇有效的文字檔。",
  intakeRecoveryTitle: "找回已存文字",
  intakeRecoveryBound:
    "僅查詢文字加入的精確身分，每次進入專案最多自動查三項，不從請求鍵重建來源內容，也不執行模型。",
  intakePendingItem: "本機文字儲存",
  intakeFound:
    "此請求的來源與證據副本已保存。可開啟連結文字；不準備或執行任務，也不標記來源已審閱。",
  intakeNotObserved:
    "目前尚未看到已提交的文字儲存；先前請求仍可能完成或留下未註冊副本。這不代表失敗，請勿另建替代請求。",
  intakePendingUnknown:
    "此文字儲存結果仍未知。保留精確身分，不猜測來源、不自動重送，也不另建請求。",
  intakeCheck: "查詢已存文字",
  intakeRetrySame: "重送同一文字儲存請求",
  intakeNoPayload:
    "此工作階段已無原始輸入，只能唯讀查詢；無法由請求鍵重建文字與中繼資料。",
  intakeOpenSaved: "開啟已存文字",
  intakeStorageUnavailable:
    "瀏覽器儲存空間不可用，只能在本工作階段保留文字儲存身分；重新載入或關閉可能無法找回。不在瀏覽器儲存標題、來源位置、檔名或文字。",
  intakeStorageConfirm:
    "因無法保存身分，文字尚未送出。可明確選擇僅限本工作階段恢復，或取消這筆未送出的請求。",
  intakeSessionOnly: "僅以本工作階段恢復儲存",
  intakeSavingLeave:
    "正在儲存本機副本；可離開，但未完成請求仍可能完成。未執行模型。",
  intakeSavedUnavailable:
    "來源與副本已註冊，但已存位元組目前過期或無法讀取。不重建或修復文字；選取摘要前請重新確認證據。",
  intakeResolveFirst:
    "請先透過恢復控制項處理未決文字儲存，再開始新請求；仍可閱讀及進行其他工作。",
  intakeLocalLocator: "已存本機文字，未提供出版來源位置。",
  abstractSelectEntire: "將全文選為摘要",

  prepareRecoveryTitle: "找回已準備任務",
  prepareRecoveryBound:
    "只查詢已保存的精確請求身分。每次進入專案最多自動查詢三項；其餘查詢與同請求重送均須明確操作，不會呼叫模型。",
  preparePendingItem: "摘要準備請求",
  prepareFound:
    "已確認此請求保存的原任務。可開啟同一任務；恢復操作不另建替代任務，也不啟動執行。",
  prepareNotObserved:
    "目前尚未看到已保存的準備結果。先前請求仍可能完成；這不代表失敗，也不表示可以另建新請求。",
  preparePendingUnknown:
    "此精確請求的結果仍未知。保留其身分，不猜測任務，也不自動重送。",
  prepareCheck: "查詢已保存準備結果",
  prepareRetrySame: "重送同一準備請求",
  prepareNoPayload:
    "此工作階段已無原始輸入，只能唯讀查詢；不重建或送出推測的內容。",
  prepareOpenRecovered: "開啟找回的任務",
  prepareLegacyFallback:
    "此後端未提供相容的準備恢復能力。準備操作沿用原本無請求鍵的路徑；回應遺失時，此介面無法提供持久恢復，不宣稱保證找回。",
  prepareResolveFirst:
    "此專案仍有結果未明的準備請求。請先使用恢復控制項，不要另開新請求；仍可閱讀或進行其他工作。",
  prepareStorageUnavailable:
    "瀏覽器儲存空間不可用，只能在目前工作階段保留請求身分；重新載入或關閉後可能無法自動找回。不儲存來源文字、指示或憑證。",
  prepareStorageConfirm:
    "因無法在瀏覽器保存身分，此請求尚未送出。可選擇僅限本工作階段的恢復，或不送出並繼續其他工作。",
  prepareSessionOnly: "僅以本工作階段恢復準備任務",
  returnScope: "目前所選專案已保存的工作：",
  returnNotResume:
    "此處是已保存的專案狀態，不代表已保存閱讀位置或上次瀏覽的專案。",
  returnPending: "待查看任務",
  returnAccepted: "人工已接受任務紀錄",
  returnAcceptanceNote:
    "接受紀錄、候選產物目前是否可交付、交付結果是不同狀態。採取動作前，請開啟任務檢視目前檢查結果。",
  returnTaskUpdated: "任務最後更新",
  returnUnknown: "未知／未記錄",
  returnOpenTask: "開啟任務",
  returnBoundedTasks:
    "最多顯示最近更新的五項任務。開啟審查與交付可查看全部任務，包括較早的未完成工作。",
  returnEmpty:
    "尚無已保存任務。可至文獻新增來源紀錄或搜尋書目；登錄來源不代表已閱讀全文。",
  returnLocalBundles: "已保存的本機封裝狀態",
  returnDeliveryScope:
    "這些動作只建立本機 ZIP，不表示已送達 Zotero、Obsidian 或 NotebookLM；此處無從確認外部交付。",
  returnBundleReview: "本機封裝等待人工審查",
  returnNoReceipt: "未記錄本機收據，不代表成功或失敗；重試前請先檢視動作。",
  returnNoBundles: "尚無本機封裝動作紀錄；不影響已接受的內容。",
  returnReceiptHistory: "僅為最後記錄的收據；開啟本頁並未重新核驗該檔案。",
  returnBoundedBundles:
    "最多顯示最近建立的五項本機封裝動作；不是最後交付或外部同步時間軸。",
  returnInspectBundles: "檢視本機封裝動作",
  returnOverview: "返回專案總覽",
  returnTargetMissing:
    "所選任務已不在此專案中。請檢視更新後的專案狀態；未替您選取其他任務。",
  abstractPreparingLeave:
    "準備請求進行中。離開此來源不會取消保存；再次送出前，請先查看原專案的任務。",
  abstractPrepareUncertain:
    "準備任務的回應無法確認是否已保存，請勿盲目重送。可開啟審查並重新整理既有任務；未自動配對任何任務，也未自動重試。",
  abstractPreparedKnown: "此任務已保存。請開啟已準備的任務，避免重複建立。",
  abstractOpenPrepared: "開啟已準備任務",
  abstractReviewExisting: "查看既有任務",
  abstractRunUncertain:
    "執行回應不確定，此任務可能已啟動。請重新整理並檢視同一任務；仍顯示準備狀態不代表疑慮已解除，執行按鈕仍維持鎖定。未自動重試模型呼叫。",
  "paper-abstract-draft": "僅依摘要起草",
  abstractIdentity:
    "出版來源身分未驗證，出版版本未知。選擇紀錄與檔案，不代表已核實兩者屬於同一來源。",
  abstractScope:
    "僅從所選摘要進行限定起草：不檢索、不讀 PDF、不執行完整 skill CLI 流程、不寫入外部工具，也未獨立查核語意。",
  abstractNoText:
    "目前沒有已登錄的證據文字。此路徑僅支援既有 UTF-8 .md／.txt 證據，不支援 PDF 或僅有書目。仍可開啟來源連結及管理紀錄；離開此步驟不必另製摘要檔。",
  abstractChooseFile: "選擇既有證據文字",
  abstractChooseFilePlaceholder: "選擇已登錄的文字檔",
  abstractReadText: "讀取所選已保存文字",
  abstractPreviewInvalid: "無法確認所選文字預覽，請重新選擇檔案。",
  abstractSelectHelp:
    "用滑鼠或鍵盤在下方文字選取摘要段落。不自動選取全文，也不修改原檔。",
  abstractText: "已登錄來源文字（唯讀）",
  abstractSelected: "本次任務選取的段落",
  abstractNothingSelected: "請選取非空白段落，再準備草稿。",
  abstractDeclare:
    "準備任務表示您將所選段落指定為上方來源的摘要。這是您的選擇，不是自動身分核驗或全文檢查。",
  abstractPurpose: "用途或問題（選填）",
  abstractPrepare: "依此摘要準備任務",
  abstractPrepareNote:
    "準備只保存任務，不呼叫模型。核對所選段落後，再明確按執行，才將該段落、您的指示與套件內的起草指示送給已設定的執行器。",
  abstractRunner: "最後回報的執行器狀態",
  abstractCostUnknown:
    "此處無從確認模型上下文容量、token 用量及費用；顯示可用不代表真實起草一定成功。",
  abstractReview: "對照來源審查草稿",
  abstractBindingNote:
    "引文逐字吻合不代表支持該主張。請自行核對語意、數值、缺漏脈絡與限制；語意審查須由人作出決定。",
  abstractStoredPassage:
    "此任務實際使用的已保存段落（不是重新讀取或現況保證）：",
  abstractReturnSource: "返回此來源",
  abstractMissingPassage:
    "此任務回應沒有已保存段落；不宣稱已閱讀全文或核驗來源。",
  abstractCandidate: "返回的候選草稿（未自動接受）",
  abstractNoCandidate: "尚無返回的候選草稿；準備任務不等於模型已執行。",
  abstractRunnerUnavailable:
    "連線執行器不可用或狀態未知，因此此草稿的執行按鈕停用。可返回來源繼續閱讀，不要求另貼 JSON 或操作終端機。",
  abstractOpen: "從既有摘要起草",
  abstractHandoffUnsupported:
    "此任務原先為外部交接準備。目前介面只支援連線摘要起草；請返回來源，不必將回應改貼為一般文字或 JSON。",
  abstractTargetMissing: "所選來源或任務已不在此專案中，未替您選取其他項目。",
  pollDelayed: "更新延遲，正在自動重試；目前顯示的資料可能已過時。",
  pollStopped:
    "更新已停止。請檢查錯誤，再按重新整理重試；目前顯示的資料可能已過時。",
  pollLastSuccess: "上次成功更新：",
  writingChecks: "論文檢查",
  writingAuthorityNote:
    "使用目前的寫作規範來源與可編輯的論文狀態。研究紀錄不會自動覆寫該狀態。",
  writingAuthorityUnbound:
    "請連結公開寫作介接器，建立稿件的正式狀態來源；目前尚無任何稿件檢查通過。",
  bindManuscript: "連結論文狀態",
  inspectImpact: "檢視變更影響",
  manuscriptBound: "已連結論文狀態。請檢視下方的參照與規範來源。",
  impactUpdated: "已更新變更影響報告。",
  authorityStatePath: "規範狀態參照",
  authorityState: "檢視目前規範狀態",
  runWritingCheck: "執行論文檢查",
  writingCheck: "檢查項目",
  candidatePath: "候選檔案路徑（選填）",
  candidatePathHint: "所選檢查需要候選檔案時，請填入工作空間內的相對路徑。",
  checkState: "狀態",
  checkConsistency: "一致性",
  checkProse: "文字",
  checkCandidate: "候選稿",
  checkDocx: "DOCX",
  auditScopeNote: "檢查使用科學寫作介接器。報告本身不代表語意內容已通過驗收。",
  auditUpdated: "已更新論文檢查報告。請檢視下方結果。",
  auditReport: "論文檢查報告",
  auditFindings: "檢查發現需要處理的問題",
  auditChecksPassed: "介接器檢查通過",
  semanticNotPerformed: "尚未執行語意內容驗收。",
  checkExitCode: "檢查結束碼",
  adapterFingerprint: "寫作介接器 SHA-256",
  impactReport: "變更影響報告",
  impactScopeNote:
    "變更不會自動進行語意同步。請檢視受影響的紀錄，以及已不適用於目前版本的驗收。",
  affectedRecords: "受影響的紀錄",
  noImpacts: "未回報受影響的紀錄。",
  staleAcceptance: "需要重新檢視的驗收",
  acceptanceStale: "驗收已不適用於目前版本",
  noStaleTasks: "未回報過期的任務驗收。",
  proposalDelivery: "本機提案交付",
  deliveryScopeNote:
    "此本機 ZIP 用於交接已接受的提案，不代表發表授權，也不證明論文已通過所有發布檢查。",
  deliverySelectionNote:
    "選擇已經人工接受且包含候選檔案的任務。準備封裝不會自動核准或建立檔案。",
  acceptedCandidates: "已接受的候選任務",
  noAcceptedCandidates:
    "尚無符合條件的候選檔案。只有人工已接受，且最近一次版本檢查確認一致的檔案，才可在此選取。",
  deliveryFreshnessBlocked:
    "版本已變更或未確認的候選檔案不可選取。請查看各任務的版本檢查；缺少結果時可重新整理，版本變更時先確認預期版本，再準備新任務。",
  taskRevisionCheck: "輸入與產出版本檢查",
  taskRevisionCurrent: "與準備時的版本一致",
  taskRevisionStale: "版本已變更",
  taskRevisionUnknown: "版本尚未確認",
  taskRevisionCurrentNote:
    "最近一次回應顯示版本與準備時一致。這不代表科學內容已驗證，也不是新增的人工核准；交付前伺服器仍會檢查輸入與候選檔案。",
  taskRevisionStaleNote:
    "輸入或候選檔案已不符合準備時的版本。請先確認預期版本再準備新任務；此候選檔案目前不可選取交付。",
  taskRevisionUnknownNote:
    "最近一次回應未能確認輸入與候選檔案版本。可重新整理再檢查；尚未確認的候選檔案不可選取交付。",
  taskRevisionHistoricalAcceptance:
    "先前的人工接受只適用於當時審閱的版本，不適用於已變更或無法取得的檔案；原決策紀錄仍會保留。",
  selectAcceptedTask: "請至少選擇一項目前已接受且包含候選檔案的任務。",
  prepareDelivery: "準備本機封裝",
  deliveryPrepared: "本機封裝已準備，等待人工審閱。",
  proposalBundle: "已接受提案封裝",
  deliveryPacket: "檢視封裝內容",
  deliveryApproved: "已核准建立封裝",
  deliveryPending: "等待本機操作",
  deliveryComplete: "已建立本機封裝",
  chooseOutcome: "選擇結果",
  approveLocalBundle: "核准本機封裝",
  cancelDelivery: "取消封裝",
  createLocalBundle: "建立已核准的本機 ZIP",
  inspectDeliveryReceipt: "檢視執行收據",
  deliveryExecutionUpdated: "已更新本機封裝操作。請檢視狀態與收據。",
  deliveryReconciled: "已核對執行結果。請檢視下方收據。",
  deliveryReceipt: "本機執行收據",
  localReceiptNote: "收據記錄本機檔案位置。私人工作空間檔案不提供網頁下載。",
  receiptVerifiedAt: "收據驗證時間",
  taskRecovery: "中斷任務復原",
  taskRecoveryNote:
    "懷疑伺服器重新啟動後，可用此功能檢視中斷任務。復原須明確操作，不會自動重跑工作。",
  inspectInterruptedRun: "檢視中斷的執行",
  taskCancelled: "任務已取消。",
  recoveryInspected: "已檢視復原狀態。請確認更新後的任務狀態。",
  app: "Research Hub",
  workspace: "研究工作空間",
  local: "本機工作空間",
  overview: "研究總覽",
  literature: "文獻",
  evidence: "證據",
  design: "設計與結果",
  manuscript: "論文",
  review: "審閱與交付",
  overviewSubtitle: "掌握研究問題、證據與下一步。",
  literatureSubtitle: "尋找來源，記錄納入的文獻與理由。",
  evidenceSubtitle: "讓每項論述都連結到來源與限制。",
  designSubtitle: "讓結果背後的研究推理可供檢視。",
  manuscriptSubtitle: "先建立論證，再發展文字。",
  reviewSubtitle: "檢視代理產出、處理意見，並記錄您的決定。",
  projects: "專案",
  project: "專案",
  newProject: "新增專案",
  createProject: "建立專案",
  cancel: "取消",
  title: "標題",
  projectId: "專案識別碼",
  projectIdHint: "簡短的識別碼，例如 river-adaptation。",
  archetype: "研究取向",
  empirical: "實證研究",
  reviewStudy: "文獻回顧",
  goal: "研究目標",
  startTitle: "讓研究有個歸屬。",
  startBody: "建立專案，將研究問題、文獻、證據與論文集中在同一個工作空間。",
  startEyebrow: "從研究問題到學術貢獻",
  chooseProject: "選擇專案",
  noProject: "尚未選擇專案",
  skip: "跳至主要內容",
  navigation: "研究工作空間導覽",
  language: "介面語言",
  refresh: "重新整理",
  retry: "再試一次",
  loading: "正在載入工作空間…",
  loadError: "無法載入工作空間。",
  refreshRetained:
    "重新整理失敗。保留此專案最後已知狀態，內容可能已過時；暫存輸入及結果不確定的操作仍保留，未自動重試。",
  refreshError: "操作已儲存，但畫面更新失敗。請重新整理以查看最新狀態。",
  errorHelp: "您輸入的內容仍保留。請檢查訊息後再試一次。",
  saved: "已儲存至此專案。",
  saving: "儲存中…",
  dismiss: "關閉訊息",
  nextStep: "您的下一步",
  researchQuestion: "研究問題",
  noQuestion: "從您希望這項研究回答的問題開始。",
  addQuestion: "記錄研究問題",
  question: "問題",
  projectBrief: "專案摘要",
  noGoal: "尚未記錄研究目標。",
  workbench: "研究工作臺",
  recentActivity: "任務動態",
  noTasks: "尚無任務。準備讓代理協助時，即可建立任務。",
  readiness: "工作空間就緒狀態",
  setupSnapshot: "已儲存的設定觀察",
  snapshotScope:
    "這是本機儲存快照，不是即時驗證。目前是否就緒仍未知；此快照欄位不新增設定、登入或網路探測，既有能力檢查另計。",
  snapshotMissing: "沒有已儲存快照",
  snapshotInvalid: "快照無法使用或格式無效",
  snapshotClockSkew: "快照時間在未來；不顯示觀察結果",
  snapshotStale: "快照已舊；不顯示觀察結果",
  snapshotSaved: "僅為歷史觀察",
  snapshotObserved: "觀察時間",
  snapshotWindow: "顯示時間門檻（秒，不保證能力仍有效）",
  snapshotNext:
    "若要儲存新觀察，請在終端機明確執行 research-hub setup --autonomous --save-report --vault <workspace-root>。該命令可能探測 Zotero；重新整理此頁不會。",
  snapshotEnvironment: "必要環境變數是否存在",
  snapshotVault: "Vault 檔案系統檢查",
  snapshotZotero: "Zotero 讀取探測",
  snapshotNlm: "NotebookLM 登入效力",
  snapshotCli: "模型 CLI 實際呼叫",
  snapshotSkills: "主機技能發現",
  snapshotPassed: "曾回報通過（歷史）",
  snapshotFailed: "曾回報失敗（歷史）",
  snapshotCancelled: "曾取消（歷史）",
  snapshotSkipped: "曾略過（歷史）",
  snapshotUnknown: "未知",
  available: "可使用",
  unavailable: "目前無法使用",
  codex: "Codex 連線",
  writing: "寫作支援",
  approval: "人工核准",
  protection: "保護範圍",
  sourceCount: "個來源",
  claimCount: "項論述",
  artifactCount: "個檔案",
  taskCount: "項任務",
  records: "研究紀錄",
  sources: "來源文獻庫",
  noSources: "尚無來源。請搜尋文獻，或記錄您已使用的來源。",
  source: "來源",
  search: "搜尋文獻",
  searchQuery: "研究問題或關鍵字",
  searchAction: "尋找來源",
  searching: "搜尋中…",
  searchResults: "搜尋結果",
  noResults: "此次搜尋沒有結果。請嘗試更精確的關鍵字，或手動記錄來源。",
  addSource: "記錄來源",
  locator: "網址或來源位置",
  doi: "DOI（選填）",
  identity: "來源身分",
  unverified: "尚未驗證",
  openSource: "開啟來源",
  screening: "文獻篩選決定",
  screenSource: "記錄篩選決定",
  sourceId: "來源識別碼",
  decision: "決定",
  include: "納入",
  exclude: "排除",
  rationale: "理由",
  noScreening: "尚無篩選決定。請記錄納入或排除的理由。",
  sourceHelp: "選擇已記錄的來源，保留可追溯的篩選決定。",
  claims: "論述與證據紀錄",
  addClaim: "記錄論述",
  claim: "論述",
  uncertainty: "不確定性或限制",
  sourceIds: "支持來源識別碼",
  sourceIdsHelp: "選擇支持此論述的來源。若仍缺乏證據，可留白。",
  noClaims: "尚無論述。請新增論述、連結來源，並註明不確定性。",
  unsupported: "尚未記錄支持來源",
  analysis: "分析紀錄",
  addAnalysis: "記錄分析",
  method: "方法",
  result: "結果",
  limitation: "限制",
  noAnalysis: "尚無分析。請記錄問題、方法、結果，以及結果無法證明的部分。",
  artifacts: "專案檔案",
  registerArtifact: "登錄現有檔案",
  filePath: "工作空間內的路徑",
  filePathHint: "輸入所選工作空間中現有檔案的路徑。原始檔案內容不會上傳。",
  fileRole: "檔案用途",
  main_manuscript: "主要論文",
  figure: "圖",
  table: "表",
  supplement: "補充資料",
  reviewer_response: "審查回覆",
  noArtifacts: "尚未登錄檔案。請連結工作空間內的現有檔案，以檢視用途與指紋。",
  current: "目前版本",
  changed: "已變更",
  fingerprint: "SHA-256 指紋",
  argument: "論證大綱",
  addOutline: "新增大綱段落",
  section: "章節",
  function: "論證功能",
  bridge: "與下一節的銜接",
  noOutline: "尚無大綱。起草前，請定義各節的目的、論述、證據與銜接。",
  manuscriptState: "論文紀錄",
  workflowState: "工作流程紀錄",
  inspect: "檢視紀錄",
  noManuscript: "尚無論文紀錄。請登錄主要論文，或準備大綱任務。",
  prepareTask: "準備代理任務",
  operation: "操作",
  mode: "執行模式",
  handoff: "交接至主機代理",
  connected: "已連線的 Codex",
  instructions: "指示與驗收標準",
  taskHelp: "準備任務不會啟動代理。您可自行選擇何時執行，或下載交接封包。",
  createTask: "準備任務",
  frame: "釐清研究問題",
  outline: "建立大綱",
  draft: "起草段落",
  revise: "修訂內容",
  rebuttal: "準備審查回覆",
  synthesize: "綜整證據",
  audit: "查核證據",
  reviewOperation: "審閱內容",
  frameHint: "釐清研究問題、範圍與預期貢獻。",
  synthesizeHint: "將來源整理為可追溯的現有知識。",
  outlineHint: "將證據轉化為有順序的論述與章節。",
  draftHint: "依據已記錄的大綱與證據發展文字。",
  reviewHint: "依據證據與驗收標準檢查論文。",
  ready: "可開始執行",
  running: "執行中",
  awaiting_agent: "等待代理",
  awaiting_human: "等待人工審閱",
  accepted: "人工已接受",
  failed: "失敗",
  cancelled: "已取消",
  declined: "未接受",
  revision_requested: "已要求修訂",
  pending: "已準備",
  queued: "已排程",
  prepared: "已準備",
  completed: "人工已接受",
  blocked: "受阻",
  executionNote: "執行完成不代表研究已通過驗收。請檢視產出並記錄人工決定。",
  taskDetails: "任務詳情",
  actionHash: "操作指紋",
  taskOutput: "回傳產出",
  taskDiagnostics: "執行診斷與本機紀錄路徑",
  noOutput: "此任務尚未回傳產出。",
  runTask: "執行已連線任務",
  downloadHandoff: "下載交接封包",
  handoffDownloaded: "交接封包已下載。任務仍在等待代理。",
  importResult: "匯入主機產出",
  prose: "代理產出",
  outputStatus: "執行結果",
  completedOption: "已完成",
  failedOption: "失敗",
  outputArtifacts: "產出檔案（選填）",
  outputArtifactsHelp:
    "每行一個候選檔案：路徑 | SHA-256。請使用工作空間內的新路徑，勿使用原始檔案路徑。",
  invalidArtifacts:
    "每個產出檔案都需要路徑與 64 字元的 SHA-256 指紋，並以 | 分隔。",
  importAction: "匯入並等待人工審閱",
  importHelp: "匯入的產出會等待人工審閱，不會自動接受。",
  humanDecision: "人工決定",
  actor: "審閱者姓名",
  outcome: "結果",
  accept: "接受",
  decline: "不接受",
  requestRevision: "要求修訂",
  cancelTask: "取消任務",
  recordDecision: "記錄決定",
  approvalUnavailable:
    "請啟用本機人工核准，或使用下方互動式 CLI 指令記錄決定。",
  comments: "審閱意見",
  addComment: "記錄審閱意見",
  comment: "意見",
  severity: "嚴重程度",
  minor: "輕微",
  major: "重大",
  critical: "關鍵",
  noComments: "尚無審閱意見。請記錄具體問題與嚴重程度。",
  status: "狀態",
  OPEN: "待處理",
  CLOSED: "已關閉",
  RESOLVED: "已解決",
  warnings: "需要注意",
  preparing: "準備中…",
  required: "必填",
  taskCreated: "任務已準備。就緒時，請選擇執行或下載交接封包。",
  runStarted: "已要求執行任務。請於下方查看狀態。",
  resultImported: "產出已匯入，等待人工審閱。",
  decisionSaved: "已記錄人工決定。",
  browseEvidence: "檢視證據",
  viewReview: "開啟審閱與交付",
  viewLiterature: "探索文獻",
  noCapability: "尚未回報",
  inputHash: "交接封包中的輸入指紋",
  inputHashHelp:
    "貼上代理所使用封包中的 64 字元 input_hash，將產出連結至該次特定請求。",
};
export const dictionaries = { en, "zh-TW": zhTW };
export type Translate = (key: MessageKey) => string;
export const translator =
  (locale: Locale): Translate =>
  (key) =>
    dictionaries[locale][key];
export function operationLabel(op: Operation): MessageKey {
  return op === "review" ? "reviewOperation" : op;
}
export function statusLabel(status: string, t: Translate): string {
  return Object.hasOwn(en, status) ? t(status as MessageKey) : status;
}
export function projectWarningLabel(warning: string, t: Translate): string {
  // Match only this stable backend notice. Unknown/extended diagnostics remain
  // verbatim, including paths and error details; the API payload is unchanged.
  return warning === en.writingAuthorityUnbound
    ? t("writingAuthorityUnbound")
    : warning;
}
export function statusTone(
  status: string,
): "good" | "warn" | "danger" | "neutral" {
  if (status === "completed" || status === "accepted") return "good";
  if (["failed", "declined", "blocked"].includes(status)) return "danger";
  if (["running", "awaiting_human", "revision_requested"].includes(status))
    return "warn";
  return "neutral";
}
export function nextOperation(detail: ProjectDetail): {
  operation: Operation;
  hint: MessageKey;
} {
  if (!detail.records.some((record) => record.kind === "question"))
    return { operation: "frame", hint: "frameHint" };
  if (!detail.records.some((record) => record.kind === "claim"))
    return { operation: "synthesize", hint: "synthesizeHint" };
  if (!detail.records.some((record) => record.kind === "outline"))
    return { operation: "outline", hint: "outlineHint" };
  if (!detail.artifacts.some((artifact) => artifact.role === "main_manuscript"))
    return { operation: "draft", hint: "draftHint" };
  return { operation: "review", hint: "reviewHint" };
}
