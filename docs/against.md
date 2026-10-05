# The case against this tool

Written as strongly as I can make it, because a project that cannot argue
against itself has not been thought about hard enough — and because several of
these objections are supported by this repository's own measurements.

Nothing here is a strawman. Where an argument is decisive, it says so.

---

## 1. It solves the tractable half and may disguise the hard half

Verifying that a cited work **exists** is the easy problem. Verifying that it
**says what the citing text claims** is the one that matters, and this tool
barely touches it.

Quote verification covers only openly available sources. Most scholarly text is
paywalled, so on a typical document the honest answer to "does this source
support the claim" is *unchecked*. A reader who sees a green result has been
told that the references are real, and may hear that the argument is sound.

**This is the strongest objection in the list.** The mitigation — separating
quote findings from the citation score, capping detection coverage at 60% in
the business case, and refusing to refute a quote without full text — reduces
the risk but does not remove it. A tool that makes the cheap check cheaper can
crowd out the expensive check that was the point.

## 2. A passing badge is an unearned signal

The failure at Deloitte, EY and KPMG was not that nobody checked. It was that
checking was performed on output that looked correct, and the check was
satisfied by appearances.

A CI badge is an appearance. "citeaudit passed" is exactly the kind of artifact
that substitutes for judgment, and institutions are extremely good at
converting a signal into a box to tick. It is entirely possible that this tool
gets adopted, passes, and the next fabricated report ships with a green badge
on the repository that produced it — having been *more* trusted, not less,
because a machine said something.

There is no technical fix. The exit-code design tries to help by refusing to
fail a build on inconclusive checks, which keeps the badge from meaning more
than it should. It is a partial answer at best.

## 3. It creates an incentive to game the input

This repository's own data shows references carrying a DOI verify at 3.44%
against 18.07% for description-only entries. That gap is presented as an
argument for mandating identifiers.

It is equally an argument for **attaching a DOI to make the tool quiet**. A
plausible-looking DOI silences the check, and a *wrong* DOI silences it almost
as well unless the title comparison catches it — which is precisely the
comparison that produced fourteen false accusations across two rounds before it
was fixed.

Mandating identifiers may improve bibliographies. It may also produce
bibliographies optimised for a checker.

## 4. The base rate may make document-level detection hopeless

This is the objection this project's own findings raise most directly.

Legitimate author-written bibliographies come back **13.16%** unverified
(arXiv, n=1,201) and **13.92%** (Wikipedia scholarly, n=237). Those are real
references failing for real reasons: non-indexed venues, workshop papers,
transcription errors.

A fabricated citation is one more entry in that pile. Unless a document is
extraordinarily bad, a handful of fabrications is statistically invisible
against a 13% legitimate failure rate. The tool can flag *individual*
references for a human to inspect, but the idea of an aggregate "integrity
score" that separates honest documents from dishonest ones is not supported by
the measurements.

**That argument is largely correct.** The right conclusion is narrower than the
project's framing sometimes suggests: this is a triage aid, not a detector.

## 5. Coverage is structurally worst exactly where the problem is

Scholarly indexes cover scholarly publishing. The fabrication incidents
happened in consulting deliverables and government reports — grey literature,
which Crossref and OpenAlex largely do not index.

Within Wikipedia, `cite journal` references come back 13.7% unverified while
`cite web` reaches 64.4% and `cite news` 79.2%. Those high numbers measure
index coverage rather than integrity, which is why they are reported
separately — but they also show what happens when this tool meets a
bibliography full of reports, memoranda and web sources.

A consulting report's bibliography looks far more like the second group than
the first. **The tool is weakest on precisely the corpus it was built for.**

## 6. It would have caught only part of the case that motivated it

Deloitte's retracted report contained fabricated academic references *and* a
fabricated quote attributed to a real federal court judge.

The references: caught. The judicial quote: **not caught**, because Australian
court judgments are not in Crossref and the quote verification path has no
source text to check against.

On the flagship example, this is roughly a half-solution.

## 7. The extrapolation is still an extrapolation

The corpus agreement — 13.16% and 13.92% across expert and non-expert authors —
is the strongest empirical result here, and it makes carrying the figure to
consulting deliverables more defensible than a disclaimer would.

It does not make it valid. Both corpora are public, both are audited in some
form, and neither was produced under commercial deadline pressure by someone
whose incentive is to finish. The true rate in the target corpus could be
materially higher — or lower, if professional bibliographies are assembled with
more care than a Wikipedia edit.

No amount of sampling public data closes that gap. Only sampling the actual
corpus would, and it is not publicly samplable.

---

## What survives

Taking the above seriously, the defensible claim is narrower than "this
prevents the next retraction":

- It finds **individual** references that do not resolve, fast, at a measured
  false-positive rate of 0.00% with identifiers and 1.30% without.
- It catches the specific failure a link checker cannot see: a real identifier
  attached to a different work.
- It establishes base rates that **did not previously exist**, which is what
  makes any score interpretable at all — including the base rate that argues
  against its own aggregate scoring.
- It is free, has no stored credentials, and adds a check where there was none.

That is worth having. It is not a solution to fabricated citations, and a
reader who takes it for one has been misled — which is why this document is in
the repository rather than left for someone else to write.

## The objection I have not answered

Argument 4 is the one I cannot dispose of. If a 13% legitimate failure rate
buries fabrication in noise, then aggregate scoring is close to useless and the
tool's value collapses to per-reference triage.

Testing it properly needs something this project does not have: a corpus of
documents with **known** fabricated references, to measure detection against.
The retracted reports would serve, and they are not public in a usable form.

Until that exists, treat the integrity score as a prompt to look, never as a
verdict.
