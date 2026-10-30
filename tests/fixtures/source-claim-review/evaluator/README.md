# Evaluator-only fixture

Do not include this directory when sending the `reviewer/` bundle for a blind
review. Directory separation is not access control. The rubric is synthetic,
not a scientific truth oracle. The included
review record was supplied by the task parent, which reported a fresh reviewer
receiving only the reviewer bundle; the fixture cannot independently establish
that isolation. Its bytes are retained as supplied, with a trailing newline.

The fixture code checks native-capture locators against the synthetic passage's
label. The production validator does not semantically interpret native-capture
locators. The source-audit test checks record and source binding, expected label
agreement, and rejection of certain inconsistent judgments. It does not decide
semantic support or establish general model accuracy or skill improvement.
