# citeaudit

**Verify that the citations in a document actually exist.**

[![ci](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/ci.yml/badge.svg)](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/ci.yml)
[![live-verification](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/live-verification.yml/badge.svg)](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/live-verification.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Point it at a document. It extracts every DOI, arXiv identifier, URL, and
bibliographic reference, checks each against the authority that can answer for
it, and tells you which ones do not hold up.

```bash
pip install citeaudit
citeaudit report.docx
```

---

## Why this exists

Between October 2025 and May 2026, three of the world's four largest
professional services firms retracted or corrected published reports containing
citations that did not exist.

- **Deloitte Australia** refunded part of a A$440,000 contract with the
  Department of Employment and Workplace Relations after a 237-page assurance
  review was found to contain a fabricated quote attributed to a federal court
  judge and references to academic papers that had never been written.
  ([The Guardian](https://www.theguardian.com/australia-news/2025/oct/06/deloitte-to-pay-money-back-to-albanese-government-after-using-ai-in-440000-report))
- **EY** withdrew a study after a majority of its citations could not be
  verified.
- **KPMG** opened a review and withdrew a report over similar failures.

Every one of those documents passed internal quality assurance and partner
review. Two passed client sign-off.

The reason is not that reviewers were careless. It is that professional review
was designed to catch the mistakes humans make — arithmetic slips, logical
gaps, weak sourcing. Machine-generated text fails differently. It produces
references that are correctly formatted, plausibly titled, attributed to real
researchers in the right field, and published in journals that exist. Nothing
about them looks wrong, because nothing about them *is* wrong except that the
paper was never written.

Checking that by hand takes about ninety seconds per reference. A 237-page
report has hundreds. That arithmetic is why it does not get done, and it is the
entire reason this tool exists.

## What it catches that a link checker does not

A link checker asks "does this URL respond". That is the wrong question, and
answering it well provides false assurance.

The dangerous failure is a **real DOI attached to the wrong paper**. The link
resolves. A reviewer clicks it and lands on a genuine article in a real journal.
The citation passes every check that stops at HTTP 200 — and it is still wrong,
because it is not the source that supports the claim being made.

citeaudit compares what the document *claims* about a reference against what
the authority actually *holds* under that identifier:

```
MISM  line 42   10.1038/nature14539
      document says: 'Procedural fairness in machine-assisted eligibility determination'
      record holds:  'Deep learning'
      identifier resolves to a DIFFERENT work (8% title similarity)
      check it: https://doi.org/10.1038/nature14539
```

It also catches references carrying no identifier at all, by searching Crossref
for the described work. If nothing close exists, that is reported — which is
how a confident reference to a paper nobody ever wrote gets found.

## Verdicts

The taxonomy is the most important design decision in the tool.

| Verdict | Meaning | Counts as failure |
|---|---|:---:|
| `VERIFIED` | Resolves, and the record matches the claim | |
| `MISMATCH` | Resolves, but to a **different work** than claimed | ✓ |
| `NOT_FOUND` | Well-formed identifier, no such record exists | ✓ |
| `MALFORMED` | Identifier is syntactically invalid | ✓ |
| `UNREACHABLE` | Could not complete the check | |
| `UNVERIFIABLE` | No identifier and no title specific enough to search | |

**A network timeout is not evidence of fabrication.** A tool that reports
"citation not found" when an API was slow is committing precisely the error it
exists to catch: emitting a confident claim its evidence does not support.
`UNREACHABLE` and `NOT_FOUND` are separate verdicts, counted separately, and
inconclusive checks are excluded from the integrity score's denominator rather
than silently passed or failed.

Where nothing could be checked, the score is `n/a` — never 0% or 100%.

## Usage

```bash
citeaudit report.docx                      # human-readable
citeaudit paper.pdf --format json -o out.json
citeaudit *.md --format html -o report.html
citeaudit thesis.tex --show-verified       # include passing citations

citeaudit draft.md --fail-under 95         # gate on integrity score
citeaudit draft.md --strict                # inconclusive also fails
```

Supported inputs: `.md` `.txt` `.rst` `.tex` `.html` `.pdf` `.docx`

Exit codes: `0` clean, `1` failures found, `2` tool error.

### As a GitHub Action

```yaml
- uses: harshit-malik-nyu/citeaudit@v1
  with:
    paths: 'docs/**/*.md reports/*.pdf'
    fail-under: '95'
    mailto: 'you@example.com'
```

### As a library

```python
from citeaudit.verify import Verifier

report = Verifier().verify_file("manuscript.docx")
for finding in report.failures:
    print(finding.citation.raw, finding.detail, finding.evidence_url)
```

## Live evidence

This repository does not ask you to take its word for anything.

A [scheduled workflow](.github/workflows/live-verification.yml) runs the tool
against the real Crossref and arXiv APIs every week and commits what they
returned:

- [`evidence/demo-report.json`](evidence/) — full findings with evidence URLs
- [`evidence/demo-report.md`](evidence/) — the same, readable
- [`evidence/manifest.json`](evidence/) — timestamps, commit SHA, run URL, artifact hashes
- [`docs/index.html`](docs/) — rendered report, published to GitHub Pages

Every finding carries an `evidence_url` pointing at the authority record that
produced the verdict. You can confirm or refute any line of any report without
running this code.

## Authorities

| Authority | Answers | Limits |
|---|---|---|
| [Crossref](https://www.crossref.org) | Does this DOI exist, and what is it | Covers scholarly publishing; not books, reports, or grey literature |
| [arXiv](https://arxiv.org) | Does this preprint exist | Preprints only |
| HTTP | Does this URL respond | Liveness only — proves nothing about content |

Both scholarly APIs are free and maintained on public goodwill. The client
paces its requests and identifies itself with a contact address per Crossref's
polite-pool convention. Please set `--mailto`.

## Limitations

Stated plainly, because a verification tool that oversells itself is
self-refuting.

- **A `NOT_FOUND` is not proof of fabrication.** Crossref does not cover books,
  government reports, working papers, or most grey literature. A real reference
  to a real report will fail this check. The tool reports what the authority
  said; judgment stays with you.
- **`VERIFIED` does not mean the source supports the claim.** It means the
  reference points at a real work that matches the description. Whether that
  work actually says what the document claims is a different problem, and this
  tool does not attempt it.
- **Quote verification is not implemented.** Deloitte's fabricated judicial
  quote would not be caught by this version. Catching it requires full-text
  retrieval, which is licensing-constrained for most publishers.
- **Reference parsing is heuristic.** Citation styles vary enormously.
  Unparsed references are reported as `UNVERIFIABLE` rather than skipped
  silently, so you can see what the tool could not read.
- **Title matching has thresholds**, set conservatively so that a false
  accusation is rarer than a missed detection. See
  [`src/citeaudit/match.py`](src/citeaudit/match.py) for the reasoning.

## Development

```bash
make install
make test       # offline suite
make live       # hits real APIs
make demo
```

The test suite is split deliberately. Offline tests use stub transports so a
failure always means the code is wrong, never that an API was slow. Live tests
run in CI and skip rather than fail when an authority is unreachable — the same
distinction the tool draws between `NOT_FOUND` and `UNREACHABLE`.

## License

MIT
