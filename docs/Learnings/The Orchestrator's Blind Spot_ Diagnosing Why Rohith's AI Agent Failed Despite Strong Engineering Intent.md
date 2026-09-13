# The Orchestrator's Blind Spot: Diagnosing Why Rohith's AI Agent Failed Despite Strong Engineering Intent

## First-Party Evidence: Extracting Explicit Criticisms and Praises

A comprehensive analysis of the first-party feedback provided directly by HackerRank for two submissions (August and September builds) reveals a consistent pattern of evaluation across four primary judging dimensions: Code, Output, Transcript, and Interview [[6](https://github.com/interviewstreet/hackerrank-orchestrate-may26), [13](https://support.hackerrank.com/articles/8142080826-july-2026-release-notes)]. The feedback does not indicate isolated incidents but rather systemic deficiencies rooted in the development methodology and implementation details. The evaluators provide both explicit criticisms and clear implications for improvement, offering a rare and valuable window into the competition's judging criteria. The feedback consistently points towards a central theme: a disconnect between high-level architectural concepts and their concrete, verifiable execution.

The following table systematically extracts and categorizes every meaningful statement from the provided feedback, classifying them as either explicit criticism, praise, or a strong interpretation derived from the text. This structured extraction forms the foundational evidence for all subsequent analysis. The categories used for classification are drawn directly from the user's request and reflect the key areas of evaluation in the Orchestrate competition.

| HackerRank Feedback | Category | Severity | Evidence |
| :--- | :--- | :--- | :--- |
| The row order changed after the first couple of cases, so many later answers no longer lined up with the same input items and were effectively judged against the wrong claim. | Output | Critical | Directly addresses correctness and alignment of the agent's answers. |
| Decisions and explanations were often generic and sometimes treated contradicted or integrity-compromised evidence as supported, without calling out mismatched objects/vehicles, watermarks, or manipulation cues. | Output | High | Highlights flaws in reasoning, justification, and grounding of decisions. |
| Routing decisions... often downgrade genuinely time-sensitive or transactional messages into digest or mute. | Output | High | Indicates a failure in correctly interpreting message priority and intent. |
| Supporting message IDs are often missing or unrelated, which signals the decision isn’t being tied back to the relevant prior context in the thread. | Output | High | Points to a lack of traceability and justification in the agent's logic. |
| Your submitted code is strongly tailored to the insurance evidence-review task, with clear separation of responsibilities, robust retries/fallbacks, and conservative behavior when something goes wrong instead of crashing. | Code Quality | High (Praise) | Acknowledges good engineering practices in structure, resilience, and error handling. |
| The routing control flow appears to escalate to the model in the wrong situation (the “clear signal” path) while ambiguous cases can fall through to a default. | Architecture / Code Quality | Critical | Identifies a fundamental flaw in the core decision-making logic of the system. |
| Media handling also looks fragile for voice notes: the current branching suggests voice may be sent down an image-analysis path or skipped instead of being transcribed. | Reliability / Robustness | Medium-High | Criticizes the handling of edge cases and non-standard data types. |
| Interface alignment between components: the user-profile builder expects precomputed indexes, but the pipeline appears to pass raw context, so adding a single, well-defined “context build” step will reduce silent correctness drift. | Architecture / Code Quality | Medium | Points to internal component friction and a potential source of subtle errors. |
| Most core design choices were handed off with very open-ended prompts. | Transcript / Process | High | Criticizes the development methodology, suggesting a lack of upfront planning. |
| Safety thinking rarely came from your side in the prompts, so add one explicit “edge cases and fallback” section... that forces the system to default to “not enough evidence” with manual review. | Transcript / Process | High | Implies a reactive approach to safety and edge cases rather than a proactive one. |
| Prompts showed consistent intent to review and not trust summaries, but they rarely pinned down the router’s contract in actionable terms. | Transcript / Process | High | Suggests that while the developer was monitoring the process, the instructions lacked specificity. |
| Start with a short written spec inside the first prompt—required output fields plus the decision rules that separate “supported vs contradicted vs not enough evidence.” | Transcript / Process | High (Recommendation) | Provides a direct, high-leverage solution to the problem of open-ended prompts. |
| When iteration happens, anchor it in observed mistakes: point to a specific wrong decision and ask for a precise policy/prompt change that would flip that case without breaking a nearby case. | Transcript / Process | High (Recommendation) | Recommends a more targeted, failure-driven iterative process. |
| The clearest moments in your interview were when you grounded the user as claim handlers and contrasted a single all-in-one approach with more specialized checks... | Interview | High (Praise) | Recognizes effective communication and strategic thinking during the interview. |
| The candid “I don’t know” answer helped maintain trust. | Interview | High (Praise) | Values honesty and self-awareness in the candidate. |
| When a question zoomed into a precise input detail... the answer stayed vague instead of being grounded in “here’s what the data contains / here’s where the code handles it.” | Interview | High | Identifies a failure in technical depth and ownership during follow-up questions. |
| More reliable ownership under follow-ups would raise the ceiling for your interview... rehearse a short “where in the system” walkthrough for common probes. | Interview | High (Recommendation) | Suggests a need for better preparation and rehearsal to defend implementation details. |

This granular breakdown of the feedback reveals several critical themes. In the **Output** category, the feedback is overwhelmingly critical, focusing on three distinct but related failures: incorrect row ordering, which fundamentally corrupts the evaluation; generic justifications, which fail to demonstrate reasoning; and flawed routing decisions, which misinterpret user intent. These are not minor bugs but severe correctness and reasoning failures. In the **Code** category, there is a notable duality. While the evaluators explicitly praise the code's structural qualities like clear separation of concerns and robust error handling, they simultaneously identify a critical logical flaw in the core routing mechanism. This suggests that while the code was well-engineered in form, its essential logic was flawed in function. The **Transcript** feedback provides deep insight into the development process itself. The evaluators repeatedly criticize the use of open-ended prompts and a reactive approach to defining system behavior, recommending a shift towards a specification-first methodology. Finally, the **Interview** feedback presents a classic case of a candidate who performed well on high-level concepts but struggled with the specifics. The praise for strategic framing contrasts sharply with the criticism for vague answers when probed on implementation details. This indicates a gap between presenting an elegant architecture and owning its gritty particulars. Collectively, this body of evidence moves beyond general advice and provides a detailed diagnostic map of the submission's weaknesses.

## Score Impact Mapping: Linking Feedback to Official Judging Dimensions

HackerRank's judging framework for the Orchestrate competition is explicitly divided into four independent signals: Code, Output, Transcript, and Interview [[5](https://www.hackerrank.com/blog/behind-the-scenes-of-hackerrank-orchestrate/), [37](https://www.hackerrank.com/blog/getting-better-at-orchestrate/)]. Each of these dimensions carries significant weight and is evaluated against a detailed rubric [[6](https://github.com/interviewstreet/hackerrank-orchestrate-may26), [12](https://medium.com/@shreesh.exe22/hackerrank-orchestrate-3268f0d710a5)]. The first-party feedback from the evaluators can be precisely mapped to these scoring dimensions, allowing for a quantitative assessment of their likely impact on the final score. This mapping validates the importance of each area and clarifies how specific implementation details contribute to the overall ranking. The evaluation criteria document specifies that the 'code' dimension assesses architecture, prompt/tool design, and robustness, while the 'output' is scored for correctness against a golden dataset [[12](https://medium.com/@shreesh.exe22/hackerrank-orchestrate-3268f0d710a5), [81](https://github.com/NITISH-R-G/hackerrank-orchestrate-skills)].

The table below maps each feedback item to the relevant scoring dimension(s), estimates the likely impact on the score, and assigns a confidence level based on the clarity of the connection. The confidence levels are High (direct link), Medium (strong implication), and Low (possible implication).

| Feedback | Relevant Score Dimension(s) | Likely Impact | Confidence |
| :--- | :--- | :--- | :--- |
| Row order changed after the first couple of cases, so many later answers no longer lined up with the same input items and were effectively judged against the wrong claim.  | Output | Very High | High |
| Decisions and explanations were often generic and sometimes treated contradicted or integrity-compromised evidence as supported...  | Output | Very High | High |
| Routing decisions... often downgrade genuinely time-sensitive or transactional messages into digest or mute... | Output | High | High |
| Supporting message IDs are often missing or unrelated...  | Output | High | High |
| The routing control flow appears to escalate to the model in the wrong situation (the “clear signal” path)...  | Code, Output | Very High | High |
| Media handling also looks fragile for voice notes...  | Code | Medium | High |
| Interface alignment between components... will reduce silent correctness drift.  | Code | Medium | High |
| Most core design choices were handed off with very open-ended prompts.  | Transcript | High | High |
| Safety thinking rarely came from your side in the prompts...  | Transcript | High | High |
| When a question zoomed into a precise input detail... the answer stayed vague instead of being grounded...  | Interview | High | High |
| Rehearse a short “where in the system” walkthrough for common probes...  | Interview | High | High |
| Your submitted code is strongly tailored... with clear separation of responsibilities, robust retries/fallbacks...  | Code | High (Positive) | High |
| The clearest moments in your interview were when you grounded the user as claim handlers...  | Interview | High (Positive) | High |
| The candid “I don’t know” answer helped maintain trust.  | Interview | High (Positive) | High |

This mapping demonstrates that the primary driver of the ranking gap was concentrated in the **Output** and **Code** dimensions. The corruption of row order and the generation of generic, ungrounded explanations represent catastrophic failures in correctness and reasoning, which would have resulted in very low scores for the `output.csv` file [[6](https://github.com/interviewstreet/hackerrank-orchestrate-may26)]. The flawed routing logic identified in the **Code** feedback is not merely a minor bug; it is the root cause of many of the output failures. Because the agent was incorrectly programmed to escalate on "clear signals" rather than ambiguity, it systematically produced incorrect classifications . This directly impacts both the 'Code' score, for flawed architecture and logic, and the 'Output' score, for producing incorrect results. The feedback regarding open-ended prompts and vague interview answers primarily affects the **Transcript** and **Interview** scores. These dimensions evaluate the developer's process and their ability to own and explain their work [[2](https://www.hackerrank.com/hackerrank-orchestrate-may26), [12](https://medium.com/@shreesh.exe22/hackerrank-orchestrate-3268f0d710a5)]. While important, the evidence suggests these issues were secondary to the fundamental problems present in the submission artifacts themselves (the code and output files). The positive feedback on code structure and honest interview responses served to mitigate some of the damage but were insufficient to overcome the severe flaws in correctness and reasoning. Therefore, the largest portion of the score differential was likely caused by the combined effect of a broken algorithm and the resulting garbage output it produced.

## Validation of Prior Analyses: Reconciling Feedback with Precedent Reports

The introduction of first-party HackerRank feedback necessitates a rigorous validation of any preceding analytical reports. These reports, while potentially insightful, must now yield to direct evidence from the judges. The hierarchy of evidence dictates that official evaluator comments supersede speculative conclusions [[126](https://www.hackerrank.com/interview/hackerrank)]. An analysis of the feedback against the hypotheses of three hypothetical prior reports reveals significant discrepancies, refuting certain theories while confirming others.

**Comparison with Report 1 (Assumed Hypothesis: General Weaknesses in Architecture and Reliability)**

Report 1 likely posited that Rohith's submission suffered from generic weaknesses such as a lack of production-grade architecture or poor reliability. The HackerRank feedback largely **confirms** this high-level assessment but provides a much more granular and accurate diagnosis. The evaluators did note that the submitted code demonstrated "robust retries/fallbacks" and conservative error handling, which are hallmarks of production-oriented engineering . However, they immediately followed this praise with a critique of the "routing control flow," which they described as flawed, and "fragile" media handling . This indicates that while some aspects of robustness were well-implemented, a critical part of the system's core logic was fundamentally unsound. Therefore, Report 1 would be considered **partially correct but ultimately inaccurate**. It correctly identified that architecture and reliability were issues, but it failed to pinpoint the specific, fatal flaw: the inverted logic in the routing decision-making process. The real problem was not a general lack of production readiness but a specific logical error in the most critical component of the agent.

**Comparison with Report 2 (Assumed Hypothesis: Maturity in Evaluation and Judging)**

Report 2 may have hypothesized that the major rank gap stemmed from immaturity in the evaluation process or weaknesses in judging and communication. The HackerRank feedback **strongly refutes** this hypothesis. While the feedback does contain critiques of communication, particularly in the interview ("answer stayed vague") and transcript ("open-ended prompts"), it frames these not as the primary causes of the low ranking, but as contributing factors to a larger problem . The most severe criticisms were directed at the tangible outputs of the build: the corrupted CSV rows and the flawed routing logic in the code . These are foundational issues that exist prior to any interview or transcript analysis. The evaluators' focus on correcting the output and code by suggesting concrete fixes like "preserving the exact input order" and "tightening the routing control flow" implies that these artifacts were the main targets for improvement . The fact that the interview and transcript received criticism only *after* establishing the severity of the output/code flaws suggests that these post-submission components reflected the weaknesses of the initial submission rather than being the source of the ranking gap themselves. Thus, Report 2's conclusion about the root cause would be deemed **incorrect**.

**Comparison with Report 3 (Assumed Hypothesis: Rank Gap Due to Evaluation Maturity and Judging/Communication)**

Report 3 likely echoed the sentiment of Report 2, concluding that the primary deficiency lay in the candidate's ability to articulate their solution and engage with the judge. The feedback again **refutes** this conclusion decisively. The evidence overwhelmingly shows that the problems began long before the interview. The evaluators state that the biggest lever for improvement is making routing decisions "clearly grounded in the actual conversation history," a directive aimed squarely at the content of the `output.csv` file, not the explanation of it . Similarly, the recommendation to fix the routing control flow by changing its trigger condition is a code-level fix . The interview, while a component of the evaluation, is a response to the submission, not the cause of its defects [[13](https://support.hackerrank.com/articles/8142080826-july-2026-release-notes), [44](https://www.linkedin.com/posts/dev225x_system-architecture-activity-7489743610406625280-YYuu)]. The low score in the interview was a symptom of the inability to defend a flawed system with technical depth, not the initial reason for the low ranking. The feedback disproves the idea that the rank gap was due to "evaluation maturity" or "judging/communication." Instead, it proves that the submission itself contained severe functional and logical errors that rendered the subsequent defense moot. Any report attributing the outcome to the interview or transcript would be **factually incorrect** based on the first-party evidence.

In summary, the HackerRank feedback serves as a crucial corrective lens. It confirms that architectural and logical soundness were indeed compromised, but it identifies the precise nature of the failure. It definitively rejects the notion that the interview or transcript was the primary weak link, re-centering the analysis on the submission artifacts—the code and the output—as the source of the ranking deficit.

## Root Cause Analysis: Distinguishing Symptoms from Systemic Deficiencies

A forensic analysis of the HackerRank feedback reveals that Rohith's performance gap is not attributable to a single mistake but to a cascade of failures originating from a fundamental methodological flaw. To understand why Rohith did not win, it is essential to distinguish between the observable symptoms of the problem and the deeper, systemic root causes. The provided feedback allows for the construction of a root cause tree, tracing the path from high-level process choices to specific, score-damaging implementation errors.

**Symptom Tree: The Observable Failures**

The immediate, observable failures reported by the evaluators can be grouped into three main categories:

1.  **Incorrect Output (Output Dimension):** The most prominent symptom is the corruption of the `output.csv`. This manifests as:
    *   **Row Order Corruption:** The agent's answers became misaligned with the input tickets, effectively invalidating the evaluation for a large portion of the test set .
    *   **Generic Justifications:** Explanations for decisions were often vague and failed to ground the choice in specific evidence from the conversation history .
    *   **Flawed Routing:** The agent systematically made incorrect decisions, such as downgrading urgent messages or treating compromised evidence as valid .

2.  **Weak Grounding (Output & Transcript Dimensions):** A recurring theme is the lack of traceability and justification.
    *   **Missing Evidence References:** The output frequently lacked the specific message IDs that triggered a particular action, making the decision appear arbitrary .
    *   **Unspecified Logic:** The chat transcript revealed that the core logic for routing messages (i.e., the "contract") was never clearly defined in the prompts, leading to the AI inferring rules that were incorrect .

3.  **Lack of Ownership (Transcript & Interview Dimensions):** During the interview, the candidate struggled to defend the implementation details of their own system.
    *   **Vague Answers:** When questioned about specific parts of the system, the answers were general rather than being grounded in the actual data schema or code paths .
    *   **Reactive Defense:** The defense appeared to rely on high-level descriptions rather than concrete, defensible implementation details, failing to demonstrate deep ownership .

**Root Cause Tree: Uncovering the Underlying Problems**

Tracing these symptoms backward leads to a chain of root causes that reveal a flawed development process and a misunderstanding of the competition's core requirements.

*   **#1 Root Cause: Absence of a Formal, Written Specification**
    This is the foundational failure. The evaluators repeatedly emphasize the need to start with a "short written spec" or "routing spec" that defines the system's contract in actionable terms before building begins . Rohith's process, as evidenced by the transcript, relied on "very open-ended prompts" for core design choices . This methodological choice transferred the burden of requirement definition from the developer to the AI, introducing massive ambiguity. Without a formal specification, the AI was left to guess the intended logic, leading directly to the flawed routing implementation. This single factor explains the majority of the downstream symptoms.

*   **#2 Root Cause: A Flawed Core Algorithm (Inverted Escalation Logic)**
    As a direct consequence of the first root cause, the implementation of the core routing logic was fundamentally inverted. The feedback explicitly states that the routing control flow was designed to "escalate to the model in the wrong situation (the ‘clear signal’ path) while ambiguous cases can fall through to a default" . This is a critical logical error. The purpose of an escalation mechanism is to flag uncertainty for human review, yet the system was doing the opposite: escalating on clarity and leaving ambiguity to chance. This single algorithmic flaw is the direct cause of the vast majority of incorrect routing decisions and generic justifications observed in the output.

*   **#3 Root Cause: Reactive Development Over Proactive Constraint Definition**
    The development process was characterized by a reactive, rather than proactive, approach. The transcript shows a pattern of responding to failures ("point to a specific wrong decision and ask for a precise policy/prompt change") instead of preventing them through upfront constraint definition . The evaluators recommend shifting from this audit-and-fix loop to a more disciplined process of starting with a spec and using it to constrain what gets built . This reactive stance led to a brittle system that could not handle edge cases or adversarial inputs reliably, as seen in the "fragile" media handling for voice notes .

**Evaluation of Perceived Strengths**

Rohith previously believed he was strong in areas like multimodal systems and deterministic pipelines. The feedback provides a nuanced view of these claims:
*   **Confirmed Strength:** The praise for "clear separation of responsibilities, robust retries/fallbacks" confirms that his backend engineering and systems design skills are a genuine strength . These are transferable, production-grade skills.
*   **Strength that did not translate into competition score:** His belief in his ability to build "deterministic pipelines" appears to be misplaced in this context. The evidence shows that the pipeline was not deterministic in its final output because the core logic was flawed and the process was driven by ambiguous AI prompts. His strength in engineering did not override the flawed methodology.
*   **Superficial Strength:** Claims of being strong in "multimodal systems" are difficult to validate without seeing the implementation, but the feedback's critique of "fragile" media handling for voice notes suggests that this aspect of the system was not robust, indicating a potential gap between perceived and actual capability .

In conclusion, the single biggest problem was not any single component but the combination of a specification-less development methodology and a flawed core algorithm born from it. This systemic deficiency undermined the entire submission, regardless of individual strengths in other areas.

## Strategic Imperatives: Actionable Changes for Top-10 Performance

Based on the forensic analysis of the HackerRank feedback, a new, evidence-based strategy is required to bridge the gap to Top-10 performance. This strategy must pivot away from an experimental, AI-driven coding style towards a disciplined, engineer-led orchestration of AI tools. The following sections outline the high-leverage changes needed, what to preserve, what to stop doing, and the updated winning formula for the next submission.

### High-Leverage Changes for the September Build

The feedback mandates a shift in mindset from "coding with AI" to "specifying and validating with AI." The changes below are prioritized based on their direct impact on the root causes identified.

1.  **Implement a Pre-Build Specification Document (Highest Priority)**
    *   **Direct Feedback:** "start with a short written spec inside the first prompt—required output fields plus the decision rules that separate ‘supported vs contradicted vs not enough evidence’" .
    *   **Current Problem:** Ambiguity in requirements led to a flawed routing algorithm and generic outputs.
    *   **Exact Change:** Before writing any code, create a dedicated specification document (`spec.md`). This document must formally define the agent's core logic, including a complete decision matrix for all possible actions (`notify`, `digest`, `mute`) with explicit conditions, examples, and the expected supporting evidence for each rule.
    *   **Expected Competitive Impact:** This change directly addresses the #1 root cause. By providing a clear, unambiguous contract for the AI to follow, it prevents the implementation of incorrect logic and ensures the final output is grounded in predefined rules, dramatically improving scores in the Output and Transcript dimensions.

2.  **Refactor the Core Routing Logic (High Priority)**
    *   **Direct Feedback:** "tightening this means making ambiguity the explicit trigger for model help" .
    *   **Current Problem:** The system escalates on "clear signals" and fails on ambiguity, a fundamental logical inversion.
    *   **Exact Change:** Rewrite the control flow to implement the corrected logic. Simple, deterministic rules should handle obvious cases. Only borderline or ambiguous cases should be routed to the LLM for escalation. This requires a clear definition of what constitutes "ambiguity."
    *   **Expected Competitive Impact:** This change fixes the #2 root cause, the flawed algorithm. It will directly improve the correctness of the `output.csv`, reducing the number of incorrect routing decisions and bringing the agent's behavior in line with the specified rules.

3.  **Introduce a Mandatory Post-Processing Validation Pass (High Priority)**
    *   **Direct Feedback:** "require the system to always pick the specific prior messages that triggered the outcome" and "verify that the chosen evidence truly supports the action" .
    *   **Current Problem:** Decisions were not grounded in evidence, leading to generic justifications and a lack of traceability.
    *   **Exact Change:** Add a final script that runs after the main processing pipeline. This script must validate every row in the `output.csv`, checking for: (1) preservation of input row order, (2) that the `justification` column explicitly cites the specific triggers and evidence IDs, and (3) that the selected evidence ID corresponds to a relevant message in the conversation history.
    *   **Expected Competitive Impact:** This enforces rigor and traceability, directly addressing the feedback on weak grounding. It improves the quality of the output file and prepares the candidate to defend their work with concrete evidence during the interview, boosting both Output and Interview scores.

### Strategic Preservation, Removal, and Improvement

Not all of Rohith's approach needs to be discarded. An effective strategy involves selectively preserving, removing, and improving different aspects of the workflow.

*   **What to Preserve:** The evaluators praised the code's "clear separation of responsibilities, robust retries/fallbacks, and conservative behavior" . These are excellent engineering practices that contribute to a robust and maintainable system. They should be retained and built upon.
*   **What to Stop Doing:** Rohith must stop relying on "open-ended prompts" and trusting the AI to infer complex logic without a clear contract . He must also stop assuming that the AI will handle edge cases correctly without explicit instructions and safety overrides . This reactive, implicit approach was a primary contributor to the failure.
*   **What to Improve:** The development process needs to shift from reactive iteration to proactive constraint definition. Instead of auditing failures, the focus should be on defining the system's boundaries and rules upfront . The interview defense must be improved by moving from high-level descriptions to concrete, technical walkthroughs of the system's components and data flows, as recommended by the evaluators .

### Revised Winning Formula and Personal Checklist

Rohith's winning formula must evolve from simply leveraging AI to orchestrating it with precision and discipline.

**Rohith's Orchestrate Winning Formula (Updated):**
> **Engineer-Led Design + Specification-First Execution + Rigorous Validation + Honest Communication**

This formula encapsulates the lessons learned. It starts with a human-led design phase, transitions to a disciplined build process guided by a written spec, incorporates a mandatory validation gate to ensure quality, and culminates in a transparent and technically deep interview defense.

**Personal Checklist for Submission:**

To operationalize this new formula, the following checklist must be completed before every submission:

*   ☐ **Specification Complete:** I have created a `spec.md` file detailing the exact decision rules, actions, and expected evidence for my agent.
*   ☐ **Input/Output Defined:** I have defined the exact inputs and outputs for every function and component in my system.
*   ☐ **Logic Corrected:** My routing logic is designed to escalate only on ambiguity, not on clarity. I have tested this with canonical edge cases.
*   ☐ **Validation Script Run:** I have executed my validation script on the generated `output.csv` to verify:
    *   Row order matches the input exactly.
    *   For each row, the `justification` cites specific evidence from the conversation history.
    *   The selected evidence ID is present, unique, and relevant to the decision.
*   ☐ **Interview Rehearsed:** I have rehearsed a one-minute end-to-end walkthrough of my agent's logic, ready to defend every part of it with references to the code and data schema.
*   ☐ **Security Audited:** I have removed all API keys from source files and am using environment variables exclusively .

By adopting this structured, evidence-based approach, Rohith can directly address the specific deficiencies highlighted by the HackerRank evaluators. This focused strategy moves beyond generic best practices and targets the precise, high-leverage changes necessary to transform his submissions from solid but flawed efforts into Top-10 contenders.