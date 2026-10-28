# LinkedIn post (draft)

Attach: `docs/media/family-vault-demo.gif`

---

₹1.84 lakh crore of Indian families' money is lying unclaimed. Most of it isn't lost. Nobody knew where it was.

Bank deposits nobody came back for. Insurance policies whose nominee died years ago. Shares sitting in IEPF because the family didn't know the demat account existed. When an earner dies or falls ill, families scramble through cupboards, emails and passbooks — and money quietly moves to unclaimed-funds pools.

So I built family-vault: a proof of value that maps WHERE a family's assets, nominees and papers are (never full account numbers, only the last 4 digits), finds the gaps, and generates an "if something happens" checklist.

The interesting part is not the app. It's the modelling.

The traditional approach is a list of accounts: one row per FD, one per policy, a "nominee" text column. It looks fine until you ask real questions:
→ Which policies name a nominee who has passed away?
→ Is a minor the nominee, with no guardian recorded?
→ Does only ONE person in the family even know this account exists?
→ If Rohan dies tomorrow, who walks into which bank, carrying which papers?

Every one of those is a relationship question. So I modelled the family as a knowledge graph with an ontology:
• 7 classes (Person, Asset, Liability, Document, Institution, Advisor, Nominee) and 7 relations (owns, nominee_of, guardian_of, held_at, documented_by, advised_by, knows_about)
• The ontology is validated on every write and exports to Turtle/JSON-LD, so an insurer or advisor can speak the same vocabulary
• Every fact carries provenance: source, time, confidence, and whether a human, a rule or a model asserted it

What that bought:
1️⃣ Gap detection became graph patterns, not spaghetti code. "Minor nominee without guardian" is a 2-hop check. "Single point of knowledge" is how many people have a knows_about edge to the asset. 8 deterministic rules, each with a plain-language fix.
2️⃣ The checklist is a traversal: asset → institution → documents → nominee (or the guardian, or the joint holder, or the next of kin), with steps blocked by gaps flagged.
3️⃣ Privacy by structure: a nominee's view is just a subgraph. Field-level encryption on sensitive properties, a two-step unlock (passphrase + authenticator code), and a tamper-evident audit log. The LLM only ever sees structure (asset type, action, counts), never names or numbers.
4️⃣ A new asset type is a line in the ontology, not a schema migration.

Measured on 3 synthetic families with planted gaps:
✅ 23/23 gaps found, 0 false positives (precision and recall 100%)
✅ 9/9 checklists match hand-written references
✅ 22/22 full account, card, Aadhaar, PAN and PIN inputs rejected with an explanation
(Caveat: I wrote both the rules and the test set. This shows the engine matches its spec, not real-world accuracy.)

Why this matters in India 🇮🇳
• ₹98,073 cr in unclaimed bank deposits in RBI's DEA Fund (Jan 2026)
• ₹21,718 cr in unclaimed insurance (Mar 2024)
• ₹89,004 cr of shares in IEPF (Nov 2025)
• 23.4 crore demat accounts (Jul 2026) and a ~43 crore-strong middle class: more households own more scattered assets every year

My rough sizing (assumptions, not research):
• TAM: ~10 crore middle-class households × ₹999/yr ≈ ₹10,000 cr/yr
• SAM: ~3 crore digitally active investing households ≈ ₹3,000 cr/yr
• Early SOM: 1% of SAM in 3–5 years ≈ 3 lakh families ≈ ₹30 cr ARR, before an advisor channel (CAs, MF distributors and insurance agents onboarding their clients' families)

It's a proof of value with synthetic data only, not a product. Productizing it needs proper key management, legal review of emergency access, DPDP compliance, and institution-verified claim guides.

Code and eval report: https://github.com/KaranNMakim/family-vault

If you've ever helped a family settle someone's affairs, I'd love to hear what was hardest to find.

#KnowledgeGraph #Ontology #FinTech #India #PersonalFinance #EstatePlanning #DataModelling #ProductManagement

---

## Sources

- ₹1.84 lakh crore unclaimed (Department of Financial Services, Oct 2025): https://www.businesstoday.in/amp/personal-finance/banking/story/finance-minister-launches-rs-1-84-lakh-crore-unclaimed-assets-campaign-496827-2025-10-04
- ₹98,073 crore in DEA Fund, 31 Jan 2026 (Finance Ministry data): https://insights.dsij.in/dsijarticledetail/rs-98073-crore-in-unclaimed-bank-deposits-how-to-find-forgotten-money-through-rbis-udgam-portal-58952
  - Note: other parliamentary replies give ₹72,454 cr (28 Jan 2026) and ₹86,917 cr (30 Jun 2026); the sources don't reconcile the bases. https://www.outlookmoney.com/banking/rs-86917-crore-in-unclaimed-bank-deposits-sbi-accounts-for-largest-share
- ₹21,718 crore unclaimed insurance, 31 Mar 2024 (Lok Sabha reply): https://moneylife.in/article/insurers-have-rs21718-crore-unclaimed-funds-irdai-does-not-maintain-details-govt/76285.html
- ₹89,004 crore of shares in IEPF, 30 Nov 2025: https://www.businesstoday.in/amp/personal-finance/investment/story/reliance-industries-tops-iepf-unclaimed-shares-rs89000-crore-stuck-across-1671-companies-report-525182-2026-04-12
- ₹2.2 lakh crore estimate (1 Finance, Dec 2025): https://www.businesstoday.in/amp/personal-finance/news/story/rs-22-lakh-crore-unclaimed-funds-lie-idle-across-banks-epf-insurance-stocks-mfs-524958-2026-04-10
- 23.4 crore demat accounts, Jul 2026: https://newsable.asianetnews.com/business/demat-account-additions-surge-in-july-2026-reach-234-4-million-articleshow-hykhvbp
- Middle class 43.2 crore people (PRICE ICE 360, 2021): https://stratnewsglobal.com/trade-tech/a-rapidly-expanding-middle-class-is-reshaping-indias-socio-economic-fabric/

Sizing assumptions: ~4.5 people per household → ~10 crore middle-class households; ~3 crore unique investing, digitally active households (demat accounts include duplicates per person and family); ₹999/year family subscription (pricing hypothesis from the README).
