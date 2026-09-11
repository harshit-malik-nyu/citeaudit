# What a fabricated citation costs

A sizing of the problem citeaudit addresses, and of what avoiding it is worth.

Every input is labelled by evidence class. Three are observed facts. The rest
are estimates, and they are stated as estimates so a reader can substitute
their own and re-derive the answer. A model whose assumptions are buried is not
a model, it is an assertion with arithmetic attached.

| Class | Meaning |
|---|---|
| **OBSERVED** | Publicly reported. Sourced and checkable. |
| **ESTIMATE** | My assumption. Defensible, unverified, and the thing to attack. |
| **DERIVED** | Computed from the above. |

---

## 1. The loss event

### Direct cost

| Input | Value | Class | Basis |
|---|---:|---|---|
| Contract value, Deloitte / DEWR | A$440,000 | OBSERVED | [The Guardian, Oct 2025](https://www.theguardian.com/australia-news/2025/oct/06/deloitte-to-pay-money-back-to-albanese-government-after-using-ai-in-440000-report) |
| Portion refunded | Final instalment | OBSERVED | Partial, not total |
| Assumed refund share | 25% | ESTIMATE | Final instalment on a four-stage engagement |
| **Direct refund** | **A$110,000** | DERIVED | |

The refund is the smallest line in the total, and the only one that appears in
the press. It is the visible tip of the loss, not the loss.

### Remediation cost

| Input | Value | Class | Basis |
|---|---:|---|---|
| Report length | 237 pages | OBSERVED | Reported |
| References requiring manual re-verification | 300 | ESTIMATE | Typical density for a report of this length |
| Minutes per manual check | 3 | ESTIMATE | Locate, open, confirm the claim is supported |
| Consultant hours | 15 | DERIVED | |
| Partner/QA review hours | 40 | ESTIMATE | Response drafting, client management, internal review |
| Blended rate | A$400/hr | ESTIMATE | Mixed seniority |
| **Remediation** | **A$22,000** | DERIVED | |

### Commercial cost

This is the line that matters, and the hardest to defend.

| Input | Value | Class | Basis |
|---|---:|---|---|
| Annual revenue from the affected client segment | A$20,000,000 | ESTIMATE | One government practice, one jurisdiction |
| Win-rate impairment, 12 months post-incident | 3% | ESTIMATE | See sensitivity |
| **Commercial drag** | **A$600,000** | DERIVED | |

A public retraction in a procurement-sensitive segment does not stay contained
to one contract. It becomes a line in a competitor's next pitch. Three percent
is a deliberately conservative placeholder for an effect that is real,
material, and genuinely hard to measure — which is why the sensitivity table
below spans an order of magnitude around it.

### Total

| | |
|---|---:|
| Direct refund | A$110,000 |
| Remediation | A$22,000 |
| Commercial drag | A$600,000 |
| **Expected cost per incident** | **≈ A$732,000** |

The refund is 15% of the total. Reporting that headlines the refund
understates the loss by roughly sevenfold.

---

## 2. Frequency

| Input | Value | Class | Basis |
|---|---:|---|---|
| Major firms with a public incident, Oct 2025 – May 2026 | 3 of 4 | OBSERVED | Deloitte, EY, KPMG |
| Window | 8 months | OBSERVED | |
| Public incidents per firm-year | 0.56 | DERIVED | |
| Ratio of actual to publicly surfaced incidents | 5× | ESTIMATE | Most are caught internally or never surface |
| **Incidents per firm-year** | **≈ 2.8** | DERIVED | |

The 5× multiplier is the weakest number in this document. It is unknowable from
public data by construction — an incident that never surfaced leaves no trace
to count. It is flagged rather than defended.

**Expected annual loss per firm: ≈ A$2.0m** (2.8 × A$732k)

---

## 3. Cost of mitigation

| Input | Value | Class |
|---|---:|---|
| Software licence | A$0 (MIT) | OBSERVED |
| API cost | A$0 (Crossref and OpenAlex are free) | OBSERVED |
| Integration, one-time | 40 engineer-hours | ESTIMATE |
| Maintenance | 4 hours/month | ESTIMATE |
| Triage of flagged references | 2 min each | ESTIMATE |
| **Year-one cost** | **≈ A$35,000** | DERIVED |

### The triage load is the real operating cost

The base-rate study is what makes this line calculable rather than guessed.
Measured false-positive rate on genuine references is **0.5%** when a DOI is
supplied and **2.4%** when it is not
([evidence](../evidence/baserate/report.md)).

For a 300-reference report citing without DOIs, that is roughly **7 false
flags** to triage — about 15 minutes. Tolerable.

Without the OpenAlex fallback the rate would be materially higher; that
fallback rescued 26 of 418 references in the first run that Crossref alone
would have reported as non-existent. Coverage breadth is not a feature here, it
is what keeps the operating cost low enough for anyone to keep the tool
switched on.

---

## 4. Return

| | |
|---|---:|
| Expected annual loss | A$2,050,000 |
| Detection coverage | 60% (ESTIMATE) |
| Loss avoided | A$1,230,000 |
| Mitigation cost | A$35,000 |
| **Net** | **A$1,195,000** |
| **Breakeven** | **one incident every 21 years** |

Detection coverage is capped at 60% because citeaudit verifies that a cited
work exists, not that it says what the document claims. Deloitte's fabricated
judicial quote — attributed to a real judge in a real case — would **not** be
caught by this tool. That limitation is priced in rather than papered over.

---

## 5. Sensitivity

The conclusion holds across the plausible range of every estimate. Net benefit,
A$m, varying the two weakest inputs:

| Win-rate impairment → | 1% | 3% | 5% | 10% |
|---|---:|---:|---:|---:|
| **1× incident rate** (public only) | 0.05 | 0.21 | 0.37 | 0.77 |
| **3×** | 0.25 | 0.72 | 1.20 | 2.40 |
| **5×** (base case) | 0.44 | 1.23 | 2.02 | 4.00 |
| **10×** | 0.93 | 2.51 | 4.08 | 8.02 |

Every cell is positive. The case does not depend on the estimates being right,
only on them being within an order of magnitude — which is the standard a
sizing should actually be held to.

Breakeven requires the incident rate to fall below **one event per 21 years per
firm**. Three of the four largest firms had one in eight months.

---

## 6. Who buys this

| Segment | Why | Channel |
|---|---|---|
| Professional services QA | Direct exposure, demonstrated | Internal deployment |
| Academic publishers | Submission screening at scale | Editorial workflow |
| Government procurement | Received the Deloitte report | Deliverable acceptance criteria |
| Grant bodies | Application screening | Review pipeline |

The natural wedge is **procurement, not the firms**. A client that writes
citation verification into its acceptance criteria forces adoption across every
vendor at once, and has no incentive to resist it. Selling to the firms means
asking them to fund the discovery of their own errors.

---

## What would change this conclusion

- **A published incident-rate study.** The 5× multiplier is the load-bearing
  estimate and it is currently unfounded.
- **Measured win-rate impact.** The commercial line is 82% of the loss and rests
  entirely on one estimate.
- **A firm disclosing real remediation cost.** Would replace two estimates with
  observations.
- **Quote verification shipping.** Would lift detection coverage above 60% and
  roughly double the benefit line.
