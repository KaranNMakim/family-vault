# Demo script (about 10 minutes, three flows)

Setup: `make demo`, then open http://localhost:3000. All families are fictional. Re-run `make seed` (or restart
`make demo`) to reset the sample vaults.

## Flow 1: onboard a family and see the gaps (4 min)

**Story:** a new family uses the guided conversation, and the vault immediately finds a risk.

1. On the start page, under **Start a new family**, enter `Iyer family` and a passphrase such as `iyer-demo-pass`.
   Click **Create vault and set up 2-step verification**. Enter the code from the demo
   authenticator (or scan the setup key into your own authenticator app) to finish.
2. The vault asks for your name: enter `Meera Iyer`, date of birth `1985-02-02`. Continue.
3. Add a family member: `Tara Iyer`, relation *daughter*, date of birth `2019-01-01`. Click **That's everyone — next**.
4. "Do you have an insurance policy?" Answer **Yes**.
5. Show the masking guard: in "Last 4 digits", type `123456789012`. The field turns red with *"This looks like a
   full number…"* and Save is disabled. (The API rejects it too, with the same explanation.) Replace it with `7788`.
6. Fill in: name `Term plan`, insurer `Kaveri Life (fictional)`, whose: Meera, nominee: **Tara**, tick *I know where
   the papers are* → `Steel cupboard`. Save, then answer **No** to "another".
7. Click **Skip this section** for the remaining sections (progress reaches 100%). Click **See the gaps we found**.
8. Point out: **Urgent: Minor nominee has no guardian / appointee**. Tara is 7. Click **Record a guardian** → choose
   Meera → Save. The gap disappears and readiness rises.
9. Optional: open **Overview** to show the score and its category breakdown. Then try **I prefer a form** on the
   *Add details* page: it is the same data through a plain form.

## Flow 2: a nominee sees only their scope (3 min)

**Story:** the Mehta family (young children, home loan).

1. On the start page, point out **How this vault is protected**. On **Mehta family (synthetic)** click **Continue**
   (passphrase pre-filled). Step 2 asks for the 6-digit code: type the one shown by the *demo authenticator* and
   click **Verify and unlock**. (Try a wrong code first: it is refused and the attempts left are shown.)
2. **Overview:** readiness **61 — Some important gaps**. The top fix is the minor nominee on Rohan's term plan (+15).
3. **Estate map:** coloured rings mark gaps. Tap *Term life cover*: details, gaps, connections and provenance
   (`seed:family_a · human`).
4. In the header, **Viewing as → Ananya Mehta (nominee)**.
5. Open **Nominee view**: only 3 assets (stock trading account, SIP folio, salary account), with the institution,
   last 4 digits and where the papers are. The term plan, her own FD and the home loan are **not** visible, nor are
   private notes. Note the read-only label in the header and the shorter menu.
6. Open **If something happens**: the checklist only includes steps for her assets. Click **Download PDF**.
7. Switch back: **Viewing as → Rohan Mehta (owner)**. Open **Vault & audit**: the role switch and every view are in
   the audit log, and the hash chain is verified.

## Flow 3: emergency access with cancel (3 min)

**Story:** the Nair family. Arjun is the only earner; his mother Lakshmi is the nominee.

1. Lock the vault, then open **Nair family (synthetic)**.
2. **Emergency access** → *Who is asking?* **Lakshmi Nair (nominee)**, waiting period **72 hours** → **Send request**.
   The owner's notifications show *"Lakshmi Nair requested emergency access. It opens in 72 hours unless you cancel."*
3. Click **Try to open access now**: refused, *waiting period not over*.
4. As the owner, click **Cancel this request (owner)**. The timeline shows *Cancelled by owner*.
5. Send a new request (24 hours), then click **Fast-forward 24h** on the demo clock and **Try to open access now**:
   status becomes **active**.
6. Click **See what Lakshmi Nair sees**: a read-only view of only the 5 assets she is nominee on. The old college
   account (nominee: an unreachable friend) is not visible.
7. Switch back to the owner and open **Vault & audit**: `emergency.requested`, `emergency.cancelled`,
   `emergency.activated` and `emergency.view` are all recorded.

## Talking points

- Only the last 4 digits are ever stored; full numbers, Aadhaar/PAN, passwords and OTPs are refused with an explanation.
- Gaps and checklists are deterministic rules. The AI, if enabled, only polishes wording, and never sees family data.
- Each checklist is general guidance, clearly labelled. Verify with the institution or a professional.
